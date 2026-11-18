//go:build !windows

package main

import (
	"os"
	"os/exec"
)

// openEditor открывает конфиг в $EDITOR (или nano/vi).
func openEditor(path string) {
	editor := os.Getenv("EDITOR")
	if editor == "" {
		for _, candidate := range []string{"nano", "vi"} {
			if _, err := exec.LookPath(candidate); err == nil {
				editor = candidate
				break
			}
		}
	}
	if editor == "" {
		logf("конфиг: %s (редактор не найден, задайте $EDITOR)", path)
		return
	}
	cmd := exec.Command(editor, path)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	_ = cmd.Run()
}
