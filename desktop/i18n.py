"""Локализация интерфейса: English / Русский.

Язык берётся из .env (LANG=en|ru). Если там пусто — из языка системы
(Windows: язык интерфейса, Linux: $LANG).
"""
import os
import sys

from dotenv import dotenv_values

from appdir import app_dir

LANGS = ('en', 'ru')

STRINGS = {
    # трей
    'tray_tooltip': {
        'en': 'tgrelay: MTProto + SOCKS5',
        'ru': 'tgrelay: MTProto + SOCKS5',
    },
    'copy_mtproto': {
        'en': 'Copy MTProto link',
        'ru': 'Копировать ссылку MTProto',
    },
    'copy_socks_wifi': {
        'en': 'Copy SOCKS link (Wi-Fi)',
        'ru': 'Копировать ссылку SOCKS (Wi-Fi)',
    },
    'copy_socks_mobile': {
        'en': 'Copy SOCKS link (mobile)',
        'ru': 'Копировать ссылку SOCKS (моб. сеть)',
    },
    'qr_mtproto': {
        'en': 'MTProto QR',
        'ru': 'QR: MTProto',
    },
    'qr_socks_wifi': {
        'en': 'SOCKS QR (Wi-Fi)',
        'ru': 'QR: SOCKS (Wi-Fi)',
    },
    'qr_socks_mobile': {
        'en': 'SOCKS QR (mobile)',
        'ru': 'QR: SOCKS (моб. сеть)',
    },
    'menu_language': {
        'en': 'Language',
        'ru': 'Язык',
    },
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
               'Check PROXY= lines in .env and start the program again.'),
        'ru': ('tgrelay не запустился:\n\n{err}\n\n'
               'Проверьте строки PROXY= в .env и запустите программу заново.'),
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
        'en': 'SECRET is not set in .env for the MTProto proxy.',
        'ru': 'В .env не задан SECRET для MTProto-прокси.',
    },
    'secret_ask': {
        'en': 'Generate a new key? [Y/n]: ',
        'ru': 'Сгенерировать новый ключ? [Y/n]: ',
    },
    'secret_declined': {
        'en': 'OK. Put your own SECRET into .env and run again.',
        'ru': 'Хорошо. Впишите свой SECRET в .env и запустите снова.',
    },
    'secret_manual': {
        'en': ('Generate one manually: python -c "import secrets; '
               'print(secrets.token_hex(16))"'),
        'ru': ('Сгенерировать вручную: python -c "import secrets; '
               'print(secrets.token_hex(16))"'),
    },
    'secret_written': {
        'en': 'SECRET generated and saved to .env: {secret}',
        'ru': 'SECRET сгенерирован и записан в .env: {secret}',
    },
    'secret_not_saved': {
        'en': 'SECRET generated (not saved): {secret}',
        'ru': 'SECRET сгенерирован (не сохранён): {secret}',
    },
    # прочее
    'no_proxies': {
        'en': 'no PROXIES in .env',
        'ru': 'в .env нет PROXIES',
    },
    'stopped': {
        'en': 'Stopped.',
        'ru': 'Остановлено.',
    },
}

_cache = {}


def _env_lang():
    for directory in (os.getcwd(), app_dir()):
        path = os.path.join(directory, '.env')
        if not os.path.exists(path):
            continue
        try:
            value = (dotenv_values(path).get('LANG') or '').strip().lower()
        except Exception:
            return ''
        return value if value in LANGS else ''
    return ''


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
    """Запомнить язык в памяти (в .env пишет вызывающая сторона)."""
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
