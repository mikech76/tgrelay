"""Туннель до цели через апстрим-прокси: HTTP CONNECT, SOCKS5 или SOCKS4.

Строка прокси в конфиге понимает схему и без схемы:

    user:pass@host:port          — определить автоматически (HTTP → SOCKS5 → SOCKS4)
    http://user:pass@host:port   — HTTP CONNECT
    https://...                  — HTTP CONNECT, при отказе — тот же CONNECT по TLS
    socks5://...  socks5h://...  — SOCKS5
    socks://...                  — тоже SOCKS5 (пятёрка по умолчанию)
    socks4://...  socks4a://...  — SOCKS4 (4a: имя узла отдаётся прокси)

Порт можно не писать: http 8080, https 443, socks5/socks4 1080.
"""
import asyncio
import base64
import ipaddress
import re
import ssl

# какие схемы понимаем; socks:// без номера — SOCKS5
SCHEMES = {
    'http': 'http',
    'https': 'https',
    'socks': 'socks5',
    'socks5': 'socks5',
    'socks5h': 'socks5',
    'socks4': 'socks4',
    'socks4a': 'socks4',
}

DEFAULT_PORTS = {'http': 8080, 'https': 443, 'socks5': 1080, 'socks4': 1080}

# порядок автоопределения: сначала HTTP — так работает большинство дешёвых прокси
AUTO_ORDER = ('http', 'socks5', 'socks4')

_KIND_NAMES = {
    'http': 'HTTP CONNECT',
    'https': 'HTTPS CONNECT',
    'socks5': 'SOCKS5',
    'socks4': 'SOCKS4',
}


def parse_line(text):
    """Разобрать строку прокси. None — пустая строка/комментарий.

    ValueError — схема незнакомая или адрес битый: вызывающий пишет это в лог.
    """
    item = re.split(r'\s+#', text.strip())[0].strip()
    if not item or item.startswith('#'):
        return None

    scheme = ''
    if '://' in item:
        scheme, item = item.split('://', 1)
        scheme = scheme.strip().lower()

    user = password = ''
    if '@' in item:
        auth, item = item.rsplit('@', 1)
        if ':' in auth:
            user, password = auth.split(':', 1)
        else:
            user = auth

    if item.startswith('['):                     # [IPv6]:port
        host, _, tail = item[1:].partition(']')
        port = tail.lstrip(':')
    else:
        host, sep, tail = item.rpartition(':')
        if not sep:
            host, port = item, ''
        elif re.fullmatch(r'\d{1,5}', tail):
            port = tail
        elif ':' in item:                        # голый IPv6 без порта
            host, port = item, ''
        else:
            host, port = item, ''

    host = host.strip().strip('[]')
    if not host or ' ' in host or '/' in host:
        raise ValueError(f'не разобрал адрес: {text.strip()}')

    kind = SCHEMES.get(scheme) if scheme else None
    if scheme and kind is None:
        raise ValueError(f'неизвестная схема {scheme}:// (есть http, https, '
                         f'socks, socks5, socks4)')

    if port:
        if not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(f'плохой порт: {text.strip()}')
        port = int(port)
    else:
        port = DEFAULT_PORTS.get(kind or 'http', 0)
        if not port:
            raise ValueError(f'не указан порт: {text.strip()}')

    return {'host': host, 'port': port, 'user': user,
            'password': password, 'kind': kind}


def describe(proxy):
    """Строка для лога: «HTTP CONNECT 1.2.3.4:8080» или «авто ...»."""
    kind = _get(proxy, 'kind')
    name = _KIND_NAMES.get(kind or '', 'авто')
    return f"{name} {_get(proxy, 'host')}:{_get(proxy, 'port')}"


def kind_name(proxy):
    return _KIND_NAMES.get(_get(proxy, 'kind') or '', 'авто')


def _get(proxy, key, default=None):
    try:
        value = proxy[key]
    except (TypeError, KeyError, IndexError):
        value = getattr(proxy, key, default)
    return default if value is None else value


def _set_kind(proxy, kind):
    try:
        proxy.kind = kind
    except AttributeError:
        try:
            proxy['kind'] = kind
        except (TypeError, KeyError):
            pass


# ---------------------------------------------------------------------------
#  публичная точка входа
# ---------------------------------------------------------------------------

async def open_tunnel(proxy, host, port, timeout=15.0):
    """Открыть туннель до host:port через прокси. Возвращает (reader, writer)."""
    kind = (_get(proxy, 'kind') or '').lower()

    if kind in _KIND_NAMES:
        return await _connect(proxy, host, port, timeout, kind)

    # схема не указана — пробуем по очереди и запоминаем, что сработало
    errors = []
    probe_timeout = min(timeout, 4.0)
    for attempt in AUTO_ORDER:
        try:
            result = await _connect(proxy, host, port, probe_timeout, attempt)
        except (OSError, asyncio.TimeoutError, ConnectionError, EOFError) as e:
            errors.append(f'{_KIND_NAMES[attempt]}: {e}')
            continue
        _set_kind(proxy, attempt)
        return result
    raise ConnectionError('прокси не отвечает ни как HTTP, ни как SOCKS — '
                          + '; '.join(errors))


async def _connect(proxy, host, port, timeout, kind):
    if kind == 'http':
        return await http_connect(proxy, host, port, timeout)
    if kind == 'https':
        try:
            return await http_connect(proxy, host, port, timeout)
        except (OSError, asyncio.TimeoutError, EOFError):
            # часть провайдеров держит CONNECT за TLS
            return await http_connect(proxy, host, port, timeout, tls=True)
    if kind == 'socks5':
        return await socks5_connect(proxy, host, port, timeout)
    if kind == 'socks4':
        return await socks4_connect(proxy, host, port, timeout)
    raise ValueError(f'неизвестный тип прокси: {kind}')


# ---------------------------------------------------------------------------
#  HTTP CONNECT
# ---------------------------------------------------------------------------

def _bracket(host):
    return f'[{host}]' if ':' in host else host


async def http_connect(proxy, host, port, timeout=15.0, tls=False):
    """CONNECT через HTTP-прокси. tls=True — тот же запрос по TLS."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(
            _get(proxy, 'host'), _get(proxy, 'port'),
            ssl=_tls_context() if tls else None),
        timeout)
    try:
        _nodelay(writer)
        target = f'{_bracket(host)}:{port}'
        lines = [f'CONNECT {target} HTTP/1.1', f'Host: {target}']
        user = _get(proxy, 'user', '')
        if user:
            token = base64.b64encode(
                f'{user}:{_get(proxy, "password", "")}'.encode()).decode()
            lines.append(f'Proxy-Authorization: Basic {token}')
        writer.write(('\r\n'.join(lines) + '\r\n\r\n').encode())
        await writer.drain()

        head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout)
        status = head.split(b'\r\n', 1)[0].split()
        if len(status) < 2 or status[1] != b'200':
            raise ConnectionError(
                head.split(b'\r\n', 1)[0].decode('latin-1', 'replace'))
    except BaseException:
        writer.close()
        raise
    return reader, writer


# ---------------------------------------------------------------------------
#  SOCKS5 (RFC 1928 + RFC 1929)
# ---------------------------------------------------------------------------

async def socks5_connect(proxy, host, port, timeout=15.0):
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(_get(proxy, 'host'), _get(proxy, 'port')),
        timeout)
    try:
        _nodelay(writer)
        user = str(_get(proxy, 'user', '') or '')
        password = str(_get(proxy, 'password', '') or '')

        methods = b'\x00\x02' if user else b'\x00'
        writer.write(b'\x05' + bytes([len(methods)]) + methods)
        await writer.drain()

        head = await asyncio.wait_for(reader.readexactly(2), timeout)
        if head[0] != 5:
            raise ConnectionError('это не SOCKS5')
        method = head[1]
        if method == 0x02:
            if not user:
                raise ConnectionError('SOCKS5 требует логин и пароль')
            writer.write(b'\x01' + bytes([len(user)]) + user.encode()
                         + bytes([len(password)]) + password.encode())
            await writer.drain()
            answer = await asyncio.wait_for(reader.readexactly(2), timeout)
            if answer[1] != 0:
                raise ConnectionError('SOCKS5: неверный логин или пароль')
        elif method != 0x00:
            raise ConnectionError('SOCKS5: неподходящий способ авторизации')

        writer.write(b'\x05\x01\x00' + _socks5_addr(host)
                     + port.to_bytes(2, 'big'))
        await writer.drain()

        reply = await asyncio.wait_for(reader.readexactly(4), timeout)
        if reply[1] != 0:
            raise ConnectionError(f'SOCKS5: отказ ({_SOCKS5_ERRORS.get(reply[1], reply[1])})')
        atyp = reply[3]
        if atyp == 0x01:
            await asyncio.wait_for(reader.readexactly(4 + 2), timeout)
        elif atyp == 0x04:
            await asyncio.wait_for(reader.readexactly(16 + 2), timeout)
        elif atyp == 0x03:
            length = await asyncio.wait_for(reader.readexactly(1), timeout)
            await asyncio.wait_for(reader.readexactly(length[0] + 2), timeout)
        else:
            raise ConnectionError(f'SOCKS5: непонятный адрес в ответе ({atyp})')
    except BaseException:
        writer.close()
        raise
    return reader, writer


_SOCKS5_ERRORS = {
    1: 'общий сбой', 2: 'правило запрещает', 3: 'сеть недоступна',
    4: 'узел недоступен', 5: 'соединение отклонено',
    6: 'TTL истёк', 7: 'команда не поддерживается',
    8: 'тип адреса не поддерживается',
}


def _socks5_addr(host):
    """Адрес назначения для SOCKS5: IP как есть, имя — пусть резолвит прокси."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raw = host.encode('idna')
        return b'\x03' + bytes([len(raw)]) + raw
    if ip.version == 4:
        return b'\x01' + ip.packed
    return b'\x04' + ip.packed


# ---------------------------------------------------------------------------
#  SOCKS4 / 4a
# ---------------------------------------------------------------------------

async def socks4_connect(proxy, host, port, timeout=15.0):
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(_get(proxy, 'host'), _get(proxy, 'port')),
        timeout)
    try:
        _nodelay(writer)
        user = str(_get(proxy, 'user', '') or '')
        try:
            packed = ipaddress.IPv4Address(host).packed
            tail = b''
        except ValueError:
            packed = b'\x00\x00\x00\x01'          # SOCKS4a: имя узла дальше
            tail = host.encode('idna') + b'\x00'
        writer.write(b'\x04\x01' + port.to_bytes(2, 'big') + packed
                     + user.encode() + b'\x00' + tail)
        await writer.drain()

        answer = await asyncio.wait_for(reader.readexactly(8), timeout)
        if answer[1] != 0x5A:
            raise ConnectionError(f'SOCKS4: отказ ({answer[1]})')
    except BaseException:
        writer.close()
        raise
    return reader, writer


# ---------------------------------------------------------------------------

def _nodelay(writer):
    sock = writer.get_extra_info('socket')
    if sock is None:
        return
    try:
        import socket
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def _tls_context():
    """TLS до самого прокси: сертификат чужой, проверять нечего."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
