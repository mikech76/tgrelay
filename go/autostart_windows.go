//go:build windows

package main

import (
	"os"
	"os/exec"
	"strings"
)

const runKey = `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
const runValue = "tgrelay"

// autostartEnabled: есть ли наш ключ в HKCU\...\Run.
func autostartEnabled() bool {
	out, err := exec.Command("reg", "query", runKey, "/v", runValue).Output()
	if err != nil {
		return false
	}
	return strings.Contains(string(out), runValue)
}

// enableAutostart прописывает текущий exe в автозагрузку пользователя.
func enableAutostart() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	cmd := exec.Command("reg", "add", runKey, "/v", runValue, "/t", "REG_SZ",
		"/d", `"`+exe+`"`, "/f")
	return cmd.Run()
}

// disableAutostart убирает ключ (ошибку «нет ключа» считаем успехом).
func disableAutostart() {
	_ = exec.Command("reg", "delete", runKey, "/v", runValue, "/f").Run()
}
