"""Каталоги приложения.

Работает в двух режимах:
  * из исходников  — .env и логи лежат рядом с файлами .py;
  * из бинарника   — .env и логи лежат рядом с tgrelay.exe / tgrelay,
    а ресурсы, вшитые в сборку (.env.example), достаются из temp-каталога.

ensure_env() возвращает:
  'ok'      — .env уже есть, запускаться;
  'created' — .env только что создан, пользователю нужно его заполнить
              (открыт и показан совет) — программа должна завершиться;
  None      — запуск из исходников, ничего делать не нужно.
"""
import os
import shutil
import sys


def is_frozen():
    """True, если программа запущена из собранного exe/bin."""
    return bool(getattr(sys, 'frozen', False))


def app_dir():
    """Каталог с .env и логами."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """Каталог с ресурсами, вшитыми в бинарник (--add-data)."""
    if is_frozen():
        return getattr(sys, '_MEIPASS', app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def log_path(name):
    """Путь к логу: рядом с программой, а если каталог недоступен — в cwd."""
    for directory in (app_dir(), os.getcwd()):
        path = os.path.join(directory, name)
        try:
            probe = open(path, 'a', encoding='utf-8')
            probe.close()
            return path
        except OSError:
            continue
    return None


def _first_existing_env():
    """Есть ли .env в cwd (как ищет proxy_pool) или рядом с программой."""
    for directory in (os.getcwd(), app_dir()):
        path = os.path.join(directory, '.env')
        if os.path.exists(path):
            return path
    return None


def ensure_env():
    if not is_frozen():
        return None
    if _first_existing_env():
        return 'ok'

    example = os.path.join(resource_dir(), '.env.example')
    if not os.path.exists(example):
        return 'ok'

    # каталог рядом с exe может быть только для чтения — берём cwd
    written = None
    for directory in (app_dir(), os.getcwd()):
        dst = os.path.join(directory, '.env')
        try:
            shutil.copyfile(example, dst)
            written = dst
            break
        except OSError:
            continue
    if written is None:
        return 'ok'

    msg = ("tgrelay\n\n"
           "Создан файл настроек:\n"
           f"{written}\n\n"
           "Впишите в него строки PROXY= (ваши HTTP-прокси), сохраните\n"
           "и запустите программу заново.\n"
           "SECRET будет сгенерирован автоматически.")
    print(msg, flush=True)
    if sys.platform == 'win32':
        try:
            os.startfile(written)          # откроется в Блокноте
        except OSError:
            pass
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, 'tgrelay', 0x40)
        except Exception:
            pass
    return 'created'


def fatal(text):
    """Нечего запускать (нет прокси, занят порт) — сказать и выйти."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f"tgrelay не запустился:\n\n{text}\n\n"
                      "Проверьте файл .env (строки PROXY=) и запустите "
                      "программу заново.",
                'tgrelay', 0x10)
        except Exception:
            pass
    else:
        print(f"tgrelay не запустился: {text}", file=sys.stderr, flush=True)
        print("Проверьте файл .env (строки PROXY=) и запустите заново.",
              file=sys.stderr, flush=True)
