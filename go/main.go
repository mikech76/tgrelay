package main

import (
	"flag"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
)

func lanIP() string {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return "127.0.0.1"
	}
	defer conn.Close()
	if addr, ok := conn.LocalAddr().(*net.UDPAddr); ok {
		return addr.IP.String()
	}
	return "127.0.0.1"
}

func mtprotoLink(host string, port int, secret string) string {
	return "tg://proxy?server=" + host + "&port=" + strconv.Itoa(port) + "&secret=" + secret
}

func main() {
	configPath := flag.String("config", "", "путь к tgrelay.txt")
	showVersion := flag.Bool("version", false, "версия и выход")
	headless := flag.Bool("headless", false, "без трея, только серверы")
	selftest := flag.String("selftest", "", "проверка: clip|qr|settings")
	flag.Parse()
	_ = debugFlag

	if *showVersion {
		fmt.Println("tgrelay", version)
		return
	}

	cfg, pool, stats, path, err := loadApp(*configPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	initLog(filepath.Join(filepath.Dir(path), "tgrelay.log"))
	logf("конфиг: %s", path)
	logf("прокси: %d", len(pool.proxies))
	for _, pr := range pool.proxies {
		logf("  %s (%s)", pr.Addr(), kindOrAuto(pr.Kind()))
	}

	if *selftest != "" {
		runSelftest(*selftest, path, cfg)
		return
	}

	servers, err := StartServers(cfg, pool, stats)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer servers.Close()

	runUI(cfg, path, pool, stats, *headless)
}
