"""Генератор PNG-иконок для Go-версии: иконка трея и иконки пунктов меню.

Запускать из папки go:
    python tools/make_assets.py

Пишет go/assets/*.png. Go вшивает их через go:embed, поэтому при изменении
иконок нужно просто перегенерировать и пересобрать.
"""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'assets')
BASE = 64

# --- палитра ---------------------------------------------------------------

BG_TOP = (13, 26, 92, 255)
BG_BOTTOM = (5, 10, 40, 255)
NEON = (60, 214, 255, 255)
WHITE = (255, 255, 255, 255)

DOT = {
    'ok': (46, 204, 113, 255),
    'traffic': (41, 200, 255, 255),
    'starting': (241, 196, 15, 255),
    'error': (231, 76, 60, 255),
    'off': (149, 165, 166, 255),
}


# --- иконка трея -----------------------------------------------------------

def tray_icon(state='ok', size=64):
    scale = 4
    s = size * scale
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    for y in range(s):
        k = y / max(s - 1, 1)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k)
                      for i in range(3)) + (255,)
        d.line([(0, y), (s, y)], fill=color)

    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1],
                                           radius=int(s * 0.22), fill=255)
    img.putalpha(mask)

    arc_w = max(2, int(s * 0.045))
    for radius in (int(s * 0.22), int(s * 0.13)):
        box = [s // 2 - radius, int(s * 0.30) - radius,
               s // 2 + radius, int(s * 0.30) + radius]
        d.arc(box, start=205, end=335, fill=NEON, width=arc_w)

    d.polygon([(int(s * 0.20), int(s * 0.56)), (int(s * 0.80), int(s * 0.34)),
               (int(s * 0.54), int(s * 0.76)), (int(s * 0.47), int(s * 0.60))],
              fill=WHITE)
    d.polygon([(int(s * 0.47), int(s * 0.60)), (int(s * 0.54), int(s * 0.76)),
               (int(s * 0.44), int(s * 0.66))], fill=(190, 226, 255, 255))

    cx, cy = int(s * 0.76), int(s * 0.78)
    r = int(s * 0.115)
    ring = max(1, int(s * 0.028))
    d.ellipse([cx - r - ring, cy - r - ring, cx + r + ring, cy + r + ring],
              fill=WHITE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DOT[state])

    return img.resize((size, size), Image.LANCZOS)


# --- пункты меню (64x64) ---------------------------------------------------

def _clipboard(d, s):
    d.rounded_rectangle([12, 12, 52, 56], radius=6, fill=WHITE,
                        outline=(120, 144, 156, 255), width=2)
    d.rounded_rectangle([23, 5, 41, 17], radius=3, fill=(120, 144, 156, 255))
    d.rectangle([21, 26, 43, 29], fill=(25, 118, 210, 255))
    d.rectangle([21, 35, 43, 38], fill=(25, 118, 210, 255))
    d.rectangle([21, 44, 36, 47], fill=(25, 118, 210, 255))


def _qr(d, s):
    black = (33, 33, 33, 255)
    d.rounded_rectangle([4, 4, 60, 60], radius=5, fill=WHITE,
                        outline=(150, 150, 150, 255), width=2)
    for x, y in ((10, 10), (40, 10), (10, 40)):
        d.rectangle([x, y, x + 14, y + 14], fill=black)
        d.rectangle([x + 4, y + 4, x + 10, y + 10], fill=WHITE)
        d.rectangle([x + 6, y + 6, x + 8, y + 8], fill=black)
    for x, y in ((40, 40), (46, 40), (40, 46), (48, 48), (30, 46), (46, 30)):
        d.rectangle([x, y, x + 4, y + 4], fill=black)


def _language(d, s):
    """Язык: «A» и «Я» на белой карточке — узнается лучше глобуса."""
    d.rounded_rectangle([4, 10, 60, 54], radius=8, fill=WHITE,
                        outline=(120, 144, 156, 255), width=2)
    font = _font(34)
    blue = (25, 118, 210, 255)
    orange = (230, 126, 34, 255)
    _center_text(d, "A", font, 18, 32, blue)
    _center_text(d, "Я", font, 46, 32, orange)


def _font(size):
    from PIL import ImageFont
    for name in ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf',
                 'arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _center_text(d, text, font, cx, cy, fill):
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text((cx - w / 2 - box[0], cy - h / 2 - box[1]), text, font=font,
           fill=fill)


def _book(d, s):
    d.rounded_rectangle([9, 10, 55, 56], radius=4, fill=(230, 126, 34, 255))
    d.rectangle([15, 10, 19, 56], fill=(191, 87, 0, 255))
    d.rounded_rectangle([21, 16, 51, 50], radius=2, fill=WHITE)
    for y in (23, 30, 37):
        d.rectangle([25, y, 47, y + 2], fill=(158, 158, 158, 255))


def _info(d, s):
    d.ellipse([6, 6, 58, 58], fill=(30, 136, 229, 255))
    d.ellipse([29, 16, 35, 22], fill=WHITE)
    d.rounded_rectangle([28, 26, 36, 48], radius=3, fill=WHITE)


def _power(d, s):
    red = (229, 57, 53, 255)
    d.arc([14, 14, 50, 50], start=300, end=240, fill=red, width=7)
    d.line([32, 8, 32, 30], fill=red, width=7)


def _gear(d, s):
    steel = (96, 125, 139, 255)
    c = s / 2
    points = []
    for i in range(16):
        radius = 24 if i % 2 == 0 else 17
        angle = math.pi * i / 8
        points.append((c + radius * math.cos(angle),
                       c + radius * math.sin(angle)))
    d.polygon(points, fill=steel)
    d.ellipse([c - 13, c - 13, c + 13, c + 13], fill=WHITE)
    d.ellipse([c - 7, c - 7, c + 7, c + 7], fill=steel)


def _pencil(d, s):
    """Редактирование конфига: карандаш по листу."""
    d.rounded_rectangle([8, 6, 52, 58], radius=4, fill=WHITE,
                        outline=(120, 144, 156, 255), width=2)
    for y in (16, 24, 32):
        d.rectangle([14, y, 34, y + 3], fill=(176, 190, 197, 255))
    orange = (245, 124, 0, 255)
    d.polygon([(30, 56), (42, 30), (50, 38), (38, 64)], fill=orange)
    d.polygon([(42, 30), (50, 38), (54, 28), (46, 22)], fill=(255, 183, 77, 255))
    d.polygon([(30, 56), (38, 64), (26, 64)], fill=(255, 224, 178, 255))


def _rocket(d, s):
    """Автозагрузка: ракета."""
    body = (229, 57, 53, 255)
    d.polygon([(32, 4), (44, 26), (44, 44), (32, 54), (20, 44), (20, 26)],
              fill=body)
    d.polygon([(20, 36), (10, 52), (22, 48)], fill=(198, 40, 40, 255))
    d.polygon([(44, 36), (54, 52), (42, 48)], fill=(198, 40, 40, 255))
    d.ellipse([26, 18, 38, 30], fill=WHITE, outline=(144, 164, 174, 255), width=2)
    d.polygon([(28, 56), (36, 56), (32, 64)], fill=(255, 167, 38, 255))


def _refresh(d, s):
    """Перечитать конфиг: круговая стрелка."""
    blue = (30, 136, 229, 255)
    d.arc([12, 12, 52, 52], start=40, end=320, fill=blue, width=8)
    d.polygon([(44, 4), (58, 18), (40, 18)], fill=blue)


def _flag_en(d, s):
    blue = (26, 35, 126, 255)
    d.rounded_rectangle([6, 14, 58, 50], radius=3, fill=blue)
    white = WHITE
    red = (211, 47, 47, 255)
    d.line([32, 14, 32, 50], fill=white, width=14)
    d.line([6, 32, 58, 32], fill=white, width=14)
    d.line([32, 14, 32, 50], fill=red, width=8)
    d.line([6, 32, 58, 32], fill=red, width=8)


def _flag_ru(d, s):
    d.rounded_rectangle([6, 14, 58, 50], radius=3, fill=WHITE)
    d.rectangle([6, 26, 58, 38], fill=(33, 71, 161, 255))
    d.rectangle([6, 38, 58, 50], fill=(211, 47, 47, 255))


DRAW = {
    'copy_mtproto': _clipboard,
    'copy_socks_wifi': _clipboard,
    'qr_mtproto': _qr,
    'qr_socks_wifi': _qr,
    'menu_settings': _gear,
    'menu_language': _language,
    'menu_docs': _book,
    'menu_about': _info,
    'menu_exit': _power,
    'menu_edit': _pencil,
    'menu_autostart': _rocket,
    'menu_reload': _refresh,
    'menu_lang_en': _flag_en,
    'menu_lang_ru': _flag_ru,
}


def render(key, size=BASE):
    img = Image.new('RGBA', (BASE, BASE), (0, 0, 0, 0))
    DRAW[key](ImageDraw.Draw(img), BASE)
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    for state in DOT:
        tray_icon(state, 64).save(os.path.join(OUT, 'icon_%s.png' % state))
    tray_icon('ok', 256).save(os.path.join(OUT, 'app.png'))
    for key in DRAW:
        render(key, 16).save(os.path.join(OUT, 'menu_%s.png' % key))
    print('assets:', sorted(os.listdir(OUT)))


if __name__ == '__main__':
    main()
