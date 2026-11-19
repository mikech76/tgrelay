//go:build windows

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

const (
)

type tray struct {
	hwnd   uintptr
	nid    notifyIconData
	app    *App
	state  string
	menu   uintptr
	ids    map[uint32]func()
	nextID uint32
}

var activeTray *tray

// taskbarCreated — сообщение Windows «панель задач перезапустилась»:
// после перезапуска Explorer иконку нужно добавить заново.
var taskbarCreated uintptr

func newTray(app *App) *tray {
	t := &tray{
		app: app, state: "starting", ids: map[uint32]func(){}, nextID: 100,
	}
	t.init()
	quitUI = t.requestClose
	return t
}

func (t *tray) init() {
	hInst, _, _ := pGetModuleHandleW.Call(0)
	if r, _, _ := pRegisterWindowMessageW.Call(uintptr(unsafe.Pointer(utf16Ptr("TaskbarCreated")))); r != 0 {
		taskbarCreated = r
	}
	className := utf16Ptr(fmt.Sprintf("tgrelayTray%d", time.Now().UnixNano()))

	cursor, _, _ := pLoadCursorW.Call(0, 32512) // IDC_ARROW
	wc := wndClassEx{
		cbSize:        uint32(unsafe.Sizeof(wndClassEx{})),
		lpfnWndProc:   syscall.NewCallback(t.wndProc),
		hInstance:     hInst,
		hCursor:       cursor,
		lpszClassName: className,
	}
	pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc)))

	hwnd, _, _ := pCreateWindowExW.Call(0,
		uintptr(unsafe.Pointer(className)), 0, 0, 0, 0, 0, 0, 0, 0, hInst, 0)
	t.hwnd = hwnd

	t.nid = notifyIconData{
		cbSize:           uint32(unsafe.Sizeof(notifyIconData{})),
		hWnd:             hwnd,
		uID:              1,
		uFlags:           nifMessage | nifIcon | nifTip,
		uCallbackMessage: wmApp + 1,
		hIcon:            trayIcon("starting"),
	}
	copyTip(&t.nid.szTip, tr("tray_tip", version))
	pShellNotifyIconW.Call(nimAdd, uintptr(unsafe.Pointer(&t.nid)))

	pSetTimer.Call(hwnd, 1, 1000, 0)
}

func (t *tray) wndProc(hwnd, msg, wparam, lparam uintptr) uintptr {
	// Колбэк — на потоке окна; меню и иконку трогаем из цикла сообщений
	// (см. run), здесь только быстрые действия.
	if taskbarCreated != 0 && msg == taskbarCreated {
		t.reAdd()
		return 0
	}
	switch msg {
	case wmApp + 1:
		// Клик по иконке приходит «отправленным» сообщением и минует очередь
		// GetMessage, поэтому передаём метку в цикл сообщений: там меню
		// открывается на потоке, к которому привязано окно.
		switch uint32(lparam) {
		case wmRButtonUp, wmContext, wmLButtonUp:
			pPostMessageW.Call(hwnd, wmApp+2, 0, 0)
		}
		return 0
	case wmClose:
		t.removeIcon()
		pDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		pPostQuitMessage.Call(0)
		return 0
	}
	r, _, _ := pDefWindowProcW.Call(hwnd, msg, wparam, lparam)
	return r
}

func (t *tray) run() {
	// Вызывается из runUI, где горутина уже привязана к потоку ОС
	// (runtime.LockOSThread): окно и цикл сообщений Win32 обязаны жить на
	// одном потоке. Иначе Go-планировщик переносит горутину на другой
	// поток — и клики по иконке перестают доходить, хотя сервер работает.
	activeTray = t
	var msg msgStruct
	for {
		r, _, _ := pGetMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0)
		if int32(r) <= 0 {
			break
		}
		if msg.hwnd == t.hwnd {
			switch msg.message {
			case wmApp + 1:
				switch uint32(msg.lParam) {
				case wmRButtonUp, wmContext, wmLButtonUp:
					t.showMenu()
				}
				continue
			case wmApp + 2: // метка от оконной процедуры: открыть меню
				t.showMenu()
				continue
			case wmTimer:
				t.updateIcon()
				continue
			}
		}
		pTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
		pDispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
	}
}

// removeIcon убирает иконку из трея.
func (t *tray) removeIcon() {
	pShellNotifyIconW.Call(nimDelete, uintptr(unsafe.Pointer(&t.nid)))
}

// reAdd возвращает иконку после перезапуска Explorer.
func (t *tray) reAdd() {
	if t.hwnd == 0 {
		return
	}
	t.nid.uFlags = nifMessage | nifIcon | nifTip
	t.nid.hIcon = trayIcon(t.state)
	copyTip(&t.nid.szTip, tr("tray_tip", version))
	pShellNotifyIconW.Call(nimAdd, uintptr(unsafe.Pointer(&t.nid)))
}

// requestClose просит окно закрыться (используется командой tgrelay stop).
func (t *tray) requestClose() bool {
	r, _, _ := pPostMessageW.Call(t.hwnd, wmClose, 0, 0)
	return r != 0
}

func (t *tray) updateIcon() {
	state := t.app.Stats.state(t.app.Pool)
	if state == t.state {
		return
	}
	t.state = state
	t.nid.uFlags = nifIcon
	t.nid.hIcon = trayIcon(state)
	pShellNotifyIconW.Call(nimModify, uintptr(unsafe.Pointer(&t.nid)))
}

// --- меню ------------------------------------------------------------------

func (t *tray) id(action func()) uint32 {
	t.nextID++
	t.ids[t.nextID] = action
	return t.nextID
}

func (t *tray) addItem(menu uintptr, text string, id uint32, icon string,
	enabled, checked bool) {
	var state uint32
	if !enabled {
		state |= mfsGrayed
	}
	if checked {
		state |= mfsChecked
	}

	info := menuItemInfo{
		fMask:      miiString | miiID | miiFType | miiState | miiBitmap,
		fType:      mftString,
		fState:     state,
		wID:        id,
		dwTypeData: utf16Ptr(text),
	}
	if icon != "" {
		info.hbmpItem = menuBitmap(icon)
	}
	info.cbSize = uint32(unsafe.Sizeof(info))
	pInsertMenuItemW.Call(menu, ^uintptr(0), 1, uintptr(unsafe.Pointer(&info)))
}

func (t *tray) addSeparator(menu uintptr) {
	pAppendMenuW.Call(menu, mfSeparator, 0, 0)
}

func (t *tray) addSubmenu(menu uintptr, text, icon string) uintptr {
	sub, _, _ := pCreatePopupMenu.Call()
	info := menuItemInfo{
		fMask:      miiString | miiFType | miiSub | miiBitmap,
		fType:      mftString,
		hSubMenu:   sub,
		dwTypeData: utf16Ptr(text),
	}
	if icon != "" {
		info.hbmpItem = menuBitmap(icon)
	}
	info.cbSize = uint32(unsafe.Sizeof(info))
	pInsertMenuItemW.Call(menu, ^uintptr(0), 1, uintptr(unsafe.Pointer(&info)))
	return sub
}

func (t *tray) showMenu() {
	logf("меню: открываю")
	t.ids = map[uint32]func(){}
	if t.menu != 0 {
		pDestroyMenu.Call(t.menu)
	}
	menu, _, _ := pCreatePopupMenu.Call()
	t.menu = menu

	snap := t.app.Stats.Snapshot()
	alive, total := t.app.Pool.Stats()

	protocols := t.protocolLine()
	t.addItem(menu, "tgrelay "+version, 0, "", false, false)
	t.addItem(menu, protocols, 0, "", false, false)
	if t.app.Pool.Direct() {
		t.addItem(menu, fmt.Sprintf(tr("direct_mode"), snap.Conns), 0, "", false, false)
	} else {
		t.addItem(menu, fmt.Sprintf(tr("proxies"), alive, total, snap.Conns), 0, "", false, false)
	}
	t.addItem(menu, fmt.Sprintf(tr("speed"), human(snap.DownRate), human(snap.UpRate)), 0, "", false, false)
	t.addItem(menu, fmt.Sprintf(tr("total"), human(float64(snap.Down)), human(float64(snap.Up))), 0, "", false, false)
	t.addSeparator(menu)

	localHost := lanIP()
	external := t.app.Cfg.External

	if t.app.Cfg.MTPort != 0 {
		secret := hexSecret(firstSecret(t.app.Cfg))
		link := func(host string) string {
			return mtprotoLink(host, t.app.Cfg.MTPort, secret)
		}
		sub := t.addSubmenu(menu, "MTProto :"+strconv.Itoa(t.app.Cfg.MTPort), "")
		t.addLinkItems(sub, localHost, external, link, "MTProto")
	}
	if t.app.Cfg.SocksPort != 0 {
		socksHost := t.app.Cfg.SocksHost
		if socksHost == "" || socksHost == "0.0.0.0" {
			socksHost = localHost
		}
		link := func(host string) string {
			return socksLink(host, t.app.Cfg.SocksPort, t.app.Cfg.User, t.app.Cfg.Pass)
		}
		sub := t.addSubmenu(menu, "SOCKS5 :"+strconv.Itoa(t.app.Cfg.SocksPort), "")
		t.addLinkItems(sub, socksHost, external, link, "SOCKS5")
	}

	t.addSeparator(menu)
	settings := t.addSubmenu(menu, tr("settings"), "menu_settings")
	t.addItem(settings, tr("edit_config"), t.id(t.openSettings), "menu_edit", true, false)
	t.addItem(settings, tr("autostart"), t.id(t.toggleAutostart), "", true,
		autostartEnabled())
	t.addItem(settings, tr("reload"), t.id(t.reloadConfig), "menu_reload", true, false)

	langMenu := t.addSubmenu(menu, tr("language"), "menu_language")
	t.addItem(langMenu, checkMark("English", lang() == "en"),
		t.id(func() { t.setLang("en") }), "menu_lang_en", true, false)
	t.addItem(langMenu, checkMark("Русский", lang() == "ru"),
		t.id(func() { t.setLang("ru") }), "menu_lang_ru", true, false)

	t.addItem(menu, tr("docs"), t.id(t.openDocs), "menu_docs", true, false)
	t.addItem(menu, tr("about"), t.id(t.showAbout), "menu_about", true, false)
	t.addSeparator(menu)
	t.addItem(menu, tr("exit"), t.id(t.exit), "menu_exit", true, false)

	// SetForegroundWindow на скрытом окне не срабатывает: меню получается
	// без «хозяина» и может зависнуть невидимым. Popup сам захватывает мышь,
	// поэтому клик мимо него меню и так закрывает.
	var pt point
	pGetCursorPos.Call(uintptr(unsafe.Pointer(&pt)))
	cmd, _, _ := pTrackPopupMenuEx.Call(menu,
		tpmReturnCmd|tpmRightAlign, uintptr(pt.X), uintptr(pt.Y), t.hwnd, 0)
	pPostMessageW.Call(t.hwnd, 0, 0, 0)
	logf("меню: выбрано %d", cmd)
	if cmd > 0 {
		if action, ok := t.ids[uint32(cmd)]; ok {
			action()
		}
	}
}

func (t *tray) addLinkItems(menu uintptr, localHost, external string,
	link func(string) string, name string) {
	host := localHost
	t.addItem(menu, fmt.Sprintf(tr("copy_link"), host),
		t.id(func() { t.copyLink(link(host), name) }), "copy_mtproto", true, false)
	t.addItem(menu, fmt.Sprintf(tr("qr_link"), host),
		t.id(func() { showQR(link(host)) }), "qr_mtproto", true, false)
	if external != "" {
		host = external
		t.addItem(menu, fmt.Sprintf(tr("copy_link"), host),
			t.id(func() { t.copyLink(link(host), name) }), "copy_mtproto", true, false)
		t.addItem(menu, fmt.Sprintf(tr("qr_link"), host),
			t.id(func() { showQR(link(host)) }), "qr_mtproto", true, false)
	}
}

func (t *tray) protocolLine() string {
	var parts []string
	if t.app.Cfg.MTPort != 0 {
		parts = append(parts, "MTProto :"+strconv.Itoa(t.app.Cfg.MTPort))
	}
	if t.app.Cfg.SocksPort != 0 {
		parts = append(parts, "SOCKS5 :"+strconv.Itoa(t.app.Cfg.SocksPort))
	}
	out := ""
	for i, part := range parts {
		if i > 0 {
			out += "   ·   "
		}
		out += part
	}
	return out
}

// --- действия --------------------------------------------------------------

func (t *tray) copyLink(link, name string) {
	setClipboard(link)
	t.balloon(fmt.Sprintf(tr("copied"), name))
}

func (t *tray) balloon(text string) {
	t.nid.uFlags = 0x00000010 // NIF_INFO
	t.nid.dwInfoFlags = 0x00000001
	t.nid.uVersion = 0
	copyTip(&t.nid.szTip, tr("tray_tip", version))
	copyInfo(t.nid.szInfo[:], text)
	copyInfo(t.nid.szInfoTitle[:], "tgrelay")
	pShellNotifyIconW.Call(nimModify, uintptr(unsafe.Pointer(&t.nid)))
}

func (t *tray) setLang(code string) {
	setLang(code)
	writeConfigValue(t.app.Path, "LANG", code)
	copyTip(&t.nid.szTip, tr("tray_tip", version))
	// меню перечитывается при следующем открытии
}

func (t *tray) openDocs() {
	url := repoURL + "/blob/main/go/README.md"
	if lang() == "ru" {
		url = repoURL + "/blob/main/go/README.ru.md"
	}
	shellExecute("open", url)
}

func (t *tray) showAbout() {
	messageBox(fmt.Sprintf(tr("about_text"), version, repoURL), tr("about_title"), 0x40)
}

func (t *tray) openSettings() {
	go watchSettings(t.app.Path)
}

func (t *tray) toggleAutostart() {
	if autostartEnabled() {
		disableAutostart()
		t.balloon(tr("autostart_off"))
	} else {
		if err := enableAutostart(); err != nil {
			messageBox("Autostart: "+err.Error(), "tgrelay", 0x10)
			return
		}
		t.balloon(tr("autostart_on"))
	}
}

func (t *tray) reloadConfig() {
	t.balloon(tr("reloading"))
	go func() {
		if err := t.app.Reload(); err != nil {
			messageBox("Reload: "+err.Error(), "tgrelay", 0x10)
		}
	}()
}

func (t *tray) exit() {
	t.removeIcon()
	pDestroyWindow.Call(t.hwnd)
}

func copyInfo(dst []uint16, text string) {
	src := u16(text)
	for i := range dst {
		if i < len(src) && i < len(dst)-1 {
			dst[i] = src[i]
		} else {
			dst[i] = 0
		}
	}
}

var restarting atomic.Bool

// watchSettings открывает Блокнот и перезапускает программу, если файл изменился.
func watchSettings(path string) {
	before := fileModTime(path)
	cmd := launchNotepad(path)
	if cmd == nil {
		return
	}
	started := time.Now()
	_ = cmd.Wait()
	quick := time.Since(started) < 2*time.Second

	if fileModTime(path) != before {
		restartSelf()
		return
	}
	if !quick {
		return
	}
	deadline := time.Now().Add(30 * time.Minute)
	for time.Now().Before(deadline) {
		time.Sleep(time.Second)
		if fileModTime(path) == before {
			continue
		}
		settled := fileModTime(path)
		for time.Now().Before(deadline) {
			time.Sleep(time.Second)
			current := fileModTime(path)
			if current == settled {
				restartSelf()
				return
			}
			settled = current
		}
	}
}

func fileModTime(path string) int64 {
	info, err := os.Stat(path)
	if err != nil {
		return 0
	}
	return info.ModTime().UnixNano()
}

func restartSelf() {
	if !restarting.CompareAndSwap(false, true) {
		return
	}
	time.Sleep(500 * time.Millisecond)
	exe, err := os.Executable()
	if err != nil {
		return
	}
	env := append(os.Environ(), "TGRELAY_HANDOFF=1")
	cmd := &execSpec{path: exe, env: env, dir: filepath.Dir(exe)}
	startDetached(cmd)
	os.Exit(0)
}

// checkMark добавляет галочку к тексту: у пунктов с картинкой служебная
// колонка занята иконкой, и системная галочка не видна.
func checkMark(text string, checked bool) string {
	if checked {
		return text + "  ✓"
	}
	return text
}
