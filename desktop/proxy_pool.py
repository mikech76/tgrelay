import logging
import os
import random
import re
import socket
import threading
import time

from dotenv import dotenv_values

from appdir import config_path
from i18n import t

logger = logging.getLogger(__name__)

ENV_PATH = config_path()
config = dotenv_values(ENV_PATH)

_OFF_VALUES = {'', '0', 'off', 'none', 'no', 'disable', 'disabled', '-'}


def _env_text():
    try:
        with open(ENV_PATH, 'r', encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def port_value(key, default):
    """Порт протокола из tgrelay.txt; None — протокол выключен.

    Выключен, если значение пустое (PROXY_PORT=), 0, off/none/no/disable/-,
    либо строка с портом осталась только закомментированной (#PROXY_PORT=…).
    Ключа нет совсем — берём default, как раньше.
    """
    raw = config.get(key)
    if raw is None:
        if re.search(rf'^[ \t]*#[ \t]*{re.escape(key)}[ \t]*=',
                     _env_text(), re.M):
            return None
        return int(default)
    value = raw.strip().lower()
    if value in _OFF_VALUES:
        return None
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"{key}={raw} — это не порт")



def save_env_value(key, value):
    """Записывает KEY=value в tgrelay.txt, сохраняя комментарии и остальные строки."""
    lines = []
    try:
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        pass

    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        if stripped.split('=', 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    with open(ENV_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")


def _iter_env(path):
    """Пара КЛЮЧ=значение из tgrelay.txt, без комментариев. Понимает повторы ключей."""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                val = re.split(r'\s+#', val)[0].strip().strip('"').strip("'")
                yield key.strip(), val
    except FileNotFoundError:
        pass


def proxy_raw():
    """Список прокси: PROXIES=... одной строкой и/или строки PROXY=..."""
    parts = []
    if config.get('PROXIES'):
        parts.append(config['PROXIES'])
    for key, val in _iter_env(ENV_PATH):
        if key == 'PROXY' and val:
            parts.append(val)
    return ';'.join(parts)


class Proxy:
    def __init__(self, host, port, user, password, kind=None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.kind = kind        # http / https / socks5 / socks4, None = авто
        self.alive = True
        self.last_check = 0
        self.fail_count = 0

    def check(self, timeout=5):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            sock.close()
            self.alive = True
            self.fail_count = 0
            self.last_check = time.time()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            self.fail_count += 1
            if self.fail_count >= 3:
                self.alive = False
            self.last_check = time.time()
            return False

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    @property
    def addr(self):
        return f"{self.host}:{self.port}"


class ProxyPool:
    def __init__(self, check_interval=60):
        self.proxies = []
        self._lock = threading.Lock()
        self._check_interval = check_interval
        self._running = False
        self._load()
        self._start_health_check()

    def _load(self):
        raw = proxy_raw()
        from upstream_proxy import parse_line
        for item in raw.replace(chr(10), ";").split(";"):
            try:
                data = parse_line(item)
            except ValueError as exc:
                logger.warning("%s", exc)
                continue
            if data is None:
                continue
            proxy = Proxy(data["host"], data["port"], data["user"],
                          data["password"], data["kind"])
            self.proxies.append(proxy)
            logger.info("Loaded proxy: %s (%s)", proxy.addr,
                        proxy.kind or "авто")

    def _start_health_check(self):
        self._running = True
        thread = threading.Thread(target=self._health_check_loop, daemon=True)
        thread.start()
        logger.info(f"Health check started (interval: {self._check_interval}s)")

    def _health_check_loop(self):
        while self._running:
            self._check_all()
            time.sleep(self._check_interval)

    def _check_all(self):
        with self._lock:
            alive_count = 0
            for proxy in self.proxies:
                was_alive = proxy.alive
                is_alive = proxy.check()

                if was_alive and not is_alive:
                    logger.warning(f"Proxy DOWN: {proxy.addr} (failures: {proxy.fail_count})")
                elif not was_alive and is_alive:
                    logger.info(f"Proxy UP: {proxy.addr}")

                if is_alive:
                    alive_count += 1

            logger.debug(f"Health check: {alive_count}/{len(self.proxies)} proxies alive")

    def get(self):
        with self._lock:
            alive_proxies = [p for p in self.proxies if p.alive]
            if not alive_proxies:
                logger.error("No alive proxies available!")
                return None
            return random.choice(alive_proxies)

    def get_any(self):
        with self._lock:
            if not self.proxies:
                return None
            return random.choice(self.proxies)

    @property
    def count(self):
        with self._lock:
            return len(self.proxies)

    @property
    def alive_count(self):
        with self._lock:
            return len([p for p in self.proxies if p.alive])

    def stop(self):
        self._running = False


def load_telegram_hosts():
    raw = config.get('TELEGRAM_HOSTS', '149.154.175.50:443')
    hosts = []
    for entry in raw.split(','):
        entry = entry.strip()
        if ':' in entry:
            parts = entry.split(':')
            hosts.append((parts[0], int(parts[1])))
    return hosts


def load_secret():
    """Секрет MTProto: берём из tgrelay.txt, а если пустой/битый — предлагаем создать."""
    raw = (config.get('SECRET') or '').replace(' ', '').replace('-', '')
    valid = bool(re.fullmatch(r'[0-9a-fA-F]{32,64}', raw)) and len(raw) % 2 == 0
    if valid:
        return bytes.fromhex(raw)

    import secrets as _secrets
    import sys

    answer = ''
    if sys.stdin is not None and sys.stdin.isatty():
        print()
        print(t('secret_missing'))
        try:
            answer = input(t('secret_ask')).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ''
        if answer in ('n', 'no', 'н', 'нет'):
            print(t('secret_declined'))
            print(t('secret_manual'))
            raise SystemExit(1)

    raw = _secrets.token_hex(16)
    try:
        save_env_value('SECRET', raw)
        logger.info("SECRET generated and saved to tgrelay.txt")
        print(t('secret_written', secret=raw))
    except OSError as e:
        logger.warning("SECRET generated, but could not save it to tgrelay.txt: %s", e)
        print(t('secret_not_saved', secret=raw))
    config['SECRET'] = raw
    return bytes.fromhex(raw)


def lan_ip():
    """Адрес этой машины в локальной сети (для ссылок «Wi-Fi»)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return '127.0.0.1'


def external_host():
    """Внешнее имя/IP из EXTERNAL_HOST (пусто — не задано)."""
    return (config.get('EXTERNAL_HOST') or '').strip()


def get_external_ip():
    return external_host() or lan_ip()
