"""Локализация интерфейса: English / Русский.

Язык берётся из tgrelay.txt (LANG=en|ru). Если там пусто — из языка системы
(Windows: язык интерфейса, Linux: $LANG).
"""
import os
import sys

from dotenv import dotenv_values

from appdir import find_config

LANGS = ('en', 'ru')

STRINGS = {
    # трей
    'tray_tooltip': {
        'en': 'tgrelay: MTProto + SOCKS5',
        'ru': 'tgrelay: MTProto + SOCKS5',
    },
    'copy_link_at': {
        'en': 'Copy link — {host}',
        'ru': 'Копировать ссылку — {host}',
    },
    'qr_link_at': {
        'en': 'Show QR code — {host}',
        'ru': 'Показать QR-код — {host}',
    },
    'menu_language': {
        'en': 'Language',
        'ru': 'Язык',
    },
    'menu_settings': {
        'en': 'Settings — tgrelay.txt',
        'ru': 'Настройки — tgrelay.txt',
    },
    'settings_saved': {
        'en': 'Settings applied — restarting…',
        'ru': 'Настройки применены — перезапуск…',
    },
    'settings_restart_later': {
        'en': 'Settings saved. The restart will happen after you close '
              'the editor.',
        'ru': 'Настройки сохранены. Перезапуск — после закрытия редактора.',
    },
    # строки состояния в меню трея
    'status_proxies': {
        'en': '{alive}/{total} proxies · {conns} connections',
        'ru': 'Прокси {alive}/{total} · соединений {conns}',
    },
    'status_speed': {
        'en': '↓ {down}/s    ↑ {up}/s',
        'ru': '↓ {down}/с    ↑ {up}/с',
    },
    'status_total': {
        'en': 'since start ↓ {down}    ↑ {up}',
        'ru': 'всего ↓ {down}    ↑ {up}',
    },
    'unit_b': {'en': 'B', 'ru': 'Б'},
    'unit_kb': {'en': 'KB', 'ru': 'КБ'},
    'unit_mb': {'en': 'MB', 'ru': 'МБ'},
    'unit_gb': {'en': 'GB', 'ru': 'ГБ'},
    'menu_docs': {
        'en': 'Documentation',
        'ru': 'Документация',
    },
    'menu_about': {
        'en': 'About',
        'ru': 'О программе',
    },
    'menu_exit': {
        'en': 'Exit',
        'ru': 'Выход',
    },
    'copied': {
        'en': '{name} — copied to clipboard',
        'ru': '{name} — скопировано в буфер',
    },
    'copy_failed': {
        'en': 'Copy failed: {err}',
        'ru': 'Не скопировалось: {err}',
    },
    'about_title': {
        'en': 'About tgrelay',
        'ru': 'О программе tgrelay',
    },
    'about_text': {
        'en': ('tgrelay {version}\n\n'
               'MTProto and SOCKS5 proxies for Telegram, running on top of your '
               'pool of HTTP CONNECT proxies.\n\n'
               'Android app, Windows tray app and Linux headless build.\n\n'
               'Author: mikech76\n'
               'Source code and docs: {repo}\n'
               'License: MIT'),
        'ru': ('tgrelay {version}\n\n'
               'Прокси MTProto и SOCKS5 для Telegram поверх пула '
               'HTTP CONNECT-прокси.\n\n'
               'Приложение для Android, трей для Windows и headless-сборка '
               'для Linux.\n\n'
               'Автор: mikech76\n'
               'Исходники и документация: {repo}\n'
               'Лицензия: MIT'),
    },
    # первый запуск и критичные ошибки
    'fatal_body': {
        'en': ('tgrelay failed to start:\n\n{err}\n\n'
               'Check PROXY= lines in tgrelay.txt and start the program again.'),
        'ru': ('tgrelay не запустился:\n\n{err}\n\n'
               'Проверьте строки PROXY= в tgrelay.txt и запустите программу заново.'),
    },
    'fatal_title': {
        'en': 'tgrelay',
        'ru': 'tgrelay',
    },
    'already_running': {
        'en': ('tgrelay is already running.\n\n'
               'Its icon is in the system tray, next to the clock.'),
        'ru': ('tgrelay уже запущен.\n\n'
               'Иконка — в системном трее, возле часов.'),
    },
    'already_running_title': {
        'en': 'tgrelay',
        'ru': 'tgrelay',
    },
    # секрет MTProto
    'secret_missing': {
        'en': 'SECRET is not set in tgrelay.txt for the MTProto proxy.',
        'ru': 'В tgrelay.txt не задан SECRET для MTProto-прокси.',
    },
    'secret_ask': {
        'en': 'Generate a new key? [Y/n]: ',
        'ru': 'Сгенерировать новый ключ? [Y/n]: ',
    },
    'secret_declined': {
        'en': 'OK. Put your own SECRET into tgrelay.txt and run again.',
        'ru': 'Хорошо. Впишите свой SECRET в tgrelay.txt и запустите снова.',
    },
    'secret_manual': {
        'en': ('Generate one manually: python -c "import secrets; '
               'print(secrets.token_hex(16))"'),
        'ru': ('Сгенерировать вручную: python -c "import secrets; '
               'print(secrets.token_hex(16))"'),
    },
    'secret_written': {
        'en': 'SECRET generated and saved to tgrelay.txt: {secret}',
        'ru': 'SECRET сгенерирован и записан в tgrelay.txt: {secret}',
    },
    'secret_not_saved': {
        'en': 'SECRET generated (not saved): {secret}',
        'ru': 'SECRET сгенерирован (не сохранён): {secret}',
    },
    # прочее
    'no_proxies': {
        'en': 'no PROXIES in tgrelay.txt',
        'ru': 'в tgrelay.txt нет PROXIES',
    },
    'no_protocols': {
        'en': ('both protocols are disabled in tgrelay.txt '
               '(PROXY_PORT and SOCKS_PORT) — nothing to start'),
        'ru': ('оба протокола отключены в tgrelay.txt '
               '(PROXY_PORT и SOCKS_PORT) — запускать нечего'),
    },
    'stopped': {
        'en': 'Stopped.',
        'ru': 'Остановлено.',
    },
}

_cache = {}


def _env_lang():
    path = find_config()
    if not path:
        return ''
    try:
        value = (dotenv_values(path).get('LANG') or '').strip().lower()
    except Exception:
        return ''
    return value if value in LANGS else ''


def _system_lang():
    if sys.platform == 'win32':
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return 'ru' if (lcid & 0x3FF) == 0x19 else 'en'
        except Exception:
            return 'en'
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '').strip().lower()
        if value.startswith('ru'):
            return 'ru'
        if value:
            return 'en'
    return 'en'


def lang():
    """Текущий язык интерфейса: 'en' или 'ru'."""
    if 'lang' not in _cache:
        _cache['lang'] = _env_lang() or _system_lang()
    return _cache['lang']


def set_lang(value):
    """Запомнить язык в памяти (в конфиг пишет вызывающая сторона)."""
    if value in LANGS:
        _cache['lang'] = value


def t(key, **kwargs):
    """Строка по ключу на текущем языке (fallback — английский)."""
    entry = STRINGS.get(key, {})
    text = entry.get(lang()) or entry.get('en') or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
