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
	fmt.Println("tgrelay " + version)
	fmt.Print(app.Links())
	fmt.Println()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	logf("остановлено")
}
