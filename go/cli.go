package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// runCLI разбирает подкоманды. Возвращает true, если работа завершена
// (команда выполнена и выходить из серверного режима не нужно).
func runCLI(args []string, configPath string) bool {
	cmd := ""
	if len(args) > 0 {
		cmd = args[0]
	}
	path := configPath
	if path == "" {
		path = findConfig()
	}
	ctlPath := filepath.Join(filepath.Dir(path), ctlName)
	logPath := filepath.Join(filepath.Dir(path), "tgrelay.log")

	switch cmd {
	case "", "run", "start":
		return false

	case "help", "-h", "--help":
		printHelp()
		return true

	case "version", "-v", "--version":
		fmt.Println("tgrelay", version)
		return true

	case "status":
		out, err := controlClient(ctlPath, "status")
		if err != nil {
			fmt.Println("не запущено:", err)
			return true
		}
		fmt.Print(out)
		return true

	case "links":
		out, err := controlClient(ctlPath, "links")
		if err != nil {
			cfg, cerr := LoadConfig(path)
			if cerr != nil {
				fmt.Println("ошибка:", cerr)
				return true
			}
			fmt.Print((&App{Cfg: cfg}).Links())
			return true
		}
		fmt.Print(out)
		return true

	case "reload":
		out, err := controlClient(ctlPath, "reload")
		if err != nil {
			fmt.Println("ошибка:", err)
			return true
		}
		fmt.Print(out)
		return true

	case "stop":
		out, err := controlClient(ctlPath, "stop")
		if err != nil {
			fmt.Println("ошибка:", err)
			return true
		}
		fmt.Print(out)
		return true

	case "log":
		tailLog(logPath, args[1:])
		return true

	case "config":
		if len(args) > 1 && args[1] == "edit" {
			openEditor(path)
			return true
		}
		fmt.Println(path)
		return true

	case "check":
		checkConfig(path)
		return true

	case "help-all":
		printHelp()
		return true
	}

	fmt.Fprintf(os.Stderr, "неизвестная команда: %s\n\n", cmd)
	printHelp()
	return true
}

func printHelp() {
	fmt.Print(`tgrelay ` + version + ` — MTProto + SOCKS5 relay

Использование:
  tgrelay [команда] [--config путь]

Без команды запускает сервер (на Windows — с иконкой в трее).

Команды:
  run              запустить сервер (то же, что без команды)
  status           состояние работающего экземпляра
  links            ссылки для Telegram
  reload           перечитать конфиг и перезапустить прокси на месте
  stop             остановить работающий экземпляр
  log [-f] [-n N]  показать лог (по умолчанию 40 строк, -f — следить)
  config           путь к конфигу; config edit — открыть в редакторе
  check            проверить конфиг и доступность прокси/сети
  version          версия
  help             эта справка

Флаги:
  --config путь    свой путь к tgrelay.txt
  --headless       запускать сервер без трея (Linux, службы)
`)
}

// tailLog печатает последние строки и, с -f, следит за файлом.
func tailLog(path string, args []string) {
	follow := false
	lines := 40
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-f", "--follow":
			follow = true
		case "-n":
			if i+1 < len(args) {
				if n, err := strconv.Atoi(args[i+1]); err == nil {
					lines = n
				}
				i++
			}
		}
	}

	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Println("лог не найден:", path)
		return
	}
	text := strings.Split(strings.TrimRight(string(data), "\n"), "\n")
	if len(text) > lines {
		text = text[len(text)-lines:]
	}
	for _, line := range text {
		fmt.Println(line)
	}
	if !follow {
		return
	}

	offset := int64(len(data))
	for {
		time.Sleep(500 * time.Millisecond)
		info, err := os.Stat(path)
		if err != nil || info.Size() <= offset {
			continue
		}
		f, err := os.Open(path)
		if err != nil {
			continue
		}
		_, _ = f.Seek(offset, 0)
		buf := make([]byte, info.Size()-offset)
		n, _ := f.Read(buf)
		f.Close()
		offset += int64(n)
		fmt.Print(string(buf[:n]))
	}
}

// checkConfig проверяет конфиг и доступность апстримов (или прямого выхода).
func checkConfig(path string) {
	cfg, err := LoadConfig(path)
	if err != nil {
		fmt.Println("ошибка конфига:", err)
		os.Exit(1)
	}
	fmt.Println("конфиг:", path)
	fmt.Printf("MTProto: %s, SOCKS5: %s\n",
		portText(cfg.MTPort), portText(cfg.SocksPort))
	if cfg.MTPort == 0 && cfg.SocksPort == 0 {
		fmt.Println("ошибка: оба протокола выключены")
		os.Exit(1)
	}

	pool := NewPool(cfg.Proxies, cfg.Hosts)
	targets := cfg.Hosts
	if len(targets) == 0 {
		targets = []string{"149.154.167.51:443"}
	}

	if pool.Direct() {
		fmt.Println("режим: прямое подключение (прокси не заданы)")
		host, port := splitHostPort(targets[0])
		conn, err := pool.Dial(host, port)
		if err != nil {
			fmt.Printf("прямое подключение к %s: ОШИБКА (%v)\n", targets[0], err)
			fmt.Println("если это VPS за рубежом, проверьте firewall и DNS")
			os.Exit(1)
		}
		conn.Close()
		fmt.Printf("прямое подключение к %s: ок\n", targets[0])
		return
	}

	fmt.Printf("прокси в списке: %d\n", len(cfg.Proxies))
	ok := 0
	for _, proxy := range cfg.Proxies {
		host, port := splitHostPort(targets[0])
		conn, err := openTunnel(proxy, host, port, 10*time.Second)
		if err != nil {
			fmt.Printf("  %-22s ОШИБКА: %v\n", proxy.Addr(), err)
			continue
		}
		conn.Close()
		ok++
		fmt.Printf("  %-22s ок\n", proxy.Addr())
	}
	fmt.Printf("рабочих: %d из %d\n", ok, len(cfg.Proxies))
	if ok == 0 {
		os.Exit(1)
	}
}

func portText(port int) string {
	if port == 0 {
		return "выключен"
	}
	return ":" + strconv.Itoa(port)
}

func splitHostPort(target string) (string, int) {
	i := strings.LastIndex(target, ":")
	if i < 0 {
		return target, 443
	}
	port, _ := strconv.Atoi(target[i+1:])
	return target[:i], port
}
