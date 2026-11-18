//go:build !windows

package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

// runUI без трея: печатаем ссылки и ждём SIGINT/SIGTERM.
func runUI(app *App, headless bool) {
	cfg := app.Cfg
	local := lanIP()
	if cfg.MTPort != 0 {
		secret := hexSecret(firstSecret(cfg))
		fmt.Println("MTProto link:", mtprotoLink(local, cfg.MTPort, secret))
		if cfg.External != "" {
			fmt.Println("MTProto link (external):",
				mtprotoLink(cfg.External, cfg.MTPort, secret))
		}
	}
	if cfg.SocksPort != 0 {
		host := cfg.SocksHost
		if host == "" || host == "0.0.0.0" {
			host = local
		}
		fmt.Println("SOCKS5 link:", socksLink(host, cfg.SocksPort, cfg.User, cfg.Pass))
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	logf("остановлено")
}
