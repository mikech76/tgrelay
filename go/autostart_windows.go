//go:build windows

package main

import (
	"fmt"
	"os"
	"strings"
	"syscall"
	"unsafe"
)

const (
	hkeyCurrentUser     = 0x80000001
	keyQueryValue       = 0x0001
	keySetValue         = 0x0002
	regSZ               = 1
	errorFileNotFound   = 2
	runSubKey           = `Software\Microsoft\Windows\CurrentVersion\Run`
	runValue            = "tgrelay"
	autostartBufferSize = 1024
)

var (
	advapi32          = syscall.NewLazyDLL("advapi32.dll")
	pRegOpenKeyExW    = advapi32.NewProc("RegOpenKeyExW")
	pRegQueryValueExW = advapi32.NewProc("RegQueryValueExW")
	pRegSetValueExW   = advapi32.NewProc("RegSetValueExW")
	pRegDeleteValueW  = advapi32.NewProc("RegDeleteValueW")
	pRegCloseKey      = advapi32.NewProc("RegCloseKey")
)

// autostartValue возвращает путь, прописанный в HKCU\...\Run (если есть).
func autostartValue() (string, bool) {
	return readRunValue(runValue)
}

// readRunValue читает значение из HKCU\...\Run по имени.
func readRunValue(name string) (string, bool) {
	var key syscall.Handle
	r, _, _ := pRegOpenKeyExW.Call(hkeyCurrentUser,
		uintptr(unsafe.Pointer(utf16Ptr(runSubKey))), 0, keyQueryValue,
		uintptr(unsafe.Pointer(&key)))
	if r != 0 {
		return "", false
	}
	defer pRegCloseKey.Call(uintptr(key))

	buf := make([]uint16, autostartBufferSize)
	size := uint32(len(buf) * 2)
	var kind uint32
	r, _, _ = pRegQueryValueExW.Call(uintptr(key),
		uintptr(unsafe.Pointer(utf16Ptr(name))), 0,
		uintptr(unsafe.Pointer(&kind)),
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(unsafe.Pointer(&size)))
	if r == errorFileNotFound || r != 0 {
		return "", false
	}
	return syscall.UTF16ToString(buf), true
}

// deleteRunValue удаляет значение из HKCU\...\Run (если его нет — не ошибка).
func deleteRunValue(name string) {
	var key syscall.Handle
	r, _, _ := pRegOpenKeyExW.Call(hkeyCurrentUser,
		uintptr(unsafe.Pointer(utf16Ptr(runSubKey))), 0, keySetValue,
		uintptr(unsafe.Pointer(&key)))
	if r != 0 {
		return
	}
	defer pRegCloseKey.Call(uintptr(key))
	pRegDeleteValueW.Call(uintptr(key), uintptr(unsafe.Pointer(utf16Ptr(name))))
}

// cleanupLegacyAutostart убирает запись от старой версии программы, если она
// ведёт на тот же tgrelay: иначе при входе в систему запускались два экземпляра.
func cleanupLegacyAutostart() {
	if value, ok := readRunValue("MTProxy"); ok &&
		strings.Contains(strings.ToLower(value), "tgrelay") {
		deleteRunValue("MTProxy")
	}
}

func autostartEnabled() bool {
	_, ok := autostartValue()
	return ok
}

// enableAutostart прописывает текущий exe в автозагрузку пользователя.
func enableAutostart() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	var key syscall.Handle
	r, _, _ := pRegOpenKeyExW.Call(hkeyCurrentUser,
		uintptr(unsafe.Pointer(utf16Ptr(runSubKey))), 0, keySetValue,
		uintptr(unsafe.Pointer(&key)))
	if r != 0 {
		return fmt.Errorf("RegOpenKeyEx: код %d", r)
	}
	defer pRegCloseKey.Call(uintptr(key))

	data, err := syscall.UTF16FromString(`"` + exe + `"`)
	if err != nil {
		return err
	}
	r, _, _ = pRegSetValueExW.Call(uintptr(key),
		uintptr(unsafe.Pointer(utf16Ptr(runValue))), 0, regSZ,
		uintptr(unsafe.Pointer(&data[0])),
		uintptr(len(data)*2))
	if r != 0 {
		return fmt.Errorf("RegSetValueEx: код %d", r)
	}
	return nil
}

// disableAutostart убирает значение (если его нет — не ошибка).
func disableAutostart() {
	deleteRunValue(runValue)
}
