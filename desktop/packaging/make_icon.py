"""Генерирует иконку tgrelay.ico (круг с буквой M) — для трея и для exe."""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'tgrelay.ico')
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
         (256, 256)]


def make(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    draw.ellipse([pad, pad, size - pad, size - pad],
                 fill=(0, 168, 132, 255))

    try:
        font = ImageFont.truetype('arial.ttf', int(size * 0.58))
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), 'M', font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2 - size // 32),
              'M', fill='white', font=font)
    return img


def main():
    make(256).save(OUT, format='ICO', sizes=SIZES)
    print(f'icon: {OUT}')


if __name__ == '__main__':
    main()
