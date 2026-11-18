package main

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// App — всё приложение: конфиг, пул, серверы и канал управления.
type App struct {
	mu      sync.Mutex
	Cfg     *Config
	Pool    *Pool
	Stats   *Stats
	Path    string
	servers *Servers
	ctl     net.Listener
	ctlFile string
	started time.Time
	running bool
}

var appInstance *App

func NewApp(path string) (*App, error) {
	cfg, err := LoadConfig(path)
	if err != nil {
		return nil, fmt.Errorf("не читается %s: %w", path, err)
	}
	if err := validate(cfg); err != nil {
		return nil, err
	}
	app := &App{Cfg: cfg, Path: path, started: time.Now()}
	app.Stats = NewStats()
	app.Pool = NewPool(cfg.Proxies, cfg.Hosts)
	return app, nil
}

func validate(cfg *Config) error {
	if cfg.MTPort == 0 && cfg.SocksPort == 0 {
		return fmt.Errorf("оба протокола выключены в tgrelay.txt — запускать нечего")
	}
	return nil
}

// Start поднимает серверы и канал управления.
func (a *App) Start() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	servers, err := StartServers(a.Cfg, a.Pool, a.Stats)
	if err != nil {
		return err
	}
	a.servers = servers
	a.running = true
	if a.Pool.Direct() {
		logf("режим: прямое подключение (PROXY= не заданы)")
	}
	go a.Pool.HealthLoop(appContext, 60*time.Second)
	a.startControl()
	return nil
}

// Reload перечитывает конфиг и перезапускает серверы на месте (без выхода).
func (a *App) Reload() error {
	cfg, err := LoadConfig(a.Path)
	if err != nil {
		return fmt.Errorf("конфиг не прочитан: %w", err)
	}
	if err := validate(cfg); err != nil {
		return err
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	if a.servers != nil {
		a.servers.Close()
	}
	a.Cfg = cfg
	a.Pool = NewPool(cfg.Proxies, cfg.Hosts)
	servers, err := StartServers(a.Cfg, a.Pool, a.Stats)
	if err != nil {
		return err
	}
	a.servers = servers
	go a.Pool.HealthLoop(appContext, 60*time.Second)
	if a.Pool.Direct() {
		logf("режим: прямое подключение (PROXY= не заданы)")
	}
	return nil
}

// Stop закрывает серверы и канал управления.
func (a *App) Stop() {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.servers != nil {
		a.servers.Close()
		a.servers = nil
	}
	if a.ctl != nil {
		_ = a.ctl.Close()
		a.ctl = nil
	}
	if a.ctlFile != "" {
		_ = os.Remove(a.ctlFile)
	}
	a.running = false
}

// Status — текстовый отчёт для CLI и канала управления.
func (a *App) Status() string {
	snap := a.Stats.Snapshot()
	alive, total := a.Pool.Stats()

	var b strings.Builder
	fmt.Fprintf(&b, "version: %s\n", version)
	fmt.Fprintf(&b, "pid: %d\n", os.Getpid())
	fmt.Fprintf(&b, "config: %s\n", a.Path)
	fmt.Fprintf(&b, "uptime: %s\n", formatDuration(time.Since(a.started)))
	if a.Pool.Direct() {
		b.WriteString("mode: direct (no proxies)\n")
	} else {
		fmt.Fprintf(&b, "mode: pool\nproxies: %d/%d alive\n", alive, total)
	}
	if a.Cfg.MTPort != 0 {
		fmt.Fprintf(&b, "mtproto: 0.0.0.0:%d\n", a.Cfg.MTPort)
	}
	if a.Cfg.SocksPort != 0 {
		fmt.Fprintf(&b, "socks5: %s:%d\n", a.Cfg.SocksHost, a.Cfg.SocksPort)
	}
	fmt.Fprintf(&b, "connections: %d\n", snap.Conns)
	fmt.Fprintf(&b, "traffic: up %s, down %s\n",
		human(float64(snap.Up)), human(float64(snap.Down)))
	if lines := a.Stats.UserLines(); len(lines) > 0 {
		b.WriteString("users:\n")
		for _, line := range lines {
			fmt.Fprintf(&b, "  %s\n", line)
		}
	}
	return b.String()
}

// Links возвращает ссылки для Telegram.
func (a *App) Links() string {
	local := lanIP()
	var out strings.Builder
	if a.Cfg.MTPort != 0 {
		secret := hexSecret(firstSecret(a.Cfg))
		fmt.Fprintf(&out, "mtproto: %s\n", mtprotoLink(local, a.Cfg.MTPort, secret))
		if a.Cfg.External != "" {
			fmt.Fprintf(&out, "mtproto-external: %s\n",
				mtprotoLink(a.Cfg.External, a.Cfg.MTPort, secret))
		}
	}
	if a.Cfg.SocksPort != 0 {
		host := a.Cfg.SocksHost
		if host == "" || host == "0.0.0.0" {
			host = local
		}
		fmt.Fprintf(&out, "socks5: %s\n", socksLink(host, a.Cfg.SocksPort, a.Cfg.User, a.Cfg.Pass))
		if a.Cfg.External != "" {
			fmt.Fprintf(&out, "socks5-external: %s\n",
				socksLink(a.Cfg.External, a.Cfg.SocksPort, a.Cfg.User, a.Cfg.Pass))
		}
	}
	return out.String()
}

func formatDuration(d time.Duration) string {
	d = d.Round(time.Second)
	h := int(d.Hours())
	m := int(d.Minutes()) % 60
	s := int(d.Seconds()) % 60
	if h > 0 {
		return fmt.Sprintf("%dh%02dm", h, m)
	}
	if m > 0 {
		return fmt.Sprintf("%dm%02ds", m, s)
	}
	return strconv.Itoa(s) + "s"
}

// --- канал управления ------------------------------------------------------

const ctlName = "tgrelay.ctl"

func (a *App) startControl() {
	path := filepath.Join(filepath.Dir(a.Path), ctlName)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return
	}
	a.ctl = listener
	a.ctlFile = path

	port := listener.Addr().(*net.TCPAddr).Port
	token := randomToken()
	content := fmt.Sprintf("%d %s\n", port, token)
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		listener.Close()
		a.ctl = nil
		return
	}
	go a.serveControl(listener, token)
}

func (a *App) serveControl(listener net.Listener, token string) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		go func(c net.Conn) {
			defer c.Close()
			_ = c.SetDeadline(time.Now().Add(15 * time.Second))
			line, err := bufio.NewReader(c).ReadString('\n')
			if err != nil {
				return
			}
			fields := strings.Fields(line)
			if len(fields) != 2 || fields[0] != token {
				fmt.Fprintln(c, "error: bad token")
				return
			}
			switch fields[1] {
			case "status":
				fmt.Fprint(c, a.Status())
			case "links":
				fmt.Fprint(c, a.Links())
			case "reload":
				if err := a.Reload(); err != nil {
					fmt.Fprintf(c, "error: %v\n", err)
					return
				}
				fmt.Fprintln(c, "reloaded")
			case "stop":
				fmt.Fprintln(c, "stopping")
				go func() {
					time.Sleep(200 * time.Millisecond)
					a.Stop()
					os.Exit(0)
				}()
			default:
				fmt.Fprintln(c, "error: unknown command")
			}
		}(conn)
	}
}

// controlClient — подключение к запущенному экземпляру.
func controlClient(path, command string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("программа не запущена (нет %s)", path)
	}
	fields := strings.Fields(string(data))
	if len(fields) != 2 {
		return "", fmt.Errorf("битый файл управления %s", path)
	}
	conn, err := net.DialTimeout("tcp", "127.0.0.1:"+fields[0], 3*time.Second)
	if err != nil {
		return "", fmt.Errorf("не подключиться к работающей программе: %w", err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(20 * time.Second))
	if _, err := fmt.Fprintf(conn, "%s %s\n", fields[1], command); err != nil {
		return "", err
	}
	reply, err := readAll(conn)
	return reply, err
}

func readAll(conn net.Conn) (string, error) {
	var b strings.Builder
	buf := make([]byte, 4096)
	for {
		n, err := conn.Read(buf)
		b.Write(buf[:n])
		if err != nil {
			break
		}
	}
	return b.String(), nil
}
