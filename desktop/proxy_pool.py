import random
import re
import socket
import threading
import time
import logging
from dotenv import dotenv_values

config = dotenv_values()
logger = logging.getLogger(__name__)


class Proxy:
    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
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
        raw = config.get('PROXIES', '')
        for p in raw.split(';'):
            p = p.strip()
            if not p:
                continue
            m = re.match(r'(.+?):(.+?)@(.+?):(\d+)', p)
            if m:
                proxy = Proxy(
                    host=m.group(3),
                    port=int(m.group(4)),
                    user=m.group(1),
                    password=m.group(2)
                )
                self.proxies.append(proxy)
                logger.info(f"Loaded proxy: {proxy.addr}")
                continue
            m = re.match(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d+)', p)
            if m:
                proxy = Proxy(
                    host=m.group(1),
                    port=int(m.group(2)),
                    user='',
                    password=''
                )
                self.proxies.append(proxy)
                logger.info(f"Loaded proxy (no auth): {proxy.addr}")

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
    s = config.get('SECRET', '')
    if not s:
        import secrets
        s = secrets.token_hex(16)
    s = s.replace(' ', '').replace('-', '')
    return bytes.fromhex(s)


def get_external_ip():
    host = config.get('EXTERNAL_HOST', '')
    if host:
        return host
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'
