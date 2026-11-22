//go:build !windows

package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"
)

// takeOver: на Linux единственный экземпляр не ограничиваем.
func takeOver(headless bool) bool { return true }

// showError сообщает об ошибке в консоль (на Windows — окном).
func showError(text string) { fmt.Fprintln(os.Stderr, text) }

// runUI без трея: печатаем ссылки и ждём SIGINT/SIGTERM.
func runUI(app *App, headless bool) {	fmt.Println("tgrelay " + version)
	fmt.Print(app.Links())
	fmt.Println()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	<-sig
	logf("остановлено")
}
