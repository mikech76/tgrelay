//go:build windows

package main

import (
	"fmt"
	"os"
	"strconv"
	"syscall"
	"time"
	"unsafe"
)

// runUI запускает трей (или ждёт сигнала в режиме --headless).
func runUI(app *App, headless bool) {
	if headless || !singleInstance() {
		printLinks(app)
		select {}
	}
	t := newTray(app)
	logf("трей: окно создано")
	printLinks(app)
	logf("трей: вход в цикл сообщений")
	t.run()
	logf("трей: цикл завершён")
}

func printLinks(app *App) {
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
		if cfg.External != "" {
			fmt.Println("SOCKS5 link (external):",
				socksLink(cfg.External, cfg.SocksPort, cfg.User, cfg.Pass))
		}
	}
	fmt.Println()
}

var lockHandle uintptr

// singleInstance: один экземпляр на сессию; при TGRELAY_HANDOFF=1 ждём до 15 с.
func singleInstance() bool {
	wait := 0.0
	if os.Getenv("TGRELAY_HANDOFF") == "1" {
		wait = 15.0
	}
	deadline := time.Now().Add(time.Duration(wait * float64(time.Second)))
	for {
		handle, _, lastErr := pCreateMutexW.Call(0, 0,
			uintptr(unsafe.Pointer(utf16Ptr("tgrelay-single-instance"))))
		if handle != 0 && lastErr != syscall.Errno(183) { // ERROR_ALREADY_EXISTS
			lockHandle = handle
			return true
		}
		if handle != 0 {
			syscall.CloseHandle(syscall.Handle(handle))
		}
		if time.Now().After(deadline) {
			messageBox(fmt.Sprintf("%s\n\n%s %s", tr("already_running"),
				"tgrelay:", "иконка в трее / tray icon"), tr("already_title"), 0x40)
			return false
		}
		time.Sleep(300 * time.Millisecond)
	}
}

var _ = strconv.Itoa
