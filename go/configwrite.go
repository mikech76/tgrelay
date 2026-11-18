package main

import (
	"os"
	"strings"
)

// writeConfigValue меняет KEY=value в конфиге, сохраняя комментарии.
func writeConfigValue(path, key, value string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	lines := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n")
	found := false
	for i, line := range lines {
		trim := strings.TrimSpace(line)
		if trim == "" || strings.HasPrefix(trim, "#") || !strings.Contains(trim, "=") {
			continue
		}
		if strings.TrimSpace(strings.SplitN(trim, "=", 2)[0]) != key {
			continue
		}
		lines[i] = key + "=" + value
		found = true
		break
	}
	if !found {
		lines = append(lines, key+"="+value)
	}
	_ = os.WriteFile(path, []byte(strings.Join(lines, "\n")), 0o644)
}
