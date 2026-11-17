import io
import os
import threading
import tkinter as tk
import webbrowser

import pystray
import pyperclip
import qrcode
from PIL import Image, ImageDraw, ImageFont

import i18n
import menu_icons
import socks5_to_http
from i18n import t
from proxy_pool import config, get_external_ip, save_env_value

VERSION = '1.1'
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


def mtproto_link():
    ip = get_external_ip()
    port = config.get('PROXY_PORT', '1985')
    secret = config.get('SECRET', '').replace(' ', '').replace('-', '')
    return f"tg://proxy?server={ip}&port={port}&secret={secret}"


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


def socks_link_outside():
    """Та же ссылка, но с внешним адресом (для мобильной сети)."""
    return socks5_to_http.socks_link(host=get_external_ip())


def _label(key):
    """Текст пункта меню вычисляется при каждой отрисовке — язык меняется
    на лету без пересборки меню. Иконка рисуется отдельно (menu_icons)."""
    return lambda item: t(key)


class TrayApp:
    def __init__(self):
        self.icon = None
        self._item_keys = {}          # id(MenuItem) -> ключ иконки

    def _item(self, key, action, **kwargs):
        """Пункт меню с цветной иконкой (текст берётся из i18n)."""
        entry = pystray.MenuItem(_label(key), action, **kwargs)
        self._item_keys[id(entry)] = key
        return entry

    def _build_menu(self):
        item = pystray.MenuItem

        menu = pystray.Menu(
            self._item('copy_mtproto',
                       lambda: self._copy(mtproto_link(), 'MTProto')),
            self._item('copy_socks_wifi',
                       lambda: self._copy(socks5_to_http.socks_link(), 'SOCKS5')),
            self._item('copy_socks_mobile',
                       lambda: self._copy(socks_link_outside(), 'SOCKS5')),
            pystray.Menu.SEPARATOR,
            self._item('qr_mtproto',
                       lambda: self._qr(mtproto_link(), 'MTProto — QR')),
            self._item('qr_socks_wifi',
                       lambda: self._qr(socks5_to_http.socks_link(), 'SOCKS5 — QR')),
            self._item('qr_socks_mobile',
                       lambda: self._qr(socks_link_outside(), 'SOCKS5 — QR')),
            pystray.Menu.SEPARATOR,
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
        )
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
