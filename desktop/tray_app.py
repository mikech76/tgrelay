import io
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser

import pystray
import pyperclip
import qrcode
from PIL import Image, ImageDraw, ImageFont

import appdir
import i18n
import menu_icons
import socks5_to_http
import status
from i18n import t
from proxy_pool import (config, external_host, lan_ip, port_value,
                        save_env_value)

VERSION = '1.2'
REPO_URL = 'https://github.com/mikech76/tgrelay'
DOCS = {
    'en': REPO_URL + '/blob/main/desktop/README.md',
    'ru': REPO_URL + '/blob/main/desktop/README.ru.md',
}


def _make_icon():
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(0, 168, 132, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "M", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2 - 2),
              "M", fill="white", font=font)
    return img


def mtproto_link(host=None):
    port = port_value('PROXY_PORT', 55055)
    secret = config.get('SECRET', '').replace(' ', '').replace('-', '')
    return f"tg://proxy?server={host or lan_ip()}&port={port}&secret={secret}"


class QRWindow:
    def __init__(self, link, title="MTProxy"):
        self.link = link
        self.title = title

    def show(self):
        qr = qrcode.make(self.link)
        root = tk.Tk()
        root.title(self.title)
        root.resizable(False, False)

        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        buf.seek(0)

        photo = tk.PhotoImage(data=buf.getvalue())
        tk.Label(root, image=photo).pack(padx=10, pady=10)
        tk.Label(root, text=self.link, wraplength=280,
                 fg="gray").pack(padx=10, pady=(0, 10))
        root.mainloop()


def about_window():
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        t('about_title'),
        t('about_text', version=VERSION, repo=REPO_URL),
        parent=root)
    root.destroy()


def _socks_local_host():
    """Адрес, по которому SOCKS5 доступен в локальной сети."""
    bind = (socks5_to_http.load_config().get('SOCKS_HOST') or '').strip()
    if bind in ('', '0.0.0.0', '::'):
        return lan_ip()
    return bind


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _restart():
    """Запустить новый экземпляр и выйти.

    Новый процесс стартует с TGRELAY_HANDOFF=1 и ждёт освобождения
    блокировки/портов, поэтому «адрес занят» не возникает.
    """
    env = dict(os.environ, TGRELAY_HANDOFF='1')
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'main.py')]
    try:
        subprocess.Popen(cmd, env=env, close_fds=True)
    except OSError:
        return
    time.sleep(0.2)
    os._exit(0)


def _label(key):
    """Текст пункта меню вычисляется при каждой отрисовке — язык меняется
    на лету без пересборки меню. Иконка рисуется отдельно (menu_icons)."""
    return lambda item: t(key)


# --- строки состояния ------------------------------------------------------

def _status_protocols(item):
    """Какие протоколы подняты и на каких портах."""
    parts = []
    mt = port_value('PROXY_PORT', 55055)
    socks = port_value('SOCKS_PORT', 55056)
    if mt is not None:
        parts.append(f'MTProto :{mt}')
    if socks is not None:
        parts.append(f'SOCKS5 :{socks}')
    return '   ·   '.join(parts)


def _status_proxies(item):
    snap = status.snapshot()
    return t('status_proxies',
             alive=snap['proxies_alive'],
             total=snap['proxies_total'],
             conns=snap['conns'])


def _status_speed(item):
    snap = status.snapshot()
    return t('status_speed',
             down=status.human(snap['down_rate']),
             up=status.human(snap['up_rate']))


def _status_total(item):
    snap = status.snapshot()
    return t('status_total',
             down=status.human(snap['down_total']),
             up=status.human(snap['up_total']))


def _install_menu_refresh():
    """Пересобирать меню перед показом: счётчики всегда свежие.

    pystray строит Win32-меню один раз, а значения берёт из callables
    только при обновлении. Перед показом меню его и обновляем.
    """
    if sys.platform != 'win32':
        return
    try:
        import pystray._win32 as backend
    except Exception:
        return
    original = backend.Icon._on_notify
    if getattr(original, '_tgrelay_fresh', False):
        return

    def patched(self, wparam, lparam):
        try:
            if lparam == backend.win32.WM_RBUTTONUP:
                self.update_menu()
        except Exception:
            pass
        return original(self, wparam, lparam)

    patched._tgrelay_fresh = True
    backend.Icon._on_notify = patched


_install_menu_refresh()


class TrayApp:
    def __init__(self):
        self.icon = None
        self._item_keys = {}          # id(MenuItem) -> ключ иконки

    def _item(self, key, action, visible=True, **kwargs):
        """Пункт меню с цветной иконкой (текст берётся из i18n)."""
        entry = pystray.MenuItem(_label(key), action, visible=visible, **kwargs)
        self._item_keys[id(entry)] = key
        return entry

    def _action(self, icon_key, text, action):
        """Пункт с произвольным текстом (callable) и общей иконкой."""
        entry = pystray.MenuItem(text, action)
        self._item_keys[id(entry)] = icon_key
        return entry

    def _protocol_menu(self, title, copy_icon, qr_icon, local_host, link_fn,
                       name):
        """Подменю протокола: локальная ссылка и внешняя (если настроена)."""
        entries = []

        def add(icon, text_key, host_fn, kind):
            text = lambda item: t(text_key, host=host_fn())
            if kind == 'copy':
                action = lambda: self._copy(link_fn(host_fn()), name)
            else:
                action = lambda: self._qr(link_fn(host_fn()), name + ' — QR')
            entries.append(self._action(icon, text, action))

        add(copy_icon, 'copy_link_at', local_host, 'copy')
        add(qr_icon, 'qr_link_at', local_host, 'qr')
        if external_host():
            add(copy_icon, 'copy_link_at', external_host, 'copy')
            add(qr_icon, 'qr_link_at', external_host, 'qr')

        return pystray.MenuItem(title, pystray.Menu(*entries))

    def _build_menu(self):
        item = pystray.MenuItem
        mt_port = port_value('PROXY_PORT', 55055)
        socks_port = port_value('SOCKS_PORT', 55056)

        def label(text):
            """Строка состояния: серая, некликабельная."""
            return item(text, None, enabled=False)

        entries = [
            label(_status_protocols),
            label(_status_proxies),
            label(_status_speed),
            label(_status_total),
            pystray.Menu.SEPARATOR,
        ]

        if mt_port is not None:
            entries.append(self._protocol_menu(
                f'MTProto :{mt_port}', 'copy_mtproto', 'qr_mtproto',
                lan_ip, mtproto_link, 'MTProto'))
        if socks_port is not None:
            entries.append(self._protocol_menu(
                f'SOCKS5 :{socks_port}', 'copy_socks_wifi', 'qr_socks_wifi',
                _socks_local_host,
                lambda host: socks5_to_http.socks_link(port=socks_port,
                                                       host=host),
                'SOCKS5'))

        entries += [
            pystray.Menu.SEPARATOR,
            self._item('menu_settings', self._open_settings),
            self._item('menu_language', pystray.Menu(
                item('English', lambda: self._set_lang('en'),
                     checked=lambda _: i18n.lang() == 'en', radio=True),
                item('Русский', lambda: self._set_lang('ru'),
                     checked=lambda _: i18n.lang() == 'ru', radio=True),
            )),
            self._item('menu_docs', self._open_docs),
            self._item('menu_about', self._show_about),
            pystray.Menu.SEPARATOR,
            self._item('menu_exit', self._on_exit),
        ]
        menu = pystray.Menu(*entries)
        menu_icons.install(self._item_keys)
        return menu

    def run(self):
        self.icon = pystray.Icon("tgrelay", _make_icon(),
                                 t('tray_tooltip'), self._build_menu())
        self.icon.run()

    def _set_lang(self, value):
        i18n.set_lang(value)
        try:
            save_env_value('LANG', value)
        except OSError:
            pass
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _open_docs(self):
        webbrowser.open(DOCS.get(i18n.lang(), DOCS['en']))

    # --- настройки ---------------------------------------------------------
    def _open_settings(self):
        """Открыть конфиг в Блокноте и применить изменения после правки."""
        path = appdir.config_path()
        before = _mtime(path)
        try:
            proc = subprocess.Popen(['notepad.exe', path])
        except OSError:
            try:
                os.startfile(path)
            except OSError as e:
                self._notify(t('copy_failed', err=e))
                return
            return

        threading.Thread(target=self._watch_settings,
                         args=(path, before, proc), daemon=True).start()

    def _watch_settings(self, path, before, proc):
        """Ждём закрытия Блокнота и перезапускаемся, если файл изменился.

        На Windows Блокнот может отдать файл уже открытому окну (вкладкой):
        тогда процесс завершается сразу, а правка появится позже — такой
        случай отслеживаем по времени изменения файла.
        """
        started = time.monotonic()
        proc.wait()
        quick = time.monotonic() - started < 2.0

        if _mtime(path) != before:
            self._restart_after_save()
            return
        if not quick:
            return                       # открылся своим окном, правок нет

        deadline = time.monotonic() + 1800        # полчаса на правку вкладки
        while time.monotonic() < deadline:
            time.sleep(1.0)
            if _mtime(path) == before:
                continue
            # даём файлу «успокоиться»: человек может сохранять несколько раз
            settled = _mtime(path)
            while time.monotonic() < deadline:
                time.sleep(1.0)
                current = _mtime(path)
                if current == settled:
                    self._restart_after_save()
                    return
                settled = current

    def _restart_after_save(self):
        time.sleep(0.5)
        self._notify(t('settings_saved'))
        _restart()

    def _notify(self, message):
        try:
            self.icon.notify(message, 'tgrelay')
        except Exception:
            pass

    def _show_about(self):
        threading.Thread(target=about_window, daemon=True).start()

    def _copy(self, link, name):
        try:
            pyperclip.copy(link)
            self.icon.notify(link, t('copied', name=name))
        except Exception as e:
            self.icon.notify(t('copy_failed', err=e), name)

    def _qr(self, link, title):
        threading.Thread(target=QRWindow(link, title).show, daemon=True).start()

    def _on_exit(self, icon, item):
        icon.stop()
        os._exit(0)
