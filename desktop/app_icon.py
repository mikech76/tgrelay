"""Иконка tgrelay со светящейся точкой статуса.

Пять состояний, цвет точки:
  ok        — зелёный: всё работает;
  traffic   — голубой: идёт трафик;
  starting  — жёлтый: подключение, прокси ещё проверяются;
  error     — красный: прокси не отвечают;
  off       — серый: не запущено.

Иконка рисуется кодом, поэтому одинаково выглядит в трее, в exe и в APK
(на Android берётся отдельный вектор, но той же композиции).
"""
from PIL import Image, ImageDraw

COLORS = {
    'ok': (46, 204, 113, 255),        # зелёный
    'traffic': (41, 200, 255, 255),   # голубой
    'starting': (241, 196, 15, 255),  # жёлтый
    'error': (231, 76, 60, 255),      # красный
    'off': (149, 165, 166, 255),      # серый
}

BG_TOP = (13, 26, 92, 255)
BG_BOTTOM = (5, 10, 40, 255)
NEON = (60, 214, 255, 255)
NEON_SOFT = (120, 226, 255, 255)
WHITE = (255, 255, 255, 255)


def render(state='ok', size=64):
    """Иконка состояния: скруглённый квадрат, антенны, самолётик, точка."""
    scale = 4
    s = size * scale
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # фон: вертикальный градиент в скруглённом квадрате
    for y in range(s):
        k = y / max(s - 1, 1)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k) for i in range(3)) + (255,)
        d.line([(0, y), (s, y)], fill=color)
    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1],
                                           radius=int(s * 0.22), fill=255)
    img.putalpha(mask)

    # неоновые дуги сверху
    arc_w = max(2, int(s * 0.045))
    for radius, offset in ((int(s * 0.22), 0), (int(s * 0.13), 0)):
        box = [s // 2 - radius, int(s * 0.30) - radius + offset,
               s // 2 + radius, int(s * 0.30) + radius + offset]
        d.arc(box, start=205, end=335, fill=NEON, width=arc_w)

    # самолётик
    plane = [
        (int(s * 0.20), int(s * 0.56)),
        (int(s * 0.80), int(s * 0.34)),
        (int(s * 0.54), int(s * 0.76)),
        (int(s * 0.47), int(s * 0.60)),
    ]
    d.polygon(plane, fill=WHITE)
    fold = [
        (int(s * 0.47), int(s * 0.60)),
        (int(s * 0.54), int(s * 0.76)),
        (int(s * 0.44), int(s * 0.66)),
    ]
    d.polygon(fold, fill=(190, 226, 255, 255))

    # точка статуса
    cx, cy = int(s * 0.76), int(s * 0.78)
    r = int(s * 0.115)
    ring = max(1, int(s * 0.028))
    d.ellipse([cx - r - ring, cy - r - ring, cx + r + ring, cy + r + ring],
              fill=WHITE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=COLORS.get(state, COLORS['ok']))

    return img.resize((size, size), Image.LANCZOS)


def save_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    """Записать tgrelay.ico с зелёной точкой (для exe и ярлыков)."""
    base = render('ok', 256)
    base.save(path, format='ICO', sizes=[(n, n) for n in sizes])
    return path


def save_png(path, state='ok', size=512):
    render(state, size).save(path, format='PNG')
    return path
