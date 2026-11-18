//go:build windows

package main

import (
	"os"
	"path/filepath"

	qrcode "github.com/skip2/go-qrcode"
)

// showQR сохраняет QR-код во временный PNG и открывает его просмотрщиком.
func showQR(link string) {
	path := filepath.Join(os.TempDir(), "tgrelay-qr.png")
	if err := qrcode.WriteFile(link, qrcode.Medium, 480, path); err != nil {
		messageBox("QR: "+err.Error(), "tgrelay", 0x10)
		return
	}
	shellExecute("open", path)
}
