import asyncio
import logging

import socks5_to_http
from mtproto_handler import MTProtoHandler
from proxy_pool import ProxyPool, load_secret, config, get_external_ip

logger = logging.getLogger(__name__)

proxy_pool_instance = ProxyPool()
secret = load_secret()
handler = MTProtoHandler(secret, proxy_pool_instance)


def mtproto_port():
    """Порт MTProto берётся из .env (PROXY_PORT)."""
    return int(config.get("PROXY_PORT", "55055"))


async def start_server():
    port = mtproto_port()

    mt_server = await asyncio.start_server(
        handler.handle, host='0.0.0.0', port=port)
    addrs = ', '.join(str(s.getsockname()) for s in mt_server.sockets)
    logger.info(f"MTProto listening on {addrs}")
    print(f"MTProto listening on {addrs}")
    print(f"Proxies loaded: {proxy_pool_instance.count} "
          f"({proxy_pool_instance.alive_count} alive)")

    socks_server, _socks_pool = await socks5_to_http.start()
    logger.info("SOCKS5 listening on %s",
                ', '.join(str(s.getsockname()) for s in socks_server.sockets))
    print(f"SOCKS5 link: {socks5_to_http.socks_link()}")
    print(f"MTProto link: tg://proxy?server={get_external_ip()}"
          f"&port={port}&secret={secret.hex()}")

    try:
        await asyncio.gather(
            mt_server.serve_forever(),
            socks_server.serve_forever(),
        )
    finally:
        mt_server.close()
        socks_server.close()
