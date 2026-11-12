# tgrelay — Telegram proxy for Android and desktop

Two builds, one idea: take a cheap **HTTP CONNECT** proxy (which Telegram cannot use)
and turn it into something Telegram understands.

```
Telegram (SOCKS5) → 127.0.0.1:55056 → HTTP CONNECT + Basic auth → proxy provider → Telegram DC
```

**Русская версия: [README.ru.md](README.ru.md)**

## What is in this repository

| Folder | What it is |
|---|---|
| [`app/`](app/README.md) | Android app: one APK, local SOCKS5, no setup beyond a proxy list |
| [`desktop/`](desktop/README.md) | Windows and Linux: MTProto **and** SOCKS5 at the same time, shared proxy pool |

## Why this exists

1. **Telegram for Android has no "HTTP" proxy type.** Only SOCKS5, MTProto and WEB.
   A bought HTTP CONNECT proxy simply cannot be entered into the phone app.
   Desktop Telegram does have an HTTP field — the phone does not.
2. **MTProto proxies with a secret are sold separately and cost more.**
   SOCKS5 is often a separate, more expensive plan too.
3. **Cheap shared proxies often do not pass Telegram traffic**: they block
   datacenter addresses, non-standard ports or long-lived connections, and part
   of any pool is dead at any moment.

This project fixes all three: it converts HTTP CONNECT into SOCKS5 (and MTProto on
desktop), keeps a pool of proxies with retries and a fallback to port 443, so one
bad proxy does not take the messenger down.

Result: a cheap HTTP proxy (~39 RUB) plus this app ≈ a working Telegram proxy,
without buying an expensive MTProto plan.

## Android

1. Install the APK from **Releases**.
2. Open the app, paste your proxies (one per line), tap **Save list**.
3. Tap **Enable**, then **Set up Telegram**.

Details: [app/README.md](app/README.md).

## Desktop (Windows / Linux)

Windows:

```bat
start.cmd
```

Linux:

```bash
chmod +x install-linux.sh
./install-linux.sh
nano .env          # proxies + secret
./install-linux.sh # installs the systemd service
```

Two proxies start at once: MTProto on `55055`, SOCKS5 on `55056`.
Details: [desktop/README.md](desktop/README.md).

## Configuration (`.env`)

Everything lives in one file next to the program. Sections, comments and
one proxy per line:

```ini
# 1. PROXIES
PROXY=user:password@1.2.3.4:9405     # primary
PROXY=user:password@5.6.7.8:9829     # backup
# PROXY=9.9.9.9:8080                 # disabled: commented out

# 2. PORTS
PROXY_PORT=55055                     # MTProto
SOCKS_PORT=55056                     # SOCKS5
SOCKS_HOST=0.0.0.0                   # 127.0.0.1 = this PC only

# 3. MTProto SECRET
SECRET=                              # empty = generated on first run

# 4. EXTERNAL NAME (only if you forwarded the port)
EXTERNAL_HOST=                       # e.g. yourname.duckdns.org

# 5. SOCKS5 ACCESS
AUTH_BYPASS=127.0.0.1/32,192.168.0.0/24
SOCKS_USER=
SOCKS_PASS=
```

- Anything after ` #` is a comment.
- Full-line comments start with `#`.
- Comment out one proxy to disable it temporarily.
- Leave `SECRET` empty: on first launch the program offers to generate a key
  and writes it into `.env` for you.

## Where to buy proxies

Any provider of **HTTP CONNECT** proxies with username/password will work.

| What is offered | Works? |
|---|---|
| **HTTP / HTTP CONNECT**, shared IPv4 | yes — this is what the app needs |
| SOCKS5 | Telegram understands it directly; the app is not needed |
| MTProto with a secret | works without this app, but costs more |
| WEB proxy | needs your own domain and server |
| VPN | a different story |

Cheap option used by the author (referral link — the price for you does not change):

- **ProxyMania** — <https://proxymania.me/?r=58869>
- promo code: `USER-4eef3a9758c7dc2a` — **5% off**
- in the catalog choose: type **HTTP**, **shared IPv4**, any country, minimal term
- price: about **39 RUB** per proxy

After payment you get host, port, login and password. In the app it becomes one line:

```
user:password@1.2.3.4:9405
```

Buy 2–3 proxies: cheap shared proxies die regularly, a pool is noticeably
more stable than a single one.

## Limitations

- **Telegram calls do not work through a proxy** — a proxy limitation, not the app's.
  Text, photos, files and video work.
- Speed is limited by your proxies.
- The desktop MTProto part does not implement fake-TLS (`ee`), so traffic is not
  disguised as HTTPS.
- This is not a VPN: only Telegram uses the proxy, other apps go direct.
- On some mobile carriers DPI drops HTTP CONNECT to Telegram addresses; the proxy
  will not work over such a mobile network.

## Security

- The Android app listens on loopback only: unreachable from the LAN or the internet.
- Proxy passwords are stored locally on the device.
- The proxy provider sees your IP and traffic volume, not message contents:
  Telegram encryption is end-to-end.
- Never publish your proxy list or a build with it baked in.

## License

MIT — see [LICENSE](LICENSE).
