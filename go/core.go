package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

const (
	configName = "tgrelay.txt"
	repoURL    = "https://github.com/mikech76/tgrelay"
	version    = "1.6.1"
)

var appContext, cancelApp = context.WithCancel(context.Background())

var logFile *os.File

// initLog дублирует лог в файл рядом с конфигом (в exe нет консоли).
func initLog(path string) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err == nil {
		logFile = f
	}
}

func logf(format string, args ...any) {
	stamp := time.Now().Format("2006-01-02 15:04:05")
	line := fmt.Sprintf("%s %s", stamp, fmt.Sprintf(format, args...))
	fmt.Println(line)
	if logFile != nil {
		fmt.Fprintln(logFile, line)
	}
}

func kindOrAuto(kind string) string {
	if kind == "" {
		return "авто"
	}
	return kind
}

func findConfig() string {
	candidates := []string{configName}
	if exe, err := os.Executable(); err == nil {
		candidates = append([]string{filepath.Join(filepath.Dir(exe), configName)}, candidates...)
	}
	for _, path := range candidates {
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}
	return configName
}

// firstSecret — первый секрет: для ссылок и совместимости.
func firstSecret(cfg *Config) []byte {
	if len(cfg.Secrets) > 0 {
		return cfg.Secrets[0]
	}
	return make([]byte, 16)
}

func randomToken() string {
	buf := make([]byte, 16)
	_, _ = rand.Read(buf)
	return hex.EncodeToString(buf)
}

// lanIP — адрес машины в локальной сети (для ссылок).
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

// hexSecret — SECRET в виде hex для ссылок.
func hexSecret(secret []byte) string {
	return hex.EncodeToString(secret)
}
