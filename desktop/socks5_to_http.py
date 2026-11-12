#!/usr/bin/env python3
"""
socks5_to_http.py

Локальный SOCKS5-сервер, который весь трафик отправляет через пул
HTTP CONNECT-прокси (с Basic-аутентификацией, как у ProxyMania).

Зачем это нужно:
    Telegram умеет только SOCKS5 / MTProto / WEB. Купленные прокси говорят
    HTTP CONNECT. Этот скрипт принимает SOCKS5 от Telegram и превращает его
    в CONNECT к HTTP-прокси.

Чего он НЕ делает:
    Не расшифровывает трафик Telegram. SOCKS5 передаёт только адрес и порт,
    а шифрование Telegram идёт сквозным образом до серверов Telegram.

Запуск:
    python socks5_to_http.py                 # слушать 127.0.0.1:55056
    python socks5_to_http.py --port 9050
    python socks5_to_http.py --test          # проверить прокси и выйти
    python socks5_to_http.py --bind 0.0.0.0  # НЕ рекомендуется

В Telegram: тип SOCKS5, сервер 127.0.0.1, порт 55056,
логин/пароль — из .env (SOCKS_USER / SOCKS_PASS), если заданы.

Конфиг берётся из .env рядом со скриптом (или из переменных окружения):
    PROXIES=user:pass@host:port;host:port;...
    SOCKS_PORT=55056
    SOCKS_HOST=127.0.0.1
    AUTH_BYPASS=127.0.0.1/32,192.168.0.0/24
    SOCKS_USER=mikech
    SOCKS_PASS=...
    TEST_TARGET=149.154.167.51:443,149.154.175.50:443
Зависимостей нет — только стандартная библиотека.
"""

import argparse
import asyncio
import base64
import hmac
import ipaddress
import logging
import os
import random
import re
import socket
import struct
import sys
import time
from urllib.parse import quote

log = logging.getLogger("s2h")

DEFAULTS = {
    "SOCKS_HOST": "127.0.0.1",
    "SOCKS_PORT": "55056",
    "TEST_TARGET": "149.154.167.51:443,149.154.175.50:443",
    "AUTH_BYPASS": "",
    "SOCKS_USER": "",
    "SOCKS_PASS": "",
}

# Эти сети ходят без пароля (свой компьютер, своя Wi-Fi). 127.0.0.1 — всегда.
BYPASS_NETS = []

# Логин/пароль SOCKS5 (RFC 1929). Пусто = без авторизации.
AUTH_USER = ""
AUTH_PASS = ""


def bypass_ok(ip):
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    return any(addr in net for net in BYPASS_NETS)


def detect_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"

# --------------------------------------------------------------------------
# конфиг
# --------------------------------------------------------------------------

def _strip_comment(value):
    """Убирает комментарий в конце строки: 'текст # пояснение' -> 'текст'.

    Решётка внутри слова (x#y) и внутри кавычек комментарием не считается.
    """
    quote = None
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == '#' and i > 0 and value[i - 1] in (' ', '\t'):
            return value[:i].rstrip()
    return value.strip()


def load_env(path):
    """Парсер .env.

    Понимает:
      KEY=value
      KEY=value   # комментарий в конце строки
      # целая строка-комментарий
      PROXY=...   (несколько строк — список прокси, по одному на строку)
    """
    cfg = {}
    proxies = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = _strip_comment(val.strip()).strip('"').strip("'")
                if key == "PROXY":
                    if val:
                        proxies.append(val)
                else:
                    cfg[key] = val
    except FileNotFoundError:
        pass
    if proxies:
        base = cfg.get("PROXIES", "").strip()
        cfg["PROXIES"] = ";".join([base] + proxies) if base else ";".join(proxies)
    return cfg


def load_config():
    """Только .env. Никаких переменных окружения — всё в одном файле."""
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = dict(DEFAULTS)
    for name in (".env", os.path.join(here, ".env")):
        cfg.update(load_env(name))
    return cfg


# --------------------------------------------------------------------------
# прокси
# --------------------------------------------------------------------------

class Proxy:
    __slots__ = ("host", "port", "user", "password", "alive", "fails", "latency")

    def __init__(self, host, port, user="", password=""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.alive = True
        self.fails = 0
        self.latency = None

    @property
    def addr(self):
        return f"{self.host}:{self.port}"

    def __str__(self):
        return self.addr


def parse_proxies(raw):
    """user:pass@host:port;host:port;...

    Комментарии: строки и элементы, начинающиеся с #, пропускаются,
    хвостовой комментарий после пробела тоже отбрасывается.
    """
    result = []
    for item in raw.replace("\n", ";").split(";"):
        item = item.strip()
        if not item or item.startswith("#"):
            continue
        item = re.split(r"\s+#", item)[0].strip()
        if not item:
            continue
        m = re.match(r"^(.+?):(.+?)@\[?([0-9a-fA-F:.]+)\]?:(\d+)$", item)
        if m:
            result.append(Proxy(m.group(3), int(m.group(4)), m.group(1), m.group(2)))
            continue
        m = re.match(r"^\[?([0-9a-fA-F:.]+)\]?:(\d+)$", item)
        if m:
            result.append(Proxy(m.group(1), int(m.group(2))))
            continue
        log.warning("Не разобрал строку прокси: %s", item)
    return result


def parse_targets(raw):
    targets = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.rpartition(":")
        if not host:
            continue
        targets.append((host, int(port)))
    return targets or [("149.154.167.51", 443)]


# --------------------------------------------------------------------------
# HTTP CONNECT
# --------------------------------------------------------------------------

def _bracket(host):
    return f"[{host}]" if ":" in host else host


async def http_connect(proxy, host, port, timeout=15.0):
    """Открыть туннель до host:port через HTTP-прокси. Возвращает (reader, writer)."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(proxy.host, proxy.port), timeout)
    try:
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

        target = f"{_bracket(host)}:{port}"
        lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
        if proxy.user:
            token = base64.b64encode(
                f"{proxy.user}:{proxy.password}".encode()).decode()
            lines.append(f"Proxy-Authorization: Basic {token}")
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
        await writer.drain()

        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        status = head.split(b"\r\n", 1)[0].split()
        if len(status) < 2 or status[1] != b"200":
            raise ConnectionError(
                head.split(b"\r\n", 1)[0].decode("latin-1", "replace"))
    except BaseException:
        writer.close()
        raise
    # Всё, что после заголовков, осталось в reader — оно уйдёт клиенту как есть.
    return reader, writer


class Pool:
    def __init__(self, proxies, targets, interval=60):
        self.proxies = proxies
        self.targets = targets
        self.interval = interval
        self._task = None

    async def check_one(self, proxy, timeout=8.0):
        started = time.monotonic()
        for host, port in self.targets:
            try:
                _, writer = await http_connect(proxy, host, port, timeout)
                writer.close()
                proxy.alive = True
                proxy.fails = 0
                proxy.latency = time.monotonic() - started
                return True
            except (OSError, asyncio.TimeoutError, ConnectionError, EOFError):
                continue
        proxy.fails += 1
        if proxy.alive:
            log.warning("Прокси мёртв: %s", proxy.addr)
        proxy.alive = False
        proxy.latency = None
        return False

    async def check_all(self):
        if not self.proxies:
            return
        await asyncio.gather(*(self.check_one(p) for p in self.proxies))
        alive = sum(1 for p in self.proxies if p.alive)
        log.info("Health check: %d/%d живых", alive, len(self.proxies))

    async def _loop(self):
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.check_all()
            except Exception as e:  # noqa: BLE001
                log.exception("health check упал: %s", e)

    def start(self):
        self._task = asyncio.create_task(self._loop())

    def pick(self):
        alive = [p for p in self.proxies if p.alive]
        return random.choice(alive or self.proxies) if self.proxies else None

    async def dial(self, host, port, attempts=4):
        """Выбрать живой прокси и открыть туннель. Порт 443 — запасной вариант."""
        if not self.proxies:
            raise ConnectionError("нет ни одного прокси в PROXIES")
        candidates = [p for p in self.proxies if p.alive] or list(self.proxies)
        random.shuffle(candidates)
        ports = [port] if port == 443 else [port, 443]
        log.debug("dial %s:%s, кандидатов %d", host, port, min(len(candidates), attempts))
        last = None
        for proxy in candidates[:attempts]:
            for try_port in ports:
                try:
                    reader, writer = await http_connect(proxy, host, try_port)
                except (OSError, asyncio.TimeoutError, ConnectionError, EOFError) as e:
                    last = e
                    continue
                if try_port != port:
                    log.debug("%s:%s недоступен, ушёл на 443", host, port)
                log.info("туннель %s:%s через %s", host, try_port, proxy.addr)
                return reader, writer
            log.warning("Прокси не пустил %s:%s (%s)", host, port, last)
        raise ConnectionError(f"не удалось пройти ни через один прокси: {last}")


# --------------------------------------------------------------------------
# SOCKS5
# --------------------------------------------------------------------------

async def read_target(reader, atyp):
    if atyp == 0x01:
        host = ".".join(str(b) for b in await reader.readexactly(4))
    elif atyp == 0x03:
        length = (await reader.readexactly(1))[0]
        host = (await reader.readexactly(length)).decode("idna")
    elif atyp == 0x04:
        host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
    else:
        raise ValueError(f"неизвестный ATYP {atyp}")
    port = struct.unpack("!H", await reader.readexactly(2))[0]
    return host, port


SOCKS_OK = b"\x05\x00\x00\x01" + b"\x00" * 6
SOCKS_FAIL = b"\x05\x01\x00\x01" + b"\x00" * 6


async def pipe(src, dst, tag=""):
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (OSError, asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        try:
            dst.close()
        except (OSError, RuntimeError):
            pass


async def handle_client(reader, writer, pool):
    peer = writer.get_extra_info("peername")
    upstream = None
    try:
        ver, nmethods = await asyncio.wait_for(reader.readexactly(2), 15)
        if ver != 5:
            return
        methods = await reader.readexactly(nmethods)
        need_auth = bool(AUTH_USER) and not bypass_ok(peer[0])

        if need_auth:
            if 0x02 not in methods:
                writer.write(b"\x05\xff")
                await writer.drain()
                return
            method = 0x02
        elif 0x00 in methods:
            method = 0x00
        elif 0x02 in methods:
            method = 0x02
        else:
            writer.write(b"\x05\xff")
            await writer.drain()
            return

        writer.write(b"\x05" + bytes([method]))
        await writer.drain()
        log.debug("%s: метод %02x", peer[0], method)

        if method == 0x02:
            ver, ulen = await asyncio.wait_for(reader.readexactly(2), 15)
            uname = (await reader.readexactly(ulen)).decode("utf-8", "replace")
            plen = (await reader.readexactly(1))[0]
            passwd = (await reader.readexactly(plen)).decode("utf-8", "replace")
            ok = (ver == 1
                  and hmac.compare_digest(uname, AUTH_USER)
                  and hmac.compare_digest(passwd, AUTH_PASS))
            writer.write(b"\x01\x00" if ok else b"\x01\x01")
            await writer.drain()
            if not ok:
                log.warning("%s: неверный логин/пароль", peer[0])
                return

        ver, cmd, _rsv, atyp = await asyncio.wait_for(reader.readexactly(4), 15)
        if ver != 5 or cmd != 0x01:
            writer.write(b"\x05\x07" + b"\x00" * 8)
            await writer.drain()
            return
        host, port = await read_target(reader, atyp)
        log.debug("%s: запрос %s:%s", peer[0], host, port)

        try:
            up_reader, up_writer = await pool.dial(host, port)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: нет туннеля до %s:%s — %s", peer, host, port, e)
            writer.write(SOCKS_FAIL)
            await writer.drain()
            return
        upstream = up_writer

        writer.write(SOCKS_OK)
        await writer.drain()
        log.debug("%s -> %s:%s", peer, host, port)

        await asyncio.gather(
            pipe(reader, up_writer),
            pipe(up_reader, writer),
        )
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, OSError) as e:
        log.debug("%s: соединение закрыто (%s)", peer[0], type(e).__name__)
    except Exception as e:  # noqa: BLE001
        log.exception("%s: %s", peer, e)
    finally:
        if upstream is not None:
            try:
                upstream.close()
            except OSError:
                pass
        try:
            writer.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# режим самопроверки
# --------------------------------------------------------------------------

async def run_test(cfg, proxies, targets):
    if not proxies:
        print("PROXIES пустой — нечего проверять.")
        return 1
    print(f"Прокси в списке: {len(proxies)}", flush=True)
    print(f"Цели проверки: {', '.join(f'{h}:{p}' for h, p in targets)}\n", flush=True)
    pool = Pool(proxies, targets)
    await pool.check_all()
    for proxy in proxies:
        mark = "OK " if proxy.alive else "FAIL"
        lat = f"{proxy.latency * 1000:.0f} ms" if proxy.latency else "-"
        print(f"  [{mark}] {proxy.addr:>22}  {lat}", flush=True)
    alive = sum(1 for p in proxies if p.alive)
    print(f"\nЖивых: {alive}/{len(proxies)}", flush=True)
    return 0 if alive else 2


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def load_access(cfg):
    global AUTH_USER, AUTH_PASS
    AUTH_USER = cfg.get("SOCKS_USER", "")
    AUTH_PASS = cfg.get("SOCKS_PASS", "")
    BYPASS_NETS.clear()
    for item in re.split(r"[,;\s]+", cfg.get("AUTH_BYPASS", "")):
        item = item.strip()
        if not item:
            continue
        try:
            BYPASS_NETS.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            log.warning("AUTH_BYPASS: не понял %r", item)


def socks_link(bind=None, port=None, host=None):
    """Ссылка tg://socks для текущего конфига (для трея и логов)."""
    cfg = load_config()
    port = port or int(cfg.get("SOCKS_PORT", DEFAULTS["SOCKS_PORT"]))
    if host:
        server = host
    else:
        bind = bind or cfg.get("SOCKS_HOST", DEFAULTS["SOCKS_HOST"])
        server = detect_lan_ip() if bind in ("0.0.0.0", "::", "") else bind
    link = f"tg://socks?server={server}&port={port}"
    user = cfg.get("SOCKS_USER", "")
    if user:
        link += f"&user={quote(user)}&pass={quote(cfg.get('SOCKS_PASS', ''))}"
    return link


async def start(bind=None, port=None):
    """Поднять SOCKS5 в текущем event loop. Возвращает (server, pool)."""
    cfg = load_config()
    proxies = parse_proxies(cfg.get("PROXIES", ""))
    targets = parse_targets(cfg.get("TEST_TARGET", DEFAULTS["TEST_TARGET"]))
    load_access(cfg)
    if not proxies:
        raise RuntimeError("в .env нет PROXIES")

    bind = bind or cfg.get("SOCKS_HOST", DEFAULTS["SOCKS_HOST"])
    port = port or int(cfg.get("SOCKS_PORT", DEFAULTS["SOCKS_PORT"]))

    pool = Pool(proxies, targets)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, pool), bind, port)
    pool.start()
    asyncio.create_task(pool.check_all())   # проверка не задерживает старт
    log.info("SOCKS5 слушает %s",
             ", ".join(str(s.getsockname()) for s in server.sockets))
    return server, pool


async def amain(args):
    cfg = load_config()
    proxies = parse_proxies(cfg.get("PROXIES", ""))
    targets = parse_targets(cfg.get("TEST_TARGET", DEFAULTS["TEST_TARGET"]))

    if args.test:
        return await run_test(cfg, proxies, targets)

    if not proxies:
        log.error("В .env нет PROXIES — работать некуда.")
        return 2

    server, _pool = await start(args.bind, args.port)
    if AUTH_USER:
        log.info("Пароль требуется всем, кроме: %s",
                 ", ".join(map(str, BYPASS_NETS)) or "никого")
    else:
        log.info("Авторизация SOCKS5: выключена")
    link = socks_link(args.bind, args.port)
    log.info("В Telegram: тип SOCKS5, %s", link)
    log.info("Веб-вариант: %s", link.replace("tg://socks?", "https://t.me/socks?"))
    async with server:
        await server.serve_forever()
    return 0


def main():
    parser = argparse.ArgumentParser(description="SOCKS5 -> HTTP CONNECT конвертер")
    parser.add_argument("--port", type=int, help="порт SOCKS5 (по умолчанию 55056)")
    parser.add_argument("--bind", help="адрес прослушивания (по умолчанию 127.0.0.1)")
    parser.add_argument("--test", action="store_true",
                        help="только проверить прокси и выйти")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if sys.platform == "win32":
        # чтобы русские логи читались в cmd (cp866), а не превращались в кракозябры
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        if sys.version_info < (3, 14):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        sys.exit(asyncio.run(amain(args)))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
