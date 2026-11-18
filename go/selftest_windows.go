//go:build windows

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// runSelftest — служебные проверки без запуска серверов.
func runSelftest(kind, path string, cfg *Config) {
	switch kind {
	case "clip":
		text := "tg://proxy?server=test&port=1&secret=00"
		setClipboard(text)
		fmt.Println("clipboard set:", text)
	case "qr":
		link := mtprotoLink("127.0.0.1", cfg.MTPort, hexSecret(firstSecret(cfg)))
		showQR(link)
		time.Sleep(500 * time.Millisecond)
		qrPath := filepath.Join(os.TempDir(), "tgrelay-qr.png")
		info, err := os.Stat(qrPath)
		if err != nil {
			fmt.Println("qr error:", err)
			os.Exit(1)
		}
		fmt.Printf("qr ok: %s (%d bytes)", qrPath, info.Size())
		fmt.Println()
	case "settings":
		watchSettings(path)
	case "autostart":
		fmt.Println("before:", autostartEnabled())
		if err := enableAutostart(); err != nil {
			fmt.Println("enable error:", err)
			os.Exit(1)
		}
		fmt.Println("after enable:", autostartEnabled())
		disableAutostart()
		fmt.Println("after disable:", autostartEnabled())
	case "reload":
		fmt.Println("reload: restarting")
		restartSelf()
	}
}

// showFirstRun: конфиг только что создан — открыть его и попрощаться.
func showFirstRun(path string) {
	text := `tgrelay

Config file created / Создан файл настроек:
` + path + `

EN: fill in PROXY= lines (your proxies, HTTP or SOCKS), save the file
    and run the program again. Leave PROXY= empty to work without any
    upstream proxy (direct mode, e.g. on a VPS abroad).
RU: впишите строки PROXY= (ваши прокси, HTTP или SOCKS), сохраните
    и запустите программу заново. Оставьте PROXY= пустым, чтобы работать
    без апстрим-прокси (direct, например на VPS за рубежом).

SECRET / LANG are filled in automatically / заполнятся автоматически.`
	shellExecute("open", path)
	messageBox(text, "tgrelay", 0x40)
}
