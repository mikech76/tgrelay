package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

const (
	configName = "tgrelay.txt"
	repoURL    = "https://github.com/mikech76/tgrelay"
	version    = "1.2"
)

var debugFlag = flag.Bool("debug", false, "подробный лог")

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

// loadApp читает конфиг и собирает пул; используется и треем, и headless.
func loadApp(configPath string) (*Config, *Pool, *Stats, string, error) {
	path := configPath
	if path == "" {
		path = findConfig()
	}
	cfg, err := LoadConfig(path)
	if err != nil {
		return nil, nil, nil, path, fmt.Errorf("не читается %s: %w", path, err)
	}
	if cfg.MTPort == 0 && cfg.SocksPort == 0 {
		return nil, nil, nil, path, fmt.Errorf("оба протокола выключены в tgrelay.txt — запускать нечего")
	}
	if len(cfg.Proxies) == 0 {
		return nil, nil, nil, path, fmt.Errorf("в tgrelay.txt нет ни одного прокси (PROXY=)")
	}
	if cfg.Lang != "" {
		setLang(cfg.Lang)
	}
	stats := NewStats()
	pool := NewPool(cfg.Proxies, cfg.Hosts)
	go pool.HealthLoop(context.Background(), 60*time.Second)
	return cfg, pool, stats, path, nil
}

// hexSecret — SECRET в виде hex для ссылок.
func hexSecret(secret []byte) string {
	const digits = "0123456789abcdef"
	out := make([]byte, len(secret)*2)
	for i, b := range secret {
		out[i*2] = digits[b>>4]
		out[i*2+1] = digits[b&0x0f]
	}
	return string(out)
}
