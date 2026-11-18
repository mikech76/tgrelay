package main

import (
	"context"
	"encoding/hex"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"sync/atomic"
	"syscall"
	"time"
)

var debug atomic.Bool

func logf(format string, args ...any) {
	stamp := time.Now().Format("2006-01-02 15:04:05")
	fmt.Printf("%s %s\n", stamp, fmt.Sprintf(format, args...))
}

func main() {
	configPath := flag.String("config", "", "путь к tgrelay.txt")
	showVersion := flag.Bool("version", false, "версия и выход")
	flag.Parse()

	if *showVersion {
		fmt.Println("tgrelay (go) 0.1")
		return
	}

	path := *configPath
	if path == "" {
		path = findConfig()
	}
	cfg, err := LoadConfig(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "не читается %s: %v\n", path, err)
		os.Exit(1)
	}
	if cfg.MTPort == 0 && cfg.SocksPort == 0 {
		fmt.Fprintln(os.Stderr, "оба протокола выключены в tgrelay.txt — запускать нечего")
		os.Exit(1)
	}
	if len(cfg.Proxies) == 0 {
		fmt.Fprintln(os.Stderr, "в tgrelay.txt нет ни одного прокси (PROXY=)")
		os.Exit(1)
	}

	logf("конфиг: %s", path)
	logf("прокси: %d", len(cfg.Proxies))
	for _, p := range cfg.Proxies {
		logf("  %s (%s)", p.Addr(), kindOrAuto(p.Kind()))
	}

	pool := NewPool(cfg.Proxies, cfg.Hosts)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go pool.HealthLoop(ctx, 60*time.Second)

	var closers []net.Listener

	if cfg.MTPort != 0 {
		listener, err := net.Listen("tcp", "0.0.0.0:"+strconv.Itoa(cfg.MTPort))
		if err != nil {
			fmt.Fprintf(os.Stderr, "MTProto: %v\n", err)
			os.Exit(1)
		}
		closers = append(closers, listener)
		mt := &MTProto{secret: cfg.Secret, pool: pool, hosts: cfg.Hosts}
		go mt.Serve(listener)
		logf("MTProto слушает 0.0.0.0:%d", cfg.MTPort)
	}

	if cfg.SocksPort != 0 {
		addr := net.JoinHostPort(cfg.SocksHost, strconv.Itoa(cfg.SocksPort))
		listener, err := net.Listen("tcp", addr)
		if err != nil {
			fmt.Fprintf(os.Stderr, "SOCKS5: %v\n", err)
			os.Exit(1)
		}
		closers = append(closers, listener)
		s5 := &Socks5{pool: pool, user: cfg.User, pass: cfg.Pass, bypass: cfg.Bypass}
		go s5.Serve(listener)
		logf("SOCKS5 слушает %s", addr)
	}

	local := lanIP()
	external := cfg.External

	if cfg.MTPort != 0 {
		fmt.Println()
		fmt.Println("MTProto link:", mtprotoLink(local, cfg.MTPort, hex.EncodeToString(cfg.Secret)))
		if external != "" {
			fmt.Println("MTProto link (external):", mtprotoLink(external, cfg.MTPort, hex.EncodeToString(cfg.Secret)))
		}
	}
	if cfg.SocksPort != 0 {
		socksHost := cfg.SocksHost
		if socksHost == "0.0.0.0" || socksHost == "" {
			socksHost = local
		}
		fmt.Println("SOCKS5 link:", socksLink(socksHost, cfg.SocksPort, cfg.User, cfg.Pass))
		if external != "" {
			fmt.Println("SOCKS5 link (external):", socksLink(external, cfg.SocksPort, cfg.User, cfg.Pass))
		}
	}
	fmt.Println()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	for _, listener := range closers {
		listener.Close()
	}
	logf("остановлено")
}

func kindOrAuto(kind string) string {
	if kind == "" {
		return "авто"
	}
	return kind
}

func findConfig() string {
	candidates := []string{"tgrelay.txt"}
	if exe, err := os.Executable(); err == nil {
		candidates = append([]string{filepath.Join(filepath.Dir(exe), "tgrelay.txt")}, candidates...)
	}
	for _, path := range candidates {
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}
	return "tgrelay.txt"
}

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
