//go:build windows

package main

import (
	"os/exec"
	"syscall"
	"unsafe"
)

// setClipboard кладёт текст в буфер обмена (CF_UNICODETEXT).
func setClipboard(text string) {
	if r, _, _ := pOpenClipboard.Call(0); r == 0 {
		return
	}
	defer pCloseClipboard.Call()
	pEmptyClipboard.Call()

	utf, err := syscall.UTF16FromString(text)
	if err != nil {
		return
	}
	size := uintptr(len(utf) * 2)
	h, _, _ := pGlobalAlloc.Call(0x0042, size) // GMEM_MOVEABLE|GMEM_ZEROINIT
	if h == 0 {
		return
	}
	ptr, _, _ := pGlobalLock.Call(h)
	if ptr == 0 {
		return
	}
	dst := unsafe.Slice((*uint16)(unsafe.Pointer(ptr)), len(utf))
	copy(dst, utf)
	pGlobalUnlock.Call(h)
	pSetClipboardData.Call(13, h) // CF_UNICODETEXT
}

func launchNotepad(path string) *exec.Cmd {
	cmd := exec.Command("notepad.exe", path)
	if err := cmd.Start(); err != nil {
		shellExecute("open", path)
		return nil
	}
	return cmd
}

type execSpec struct {
	path string
	env  []string
	dir  string
}

func startDetached(spec *execSpec) {
	cmd := exec.Command(spec.path)
	cmd.Env = spec.env
	cmd.Dir = spec.dir
	_ = cmd.Start()
}
