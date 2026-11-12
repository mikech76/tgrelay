import asyncio
import os
import hashlib
import logging
import struct

from Crypto.Cipher import AES
from Crypto.Util import Counter

from upstream_proxy import http_connect
from proxy_pool import ProxyPool, load_telegram_hosts

logger = logging.getLogger(__name__)

SKIP_LEN = 8
PREKEY_LEN = 32
IV_LEN = 16
HANDSHAKE_LEN = 64
PROTO_TAG_POS = 56

# Telegram DCs: indexes follow mtprotoproxy convention (abs(dc)-1)
TG_DC_HOSTS = {
    0: "149.154.175.50",  # DC 1
    1: "149.154.167.51",  # DC 2
    2: "149.154.175.100", # DC 3
    3: "149.154.167.91",  # DC 4
    4: "91.108.56.100",   # DC 5
}

PROTO_TAG_ABRIDGED = b'\xef\xef\xef\xef'
PROTO_TAG_INTERMEDIATE = b'\xee\xee\xee\xee'
PROTO_TAG_PADDED_INTERMEDIATE = b'\xdd\xdd\xdd\xdd'

VALID_PROTO_TAGS = {
    PROTO_TAG_ABRIDGED,
    PROTO_TAG_INTERMEDIATE,
    PROTO_TAG_PADDED_INTERMEDIATE,
}

RESERVED_FIRST_BYTES = {0xef}
RESERVED_STARTS = {
    b'\x48\x45\x41\x44',  # HEAD
    b'\x50\x4f\x53\x54',  # POST
    b'\x47\x45\x54\x20',  # 'GET '
    b'\xee\xee\xee\xee',
    b'\xdd\xdd\xdd\xdd',
    b'\x16\x03\x01\x02',
}
RESERVED_CONTINUE = b'\x00\x00\x00\x00'
ZERO_64 = b'\x00' * 64


def hexdump(label, data, maxlen=128):
    if logger.isEnabledFor(logging.DEBUG):
        dump = data[:maxlen].hex()
        tag = f"{label} ({len(data)}b)"
        logger.debug(f"{tag}: {dump}")


def _aes_ctr(key, iv):
    ctr = Counter.new(128, initial_value=int.from_bytes(iv, 'big'))
    return AES.new(key, AES.MODE_CTR, counter=ctr)


def generate_relay_init(proto_tag, dc_id=0):
    while True:
        rnd = bytearray(os.urandom(HANDSHAKE_LEN))
        if rnd[0] in RESERVED_FIRST_BYTES:
            continue
        if bytes(rnd[:4]) in RESERVED_STARTS:
            continue
        if rnd[4:8] == RESERVED_CONTINUE:
            continue
        break

    rnd_bytes = bytes(rnd)
    enc_key = rnd_bytes[SKIP_LEN:SKIP_LEN + PREKEY_LEN]
    enc_iv = rnd_bytes[SKIP_LEN + PREKEY_LEN:SKIP_LEN + PREKEY_LEN + IV_LEN]

    cipher = _aes_ctr(enc_key, enc_iv)
    encrypted_full = cipher.encrypt(rnd_bytes)

    keystream_tail = bytes(
        encrypted_full[i] ^ rnd_bytes[i] for i in range(56, 64))

    tail_plain = proto_tag + struct.pack('<h', dc_id) + os.urandom(2)
    encrypted_tail = bytes(
        tail_plain[i - 56] ^ keystream_tail[i - 56] for i in range(56, 64))

    result = bytearray(rnd_bytes)
    result[PROTO_TAG_POS:HANDSHAKE_LEN] = encrypted_tail
    return bytes(result)


class MTProtoHandler:
    def __init__(self, secret, proxy_pool):
        self.secret = secret
        self.proxy_pool = proxy_pool
        self.telegram_hosts = load_telegram_hosts()

    async def handle(self, reader, writer):
        peer = writer.get_extra_info('peername')
        logger.info(f"New connection from {peer}")
        try:
            await self._handle(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError,
                OSError, TimeoutError) as e:
            logger.warning(f"{peer} — {type(e).__name__}: {e}")
        except Exception as e:
            logger.exception(f"{peer} — unexpected: {e}")
        finally:
            try:
                writer.close()
            except:
                pass

    async def _handle(self, reader, writer):
        client_init = await reader.readexactly(HANDSHAKE_LEN)
        hexdump("C->P: init", client_init)

        # --- client-side decryption keys (SHA256 + secret) ---
        clt_dec_prekey = client_init[SKIP_LEN:SKIP_LEN + PREKEY_LEN]
        clt_dec_iv = client_init[SKIP_LEN + PREKEY_LEN:
                                  SKIP_LEN + PREKEY_LEN + IV_LEN]
        clt_dec_key = hashlib.sha256(clt_dec_prekey + self.secret).digest()
        logger.debug(f"prekey(8:40)={clt_dec_prekey.hex()} iv(40:56)={clt_dec_iv.hex()} key={clt_dec_key.hex()}")

        clt_decryptor = _aes_ctr(clt_dec_key, clt_dec_iv)
        decrypted_init = clt_decryptor.encrypt(client_init)
        hexdump("P: decrypted_init", decrypted_init)

        proto_tag = decrypted_init[PROTO_TAG_POS:PROTO_TAG_POS + 4]
        if proto_tag not in VALID_PROTO_TAGS:
            logger.warning(f"Unknown protocol tag: {proto_tag.hex()}")
            return
        logger.info(f"Client proto tag: {proto_tag.hex()}")

        # --- client-side encryption keys (reversed + SHA256 + secret) ---
        clt_enc_prekey_iv = client_init[SKIP_LEN:
                                        SKIP_LEN + PREKEY_LEN + IV_LEN][::-1]
        clt_enc_key = hashlib.sha256(
            clt_enc_prekey_iv[:PREKEY_LEN] + self.secret).digest()
        clt_enc_iv = clt_enc_prekey_iv[PREKEY_LEN:]
        clt_encryptor = _aes_ctr(clt_enc_key, clt_enc_iv)

        # fast-forward client decryptor past the 64-byte init
        # (the init was already processed by decrypt(), no additional skip needed)

        dc_id = struct.unpack('<h', decrypted_init[60:62])[0]
        logger.info(f"Client DC: {dc_id}")

        # --- generate relay init for TG server ---
        relay_init = generate_relay_init(proto_tag, dc_id)
        hexdump("P->TG: relay_init", relay_init)

        # --- TG-side encryption keys (RAW, no hash) ---
        tg_enc_key = relay_init[SKIP_LEN:SKIP_LEN + PREKEY_LEN]
        tg_enc_iv = relay_init[SKIP_LEN + PREKEY_LEN:
                               SKIP_LEN + PREKEY_LEN + IV_LEN]

        tg_dec_prekey_iv = relay_init[SKIP_LEN:
                                      SKIP_LEN + PREKEY_LEN + IV_LEN][::-1]
        tg_dec_key = tg_dec_prekey_iv[:PREKEY_LEN]
        tg_dec_iv = tg_dec_prekey_iv[PREKEY_LEN:]

        tg_encryptor = _aes_ctr(tg_enc_key, tg_enc_iv)
        tg_decryptor = _aes_ctr(tg_dec_key, tg_dec_iv)

        # fast-forward TG encryptor past the relay init
        tg_encryptor.encrypt(ZERO_64)

        # --- connect upstream ---
        dc_index = abs(dc_id) - 1
        dc_index = max(0, min(dc_index, len(TG_DC_HOSTS) - 1))
        tg_host = TG_DC_HOSTS.get(dc_index, self.telegram_hosts[0][0])

        proxy = self.proxy_pool.get()
        if not proxy:
            logger.error("No upstream proxies available")
            return

        logger.info(f"Upstream: {proxy['host']}:{proxy['port']} → "
                     f"{tg_host}:443")
        up_r, up_w = await http_connect(proxy, tg_host, 443)
        logger.info("Upstream CONNECT OK")

        # send relay init to TG server
        hexdump("up_w: relay_init (raw)", relay_init)
        up_w.write(relay_init)
        await up_w.drain()

        # TG encryptor was pre-advanced by 64 above (via ZERO_64).
        # TG decryptor starts at position 0 — the relay's TG→C pipe
        # will read TG's 64-byte response init, decrypt at pos 0,
        # re-encrypt with clt_encryptor at pos 0, and forward to client,
        # advancing both to position 64.

        # --- relay client↔TG with re-encryption ---
        # client→TG:  clt_decrypt → tg_encrypt
        # TG→client:  tg_decrypt → clt_encrypt
        logger.info("Starting relay")
        await asyncio.gather(
            self._pipe(reader, up_w, clt_decryptor, tg_encryptor,
                       name="C->TG"),
            self._pipe(up_r, writer, tg_decryptor, clt_encryptor,
                       name="TG->C", timeout=30),
        )

    async def _pipe(self, src, dst, decryptor, encryptor, name="",
                    timeout=None):
        try:
            while True:
                if timeout:
                    data = await asyncio.wait_for(
                        src.read(65536), timeout=timeout)
                else:
                    data = await src.read(65536)
                if not data:
                    break
                hexdump(f"{name} raw", data, maxlen=32)
                plain = decryptor.encrypt(data)
                hexdump(f"{name} plain", plain, maxlen=32)
                encrypted = encryptor.encrypt(plain)
                hexdump(f"{name} enc→dst", encrypted, maxlen=32)
                dst.write(encrypted)
                await dst.drain()
        except (ConnectionError, asyncio.IncompleteReadError,
                OSError, TimeoutError):
            pass
        finally:
            logger.debug(f"{name} pipe closed")
            try:
                dst.close()
            except:
                pass
