import asyncio
import logging

import socks5_to_http
import status
from i18n import t
from mtproto_handler import MTProtoHandler
from proxy_pool import (ProxyPool, get_external_ip, load_secret, port_value)

logger = logging.getLogger(__name__)

proxy_pool_instance = ProxyPool()
handler = None
secret = None


async def start_server():
    """Поднять включённые протоколы. Порт можно отключить в tgrelay.txt."""
    global handler, secret

    mt_port = port_value('PROXY_PORT', 55055)
    socks_port = port_value('SOCKS_PORT', 55056)
    if mt_port is None and socks_port is None:
        raise RuntimeError(t('no_protocols'))

    status.register(proxy_pool_instance)
    servers = []

    if mt_port is not None:
        secret = load_secret()
        handler = MTProtoHandler(secret, proxy_pool_instance)
        mt_server = await asyncio.start_server(
            handler.handle, host='0.0.0.0', port=mt_port)
        addrs = ', '.join(str(s.getsockname()) for s in mt_server.sockets)
        logger.info("MTProto listening on %s", addrs)
        print(f"MTProto listening on {addrs}")
        servers.append(mt_server)
    else:
        logger.info("MTProto disabled (PROXY_PORT)")
        print("MTProto disabled (PROXY_PORT)")

    print(f"Proxies loaded: {proxy_pool_instance.count} "
          f"({proxy_pool_instance.alive_count} alive)")

    if socks_port is not None:
        socks_server, _socks_pool = await socks5_to_http.start(port=socks_port)
        logger.info("SOCKS5 listening on %s",
                    ', '.join(str(s.getsockname()) for s in socks_server.sockets))
        servers.append(socks_server)
    else:
        logger.info("SOCKS5 disabled (SOCKS_PORT)")
        print("SOCKS5 disabled (SOCKS_PORT)")

    if socks_port is not None:
        print(f"SOCKS5 link: {socks5_to_http.socks_link(port=socks_port)}")
    if mt_port is not None:
        print(f"MTProto link: tg://proxy?server={get_external_ip()}"
              f"&port={mt_port}&secret={secret.hex()}")

    try:
        await asyncio.gather(*(server.serve_forever() for server in servers))
    finally:
        for server in servers:
            server.close()
