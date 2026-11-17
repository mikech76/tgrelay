"""Цветные иконки для меню трея.

Меню pystray — обычное Win32-меню, поэтому картинки в пунктах задаются
через MENUITEMINFO.hbmpItem (32 бита с альфой, поддерживается с Vista).
Сами иконки рисуются здесь же через PIL, без внешних файлов.
"""
import ctypes
import sys

from PIL import Image, ImageDraw

_BASE = 64                      # рисуем крупно, потом уменьшаем — так глаже
_cache = {}


# --------------------------------------------------------------------------
#  Рисование иконок (64x64, прозрачный фон)
# --------------------------------------------------------------------------

def _clipboard(d, s):
    d.rounded_rectangle([12, 12, 52, 56], radius=6,
                        fill=(255, 255, 255, 255), outline=(120, 144, 156, 255),
                        width=2)
    d.rounded_rectangle([23, 5, 41, 17], radius=3, fill=(120, 144, 156, 255))
    d.rectangle([21, 26, 43, 29], fill=(25, 118, 210, 255))
    d.rectangle([21, 35, 43, 38], fill=(25, 118, 210, 255))
    d.rectangle([21, 44, 36, 47], fill=(25, 118, 210, 255))


def _wifi(d, s):
    teal = (38, 166, 154, 255)
    for r, w in ((24, 7), (16, 7)):
        d.arc([s // 2 - r, s - 12 - r, s // 2 + r, s - 12 + r],
              start=200, end=340, fill=teal, width=w)
    d.ellipse([s // 2 - 5, s - 18, s // 2 + 5, s - 8], fill=teal)


def _phone(d, s):
    d.rounded_rectangle([19, 6, 45, 58], radius=7, fill=(55, 71, 79, 255))
    d.rounded_rectangle([24, 14, 40, 44], radius=2, fill=(77, 208, 225, 255))
    d.ellipse([29, 49, 35, 55], fill=(176, 190, 197, 255))


def _qr(d, s):
    black = (33, 33, 33, 255)
    d.rounded_rectangle([4, 4, 60, 60], radius=5,
                        fill=(255, 255, 255, 255), outline=(150, 150, 150, 255),
                        width=2)
    for x, y in ((10, 10), (40, 10), (10, 40)):
        d.rectangle([x, y, x + 14, y + 14], fill=black)
        d.rectangle([x + 4, y + 4, x + 10, y + 10],
                    fill=(255, 255, 255, 255))
        d.rectangle([x + 6, y + 6, x + 8, y + 8], fill=black)
    for x, y in ((40, 40), (46, 40), (40, 46), (48, 48), (30, 46), (46, 30)):
        d.rectangle([x, y, x + 4, y + 4], fill=black)


def _globe(d, s):
    blue = (30, 136, 229, 255)
    white = (255, 255, 255, 235)
    d.ellipse([6, 6, 58, 58], fill=blue)
    d.ellipse([6, 6, 58, 58], outline=(21, 101, 192, 255), width=2)
    d.ellipse([22, 6, 42, 58], outline=white, width=3)
    d.ellipse([6, 24, 58, 40], outline=white, width=3)
    d.line([6, 32, 58, 32], fill=white, width=3)


def _book(d, s):
    d.rounded_rectangle([9, 10, 55, 56], radius=4, fill=(230, 126, 34, 255))
    d.rectangle([15, 10, 19, 56], fill=(191, 87, 0, 255))
    d.rounded_rectangle([21, 16, 51, 50], radius=2, fill=(255, 255, 255, 255))
    for y in (23, 30, 37):
        d.rectangle([25, y, 47, y + 2], fill=(158, 158, 158, 255))


def _info(d, s):
    d.ellipse([6, 6, 58, 58], fill=(30, 136, 229, 255))
    d.ellipse([29, 16, 35, 22], fill=(255, 255, 255, 255))
    d.rounded_rectangle([28, 26, 36, 48], radius=3,
                        fill=(255, 255, 255, 255))


def _power(d, s):
    red = (229, 57, 53, 255)
    d.arc([14, 14, 50, 50], start=300, end=240, fill=red, width=7)
    d.line([32, 8, 32, 30], fill=red, width=7)


_DRAW = {
    'copy_mtproto': _clipboard,
    'copy_socks_wifi': _wifi,
    'copy_socks_mobile': _phone,
    'qr_mtproto': _qr,
    'qr_socks_wifi': _qr,
    'qr_socks_mobile': _qr,
    'menu_language': _globe,
    'menu_docs': _book,
    'menu_about': _info,
    'menu_exit': _power,
}


def render(key, size):
    """PIL-картинка иконки нужного размера (RGBA)."""
    img = Image.new('RGBA', (_BASE, _BASE), (0, 0, 0, 0))
    _DRAW[key](ImageDraw.Draw(img), _BASE)
    return img.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------------------
#  PIL -> HBITMAP (32 бита, альфа)
# --------------------------------------------------------------------------

def _to_hbitmap(img):
    """HBITMAP для пункта меню: BGRA с premultiplied alpha."""
    width, height = img.size
    rgba = img.convert('RGBA')
    data = bytearray(width * height * 4)
    src = rgba.tobytes()
    for i in range(0, len(src), 4):
        r, g, b, a = src[i], src[i + 1], src[i + 2], src[i + 3]
        k = a / 255
        data[i] = int(b * k)
        data[i + 1] = int(g * k)
        data[i + 2] = int(r * k)
        data[i + 3] = a

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32), ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32), ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [('bmiHeader', BITMAPINFOHEADER),
                    ('bmiColors', ctypes.c_uint32 * 3)]

    gdi32 = ctypes.WinDLL('gdi32')
    user32 = ctypes.WinDLL('user32')

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height          # сверху вниз
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0           # BI_RGB

    bits = ctypes.c_void_p()
    hdc = user32.GetDC(None)
    hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(info), 0,
                                  ctypes.byref(bits), None, 0)
    user32.ReleaseDC(None, hdc)
    if not hbmp:
        return None
    ctypes.memmove(bits, bytes(data), len(data))
    return hbmp


def _pixel_size():
    try:
        dpi = ctypes.WinDLL('user32').GetDpiForSystem()
    except AttributeError:
        dpi = 96
    except Exception:
        dpi = 96
    return max(16, round(16 * dpi / 96))


def bitmap(key):
    """HBITMAP для ключа пункта меню (кэшируется на всё время работы)."""
    if sys.platform != 'win32':
        return None
    if key not in _cache:
        try:
            _cache[key] = _to_hbitmap(render(key, _pixel_size()))
        except Exception:
            _cache[key] = None
    return _cache[key]


# --------------------------------------------------------------------------
#  Встраивание в меню pystray
# --------------------------------------------------------------------------

def install(item_keys):
    """Научить pystray рисовать иконки. item_keys: id(MenuItem) -> ключ."""
    if sys.platform != 'win32':
        return False
    try:
        import pystray._win32 as backend
        from pystray._util import win32 as pw
    except Exception:
        return False

    original = backend.Icon._create_menu_item
    if getattr(original, '_tgrelay_icons', False):
        return True

    def patched(self, descriptor, callbacks):
        info = original(self, descriptor, callbacks)
        key = item_keys.get(id(descriptor))
        if key:
            hbmp = bitmap(key)
            if hbmp:
                info.fMask |= pw.MIIM_BITMAP
                info.hbmpItem = hbmp
        return info

    patched._tgrelay_icons = True
    backend.Icon._create_menu_item = patched
    return True
