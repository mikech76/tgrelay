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
           "Создан файл настроек / Config file created:\n"
           f"{written}\n\n"
           "RU: впишите строки PROXY= (ваши HTTP-прокси), сохраните\n"
           "    и запустите программу заново.\n"
           "EN: fill in PROXY= lines (your HTTP proxies), save the file\n"
           "    and run the program again.\n\n"
           "SECRET / LANG — заполнятся автоматически / filled in "
           "automatically.")
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


_lock_handle = None


def single_instance():
    """True, если это первый экземпляр. Блокировка держится до выхода.

    Второй запуск exe (частый случай: человек не заметил иконку в трее)
    иначе падал бы с «address already in use» и пугающим окном ошибки.
    """
    global _lock_handle
    try:
        if sys.platform == 'win32':
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            handle = kernel32.CreateMutexW(None, False, 'tgrelay-single-instance')
            if not handle:
                return True
            _lock_handle = handle
            return ctypes.get_last_error() != 183      # ERROR_ALREADY_EXISTS
        import fcntl
        handle = open(os.path.join(app_dir(), 'tgrelay.lock'), 'a+')
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        _lock_handle = handle
        return True
    except Exception:               # блокировки недоступны — не мешаем запуску
        return True


def notify_already_running():
    """Сказать, что программа уже работает, и выйти."""
    from i18n import t          # локальный импорт: i18n сам импортирует appdir
    body = t('already_running')
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, body, t('already_running_title'), 0x40)
        except Exception:
            pass
    print(body, flush=True)


def fatal(text):
    """Нечего запускать (нет прокси, занят порт) — сказать и выйти."""
    from i18n import t          # локальный импорт: i18n сам импортирует appdir
    body = t('fatal_body', err=text)
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, body, t('fatal_title'), 0x10)
        except Exception:
            pass
    else:
        print(body, file=sys.stderr, flush=True)
