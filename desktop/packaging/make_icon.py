"""Иконка tgrelay.ico со светящейся точкой статуса — для exe и ярлыков."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import app_icon  # noqa: E402

OUT = os.path.join(HERE, 'tgrelay.ico')


def main():
    app_icon.save_ico(OUT)
    print(f'icon: {OUT}')


if __name__ == '__main__':
    main()
