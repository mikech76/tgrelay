# tgrelay for desktop (Windows / Linux)

The same idea as the Android app, but for a computer: one process starts
**two proxies at once**, both using your pool of HTTP CONNECT proxies.

| Type | Default port | Used by |
|---|---|---|
| **MTProto** | 55055 | Telegram (desktop and phone) — proxy type "MTProto" with a secret |
| **SOCKS5** | 55056 | Telegram — proxy type "SOCKS5" (no secret, optional login/password) |

```
Telegram --> [MTProto 55055] \
                              --> HTTP CONNECT pool --> Telegram DC
Telegram --> [SOCKS5 55056]  /
```

The MTProto part decrypts the handshake (the protocol requires it: the client
encrypts with the secret). The SOCKS5 part decrypts nothing — it only relays
address and port.

**Русская версия: [README.ru.md](README.ru.md)**

## Windows: quick start

1. Install Python 3 from <https://python.org> (check "Add python.exe to PATH").
2. Copy the `desktop` folder anywhere.
3. Double-click `start.cmd`.
4. On the first run it creates `.env` and opens it in Notepad. Fill in:
   - `PROXY=` lines — your HTTP proxies, one per line;
   - leave `SECRET` empty — the program will offer to generate it.
5. Save, run `start.cmd` again.

A tray icon appears. Right click it:

- **Copy MTProto link** — link for Telegram;
- **Copy SOCKS link (Wi-Fi)** — for devices in the same network;
- **Copy SOCKS link (моб. сеть)** — link with the external name (see below);
- **QR** — the same as a QR code.

Autostart: put a shortcut to `run.pyw` into the Startup folder
(`Win+R` → `shell:startup`).

## Linux: installation

```bash
cd desktop
chmod +x install-linux.sh
./install-linux.sh        # creates venv, installs deps, asks for .env
nano .env                 # proxies + secret
./install-linux.sh        # second run installs the systemd service
```

Manage it:

```bash
systemctl status tgrelay
systemctl restart tgrelay
journalctl -u tgrelay -f
```

Run manually without systemd:

```bash
./venv/bin/python run_headless.py
```

## Settings: one `.env` file

Everything is in one file — proxies, ports, external name. No environment variables.

```ini
# 1. PROXIES (one per line)
PROXY=user:password@1.2.3.4:9405     # primary
PROXY=user:password@5.6.7.8:9829     # backup
# PROXY=9.9.9.9:8080                 # disabled

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

| Key | Meaning |
|---|---|
| `PROXY` | one HTTP CONNECT proxy per line (`login:password@host:port` or `host:port`) |
| `PROXY_PORT` | MTProto port (default 55055) |
| `SOCKS_PORT` | SOCKS5 port (default 55056) |
| `SOCKS_HOST` | SOCKS5 listen address |
| `SECRET` | MTProto secret; if empty, it is generated and written here |
| `EXTERNAL_HOST` | DDNS name or external IP used in links |
| `AUTH_BYPASS` | networks allowed to use SOCKS5 without a password |
| `SOCKS_USER` / `SOCKS_PASS` | login/password for everyone else |

The old one-line format is still supported:
`PROXIES=user:pass@1.2.3.4:9405;5.6.7.8:8080`.

### Comments in `.env`

```ini
# a whole line is a comment
SECRET=9d4e215aeba83fe52b0764a4d1e5bdd3   # trailing comment is ignored

PROXY=user:pass@1.2.3.4:9405        # this one is enabled
# PROXY=user:pass@9.9.9.9:1234      # this one is disabled
```

If you keep several proxies in a single `PROXIES=` line, disable one with `#`
immediately after `;` — without a space:

```ini
PROXIES=user:pass@1.2.3.4:9405;#user:pass@9.9.9.9:1234;user:pass@5.6.7.8:8080
```

A `#` **preceded by a space** cuts the rest of the line, so do not put a space
before it when disabling a single entry inside a list.

### MTProto secret

The secret is 32 hex characters (16 bytes). It is not a password but key
material: anyone who knows it can use your proxy.

If `SECRET` is empty, on the first launch the program asks:

```
В .env не задан SECRET для MTProto-прокси.
Сгенерировать новый ключ? [Y/n]:
```

Answer `Y` (or press Enter) and the key is generated and written into `.env`.
If you answer `n`, the program stops so you can set your own value.

Under a GUI/service (no console) the key is generated automatically and written
to `.env`.

## Connecting Telegram

**Computer (Telegram Desktop):**

- MTProto: `tg://proxy?server=127.0.0.1&port=55055&secret=<SECRET>`
- SOCKS5: `tg://socks?server=127.0.0.1&port=55056` (if `SOCKS_USER` is empty)

The tray always builds links with the correct address and secret.

**Phone in the same Wi-Fi:**

Server `192.168.x.x` (the computer's address), port `55055` (MTProto with the
secret) or `55056` (SOCKS5). If `SOCKS_USER` is set, the password is required —
`AUTH_BYPASS` only covers addresses from the list.

## Access from other networks (optional)

By default everything works only inside the local network. To connect from
outside (for example, Telegram Desktop on another computer), two things are needed.

**1. Port forwarding on the router.** Open the router's web interface and find
"Port Forwarding" / "Virtual Servers":

| Field | Value |
|---|---|
| External port | 55055 (MTProto) and/or 55056 (SOCKS5) |
| Internal IP | the computer's LAN address, e.g. `192.168.1.10` |
| Internal port | the same |
| Protocol | TCP |

Pin the computer's address in DHCP, otherwise it changes after a reboot.

**2. DDNS name.** A home IP changes, so dynamic DNS is used:

- <https://www.duckdns.org> — free, gives a name like `yourname.duckdns.org`;
- <https://www.noip.com> — free tier as well.

Put the name into `.env`:

```ini
EXTERNAL_HOST=yourname.duckdns.org
```

After a restart the tray links use this address.

**Before exposing anything to the internet:**

- set `SOCKS_USER` and `SOCKS_PASS`, otherwise your SOCKS5 becomes an open proxy
  for the whole internet;
- keep in mind that an MTProto proxy without fake-TLS (a secret without the `ee`
  prefix) is recognisable by DPI systems;
- never publish your secret or proxy list.

## Limitations

- Telegram calls do not work through a proxy.
- The MTProto part does not implement fake-TLS (`ee`), so traffic is not disguised
  as HTTPS.
- Speed is limited by your proxies.
- On some mobile carriers DPI drops HTTP CONNECT to Telegram addresses.

## Troubleshooting

Windows log: `tgrelay.log` next to the scripts.
Linux log: `journalctl -u tgrelay -f`.

Check the proxy pool without starting the server:

```bash
python socks5_to_http.py --test
```
