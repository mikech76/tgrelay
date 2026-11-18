//go:build windows

package main

import (
	"syscall"
	"unsafe"
)

// Минимальные обёртки над Win32 — только то, что нужно трею и меню.
var (
	user32   = syscall.NewLazyDLL("user32.dll")
	shell32  = syscall.NewLazyDLL("shell32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	gdi32    = syscall.NewLazyDLL("gdi32.dll")

	pRegisterClassExW    = user32.NewProc("RegisterClassExW")
	pCreateWindowExW     = user32.NewProc("CreateWindowExW")
	pDefWindowProcW      = user32.NewProc("DefWindowProcW")
	pDestroyWindow       = user32.NewProc("DestroyWindow")
	pGetMessageW         = user32.NewProc("GetMessageW")
	pTranslateMessage    = user32.NewProc("TranslateMessage")
	pDispatchMessageW    = user32.NewProc("DispatchMessageW")
	pPostQuitMessage     = user32.NewProc("PostQuitMessage")
	pPostMessageW        = user32.NewProc("PostMessageW")
	pCreatePopupMenu     = user32.NewProc("CreatePopupMenu")
	pAppendMenuW         = user32.NewProc("AppendMenuW")
	pInsertMenuItemW     = user32.NewProc("InsertMenuItemW")
	pDestroyMenu         = user32.NewProc("DestroyMenu")
	pTrackPopupMenuEx    = user32.NewProc("TrackPopupMenuEx")
	pSetForegroundWindow = user32.NewProc("SetForegroundWindow")
	pGetCursorPos        = user32.NewProc("GetCursorPos")
	pCreateIconIndirect  = user32.NewProc("CreateIconIndirect")
	pDestroyIcon         = user32.NewProc("DestroyIcon")
	pMessageBoxW         = user32.NewProc("MessageBoxW")
	pSetTimer            = user32.NewProc("SetTimer")
	pKillTimer           = user32.NewProc("KillTimer")
	pLoadCursorW         = user32.NewProc("LoadCursorW")
	pGetModuleHandleW    = kernel32.NewProc("GetModuleHandleW")
	pCreateMutexW        = kernel32.NewProc("CreateMutexW")
	pShellNotifyIconW    = shell32.NewProc("Shell_NotifyIconW")
	pShellExecuteW       = shell32.NewProc("ShellExecuteW")
	pCreateDIBSection    = gdi32.NewProc("CreateDIBSection")
	pCreateBitmap        = gdi32.NewProc("CreateBitmap")
	pDeleteObject        = gdi32.NewProc("DeleteObject")
	pOpenClipboard       = user32.NewProc("OpenClipboard")
	pCloseClipboard      = user32.NewProc("CloseClipboard")
	pEmptyClipboard      = user32.NewProc("EmptyClipboard")
	pSetClipboardData    = user32.NewProc("SetClipboardData")
	pGlobalAlloc         = kernel32.NewProc("GlobalAlloc")
	pGlobalLock          = kernel32.NewProc("GlobalLock")
	pGlobalUnlock        = kernel32.NewProc("GlobalUnlock")
)

const (
	wmDestroy   = 0x0002
	wmCommand   = 0x0111
	wmTimer     = 0x0113
	wmApp       = 0x8000
	wmRButtonUp = 0x0205
	wmLButtonUp = 0x0202
	wmContext   = 0x007B

	nimAdd    = 0x00000000
	nimModify = 0x00000001
	nimDelete = 0x00000002

	nifMessage = 0x00000001
	nifIcon    = 0x00000002
	nifTip     = 0x00000004

	mfString    = 0x00000000
	mfPopup     = 0x00000010
	mfSeparator = 0x00000800
	mfGrayed    = 0x00000001
	mfChecked   = 0x00000008
	mfByCommand = 0x00000000

	tpmLeftAlign  = 0x0000
	tpmRightAlign = 0x0008
	tpmReturnCmd  = 0x0100

	miiBitmap = 0x00000080 // MIIM_BITMAP
	miiString = 0x00000040 // MIIM_STRING
	miiID     = 0x00000002 // MIIM_ID
	miiFType  = 0x00000100 // MIIM_FTYPE
	miiState  = 0x00000001 // MIIM_STATE
	miiSub    = 0x00000004 // MIIM_SUBMENU

	mftString    = 0x00000000 // MFT_STRING
	mfsGrayed    = 0x00000003 // MFS_GRAYED
	mfsChecked   = 0x00000008 // MFS_CHECKED
)

type point struct{ X, Y int32 }

type msgStruct struct {
	hwnd    uintptr
	message uint32
	wParam  uintptr
	lParam  uintptr
	time    uint32
	pt      point
}

type wndClassEx struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     uintptr
	hIcon         uintptr
	hCursor       uintptr
	hbrBackground uintptr
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       uintptr
}

type notifyIconData struct {
	cbSize           uint32
	hWnd             uintptr
	uID              uint32
	uFlags           uint32
	uCallbackMessage uint32
	hIcon            uintptr
	szTip            [128]uint16
	dwState          uint32
	dwStateMask      uint32
	szInfo           [256]uint16
	uVersion         uint32
	szInfoTitle      [64]uint16
	dwInfoFlags      uint32
	guidItem         [16]byte
	hBalloonIcon     uintptr
}

type menuItemInfo struct {
	cbSize        uint32
	fMask         uint32
	fType         uint32
	fState        uint32
	wID           uint32
	hSubMenu      uintptr
	hbmpChecked   uintptr
	hbmpUnchecked uintptr
	dwItemData    uintptr
	dwTypeData    *uint16
	cch           uint32
	hbmpItem      uintptr
}

type iconInfo struct {
	fIcon    int32
	xHotspot uint32
	yHotspot uint32
	hbmMask  uintptr
	hbmColor uintptr
}

type bitmapInfoHeader struct {
	biSize          uint32
	biWidth         int32
	biHeight        int32
	biPlanes        uint16
	biBitCount      uint16
	biCompression   uint32
	biSizeImage     uint32
	biXPelsPerMeter int32
	biYPelsPerMeter int32
	biClrUsed       uint32
	biClrImportant  uint32
}

type bitmapInfo struct {
	bmiHeader bitmapInfoHeader
	bmiColors [3]uint32
}

func utf16Ptr(s string) *uint16 {
	p, err := syscall.UTF16PtrFromString(s)
	if err != nil {
		return nil
	}
	return p
}

func u16(s string) []uint16 {
	out, _ := syscall.UTF16FromString(s)
	return out
}

func copyTip(dst *[128]uint16, text string) {
	src := u16(text)
	n := len(src)
	if n > len(dst) {
		n = len(dst)
	}
	for i := 0; i < len(dst); i++ {
		if i < n {
			dst[i] = src[i]
		} else {
			dst[i] = 0
		}
	}
}

func messageBox(text, title string, flags uint32) int {
	r, _, _ := pMessageBoxW.Call(0,
		uintptr(unsafe.Pointer(utf16Ptr(text))),
		uintptr(unsafe.Pointer(utf16Ptr(title))),
		uintptr(flags))
	return int(r)
}

func shellExecute(op, file string) {
	pShellExecuteW.Call(0,
		uintptr(unsafe.Pointer(utf16Ptr(op))),
		uintptr(unsafe.Pointer(utf16Ptr(file))),
		0, 0, 1) // SW_SHOWNORMAL
}
