import asyncio
import base64


async def http_connect(proxy, target_host, target_port,
                       timeout=15):
    fut = asyncio.open_connection(proxy['host'], proxy['port'])
    reader, writer = await asyncio.wait_for(fut, timeout=timeout)

    req = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
    )
    if proxy.get('user'):
        auth_raw = f"{proxy['user']}:{proxy['password']}"
        auth_b64 = base64.b64encode(auth_raw.encode()).decode()
        req += f"Proxy-Authorization: Basic {auth_b64}\r\n"
    req += "\r\n"
    writer.write(req.encode())
    await writer.drain()

    resp = await asyncio.wait_for(
        reader.readuntil(b'\r\n\r\n'), timeout=timeout)
    status = resp.split(b'\r\n')[0].decode()
    if '200' not in status:
        writer.close()
        raise ConnectionError(f"HTTP proxy error: {status}")

    return reader, writer
