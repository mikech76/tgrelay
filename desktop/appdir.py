"""Каталоги приложения.

Работает в двух режимах:
  * из исходников  — tgrelay.txt и логи лежат рядом с файлами .py;
  * из бинарника   — tgrelay.txt и логи лежат рядом с tgrelay.exe / tgrelay,
    а шаблон, вшитый в сборку (tgrelay.example.txt), достаётся из temp.

Конфиг называется tgrelay.txt, чтобы открываться двойным кликом в Блокноте.
Старое имя .env поддерживается: при первом запуске он переименовывается.

ensure_env() возвращает:
  'ok'      — конфиг уже есть, запускаться;
  'created' — конфиг только что создан, пользователю нужно его заполнить
              (открыт и показан совет) — программа должна завершиться;
  None      — запуск из исходников, ничего делать не нужно.
"""
import os
import shutil
import sys
import time

CONFIG_NAME = 'tgrelay.txt'
LEGACY_NAME = '.env'


def find_config():
    """Путь к существующему конфигу: tgrelay.txt или старый .env."""
    dirs = (os.getcwd(), app_dir())
    for name in (CONFIG_NAME, LEGACY_NAME):
        for directory in dirs:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return path
    return None


def migrate_env(path):
    """Старый .env -> tgrelay.txt: так файл открывается двойным кликом."""
    if not path or os.path.basename(path) != LEGACY_NAME:
        return path
    target = os.path.join(os.path.dirname(path), CONFIG_NAME)
    if os.path.exists(target):
        return path
    try:
        os.replace(path, target)
        return target
    except OSError:
        return path


def is_frozen():
    """True, если программа запущена из собранного exe/bin."""
    return bool(getattr(sys, 'frozen', False))


def app_dir():
    """Каталог с конфигом и логами."""
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


def config_path():
    """Путь к конфигу для чтения и записи.

    Существующий tgrelay.txt (или старый .env) — где бы он ни лежал;
    старый .env по пути переименовывается. Если конфига нет —
    tgrelay.txt рядом с программой.
    """
    path = find_config()
    if path is None:
        return os.path.join(app_dir(), CONFIG_NAME)
    return migrate_env(path) or path


def ensure_env():
    if not is_frozen():
        return None

    found = find_config()
    if found:
        migrate_env(found)
        return 'ok'

    example = os.path.join(resource_dir(), 'tgrelay.example.txt')
    if not os.path.exists(example):
        return 'ok'

    # каталог рядом с exe может быть только для чтения — берём cwd
    written = None
    for directory in (app_dir(), os.getcwd()):
        dst = os.path.join(directory, CONFIG_NAME)
        try:
            shutil.copyfile(example, dst)
            written = dst
            break
        except OSError:
            continue
    if written is None:
        return 'ok'

    msg = ("tgrelay\n\n"
           f"Config file created / Создан файл настроек:\n"
           f"{written}\n\n"
           "EN: fill in PROXY= lines (your HTTP proxies), save the file\n"
           "    and run the program again.\n"
           "RU: впишите строки PROXY= (ваши HTTP-прокси), сохраните\n"
           "    и запустите программу заново.\n\n"
           "Double-click opens it as text / "
           "Открывается двойным кликом как текст.\n"
           "SECRET / LANG are filled in automatically / "
           "заполнятся автоматически.")
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


def _try_lock():
    """Захватить блокировку одного экземпляра (один раз, без ожидания)."""
    global _lock_handle
    try:
        if sys.platform == 'win32':
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            handle = kernel32.CreateMutexW(None, False, 'tgrelay-single-instance')
            if not handle:
                return True
            if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(handle)
                return False
            _lock_handle = handle
            return True
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


def single_instance(wait=0.0):
    """True, если это первый экземпляр. Блокировка держится до выхода.

    Второй запуск exe (частый случай: человек не заметил иконку в трее)
    иначе падал бы с «address already in use» и пугающим окном ошибки.

    wait — сколько секунд подождать, если экземпляр уже есть. Нужно при
    перезапуске из меню: новый процесс ждёт, пока старый освободит порты.
    """
    deadline = time.monotonic() + wait
    while True:
        if _try_lock():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


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
