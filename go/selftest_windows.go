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
		link := mtprotoLink("127.0.0.1", cfg.MTPort, hexSecret(cfg.Secret))
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
	}
}
