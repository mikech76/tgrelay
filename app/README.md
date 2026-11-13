# tgrelay for Android

A local SOCKS5 proxy for Telegram: the phone runs a server on `127.0.0.1:55056`
and forwards traffic through your pool of HTTP CONNECT proxies.

**Русская версия: [README.ru.md](README.ru.md)**

## Install

1. Download the APK from **Releases**.
2. Allow installation from unknown sources and install it.
3. Open the app.

## Setup

1. Paste your proxies into the "Прокси" field — one per line:

   ```
   user:password@1.2.3.4:9405
   5.6.7.8:8080
   ```

   Comments are allowed: a line starting with `#` is ignored, and everything
   after ` #` is ignored too. Comment out a proxy to disable it temporarily.

2. Tap **Save list** (Сохранить список).
3. Tap **Enable** (Включить) — a persistent notification appears.
4. Tap **Set up Telegram** (Настроить Telegram) and confirm the proxy.

Manual setup: Settings → Data and Storage → Proxy Settings → Add proxy →
**SOCKS5**, server `127.0.0.1`, port `55056`, empty login and password.

## Good to know

- **Notification**: shows whether the proxy pool is reachable (`Прокси: 6/6 доступны`),
  traffic up/down, uptime and has a **Стоп** button. It updates every 5 seconds.
- **Allow background work** (Разрешить работу в фоне) — exempts the app from
  battery optimisation.
- **Start on boot** (Запускать при включении телефона) — autostart after reboot.
- Logs for debugging: `adb logcat -s tgsocks`.

## Build

Docker is required:

```bash
docker pull ghcr.io/cirruslabs/android-sdk:34
cp assets/example_proxies.txt assets/default_proxies.txt   # optional: baked-in list
docker run --rm -v "$PWD:/app" ghcr.io/cirruslabs/android-sdk:34 bash /app/build.sh
```

Result: `build/tgsocks.apk`.

## Limitations

- Telegram calls do not work through a proxy.
- Only Telegram uses the proxy — this is not a VPN.
- On some mobile carriers DPI drops connections to Telegram addresses.

General description and where to buy proxies — in the
[root README](../README.md).
