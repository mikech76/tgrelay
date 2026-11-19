//go:build !windows

package main

import (
	"os"
	"strings"
)

// systemLang — язык системы по переменным окружения (ru* → ru, иначе en).
func systemLang() string {
	for _, key := range []string{"LC_ALL", "LC_MESSAGES", "LANG"} {
		if strings.HasPrefix(strings.ToLower(os.Getenv(key)), "ru") {
			return "ru"
		}
	}
	return "en"
}
