//go:build !windows

package main

import "fmt"

func runSelftest(kind, path string, cfg *Config) {
	logf("selftest доступен только на Windows")
}

func showFirstRun(path string) {
	fmt.Printf("Создан конфиг: %s\nВпишите строки PROXY= и запустите снова.\n", path)
}
