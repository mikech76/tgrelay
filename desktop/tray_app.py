import io
import os
import threading
import tkinter as tk

import pystray
import pyperclip
import qrcode
from PIL import Image, ImageDraw, ImageFont

import socks5_to_http
from proxy_pool import config, get_external_ip


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


def socks_link_outside():
    """Та же ссылка, но с внешним адресом (для мобильной сети)."""
    return socks5_to_http.socks_link(host=get_external_ip())


class TrayApp:
    def __init__(self):
        self.icon = None

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem(
                "Copy MTProto link",
                lambda: self._copy(mtproto_link(), "MTProto")),
            pystray.MenuItem(
                "Copy SOCKS link (Wi-Fi)",
                lambda: self._copy(socks5_to_http.socks_link(), "SOCKS5")),
            pystray.MenuItem(
                "Copy SOCKS link (моб. сеть)",
                lambda: self._copy(socks_link_outside(), "SOCKS5")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "MTProto QR",
                lambda: self._qr(mtproto_link(), "MTProxy — QR")),
            pystray.MenuItem(
                "SOCKS QR (Wi-Fi)",
                lambda: self._qr(socks5_to_http.socks_link(), "SOCKS5 — QR")),
            pystray.MenuItem(
                "SOCKS QR (моб. сеть)",
                lambda: self._qr(socks_link_outside(), "SOCKS5 (моб.) — QR")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )
        self.icon = pystray.Icon("MTProxy", _make_icon(),
                                 "MTProxy + SOCKS5", menu)
        self.icon.run()

    def _copy(self, link, name):
        try:
            pyperclip.copy(link)
            self.icon.notify(f"{link}", f"{name} — скопировано")
        except Exception as e:
            self.icon.notify(f"Не скопировалось: {e}", name)

    def _qr(self, link, title):
        threading.Thread(target=QRWindow(link, title).show, daemon=True).start()

    def _on_exit(self, icon, item):
        icon.stop()
        os._exit(0)
