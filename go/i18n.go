package main

import (
	"fmt"
	"strconv"
	"strings"
	"sync"
)

var (
	langMu   sync.RWMutex
	langCode = "en"
)

func lang() string {
	langMu.RLock()
	defer langMu.RUnlock()
	return langCode
}

func setLang(code string) {
	langMu.Lock()
	if code == "ru" || code == "en" {
		langCode = code
	}
	langMu.Unlock()
}

type pair struct{ en, ru string }

var texts = map[string]pair{
	"settings":    {"Settings", "Настройки"},
	"edit_config": {"Edit config file", "Редактировать конфиг"},
	"autostart":   {"Run at startup", "Автозагрузка"},
	"reload":      {"Reload config", "Перечитать конфиг"},
	"autostart_on":  {"Autostart enabled", "Автозагрузка включена"},
	"autostart_off": {"Autostart disabled", "Автозагрузка выключена"},
	"reloading":     {"Reloading config — all proxies and ports restart…",
	                  "Перечитываю конфиг — прокси и порты перезапускаются…"},
	"language":    {"Language", "Язык"},
	"docs":        {"Documentation", "Документация"},
	"about":       {"About", "О программе"},
	"exit":        {"Exit", "Выход"},
	"copy_link":   {"Copy link — %s", "Копировать ссылку — %s"},
	"qr_link":     {"Show QR code — %s", "Показать QR-код — %s"},
	"proxies":     {"%d/%d proxies · %d connections", "Прокси %d/%d · соединений %d"},
	"speed":       {"↓ %s/s    ↑ %s/s", "↓ %s/с    ↑ %s/с"},
	"total":       {"since start ↓ %s    ↑ %s", "всего ↓ %s    ↑ %s"},
	"copied":      {"%s link copied", "Ссылка %s скопирована"},
	"copy_failed": {"Could not copy: %v", "Не удалось скопировать: %v"},
	"about_title": {"About tgrelay", "О программе"},
	"about_text": {"tgrelay %s\n\nMTProto + SOCKS5 relay over your own proxy pool.\n\n%s",
		"tgrelay %s\n\nMTProto + SOCKS5 через ваш пул прокси.\n\n%s"},
	"tray_tip":       {"tgrelay: MTProto + SOCKS5", "tgrelay: MTProto + SOCKS5"},
	"already_running": {"tgrelay is already running.", "tgrelay уже запущен."},
	"already_title":   {"tgrelay", "tgrelay"},
	"settings_saved":  {"Settings applied — restarting…", "Настройки применены — перезапуск…"},
	"qr_title":        {"tgrelay — QR", "tgrelay — QR"},
}

func tr(key string, args ...any) string {
	item, ok := texts[key]
	if !ok {
		return key
	}
	text := item.en
	if lang() == "ru" {
		text = item.ru
	}
	if len(args) == 0 {
		return text
	}
	return fmt.Sprintf(text, args...)
}

// formatFloat — без локали, чтобы не тянуть x/text.
func formatFloat(v float64, digits int) string {
	return strconv.FormatFloat(v, 'f', digits, 64)
}

func replaceComma(s string) string {
	return strings.ReplaceAll(s, ".", ",")
}
