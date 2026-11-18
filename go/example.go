package main

import (
	_ "embed"
	"os"
	"path/filepath"
)

//go:embed tgrelay.example.txt
var exampleConfig string

// ensureConfig: если конфига нет — создать рядом с exe (или в cwd).
// Возвращает путь и признак «только что создан».
func ensureConfig(path string) (string, bool) {
	if _, err := os.Stat(path); err == nil {
		return path, false
	}
	dir := filepath.Dir(path)
	if dir == "" {
		dir = "."
	}
	if err := os.WriteFile(path, []byte(exampleConfig), 0o644); err != nil {
		// каталог рядом с exe может быть только для чтения — пробуем cwd
		alt := filepath.Join(".", configName)
		if err2 := os.WriteFile(alt, []byte(exampleConfig), 0o644); err2 != nil {
			return path, false
		}
		return alt, true
	}
	return path, true
}
