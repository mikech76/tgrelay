//go:build windows

package main

// openEditor открывает конфиг в Блокноте.
func openEditor(path string) {
	shellExecute("open", path)
}
