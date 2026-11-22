//go:build windows

package main

import (
	"fmt"
	"os"
	"runtime"
	"strconv"
	"syscall"
	"time"
	"unsafe"
)

// runUI запускает трей (или ждёт сигнала в режиме --headless).
func runUI(app *App, headless bool) {
	if headless {
		printLinks(app)
		select {}
	}
	// Всё, что связано с окном и меню, должно жить на одном потоке ОС:
	// создание окна, цикл сообщений и показ меню. Иначе Go-планировщик
	// разносит их по разным потокам, и клики по иконке теряются.
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	cleanupLegacyAutostart()
	t := newTray(app)
	logf("трей: окно создано")
	printLinks(app)
	logf("трей: вход в цикл сообщений")
	t.run()
	logf("трей: цикл завершён")
}

func printLinks(app *App) {
	fmt.Print(app.Links())
	fmt.Println()
}

var lockHandle uintptr

// takeOver занимает слот единственного экземпляра до запуска серверов.
// При перезапуске из меню новая копия ждёт, пока старая отпустит порты.
func takeOver(headless bool) bool {
	if headless {
		return true
	}
	return singleInstance()
}

// showError показывает ошибку окном: у GUI-сборки нет консоли, и без этого
// неудачный запуск (например, битый конфиг) выглядел бы как «программа закрылась».
func showError(text string) {
	messageBox(text, "tgrelay", 0x10)
}

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
