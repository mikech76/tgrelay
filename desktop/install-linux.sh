#!/usr/bin/env bash
# Установка tgrelay на Linux (Debian/Ubuntu): venv, зависимости, systemd.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ "$(id -u)" -eq 0 ]; then
    echo "Запускайте от обычного пользователя, sudo внутри скрипта."
    exit 1
fi

echo "== пакеты =="
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

echo "== виртуальное окружение =="
python3 -m venv venv
./venv/bin/pip install --upgrade pip >/dev/null
./venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo
    echo "Создан .env. Впишите SECRET и PROXIES, затем запустите скрипт снова:"
    echo "  nano $DIR/.env"
    exit 1
fi

echo "== systemd =="
sudo tee /etc/systemd/system/tgrelay.service >/dev/null <<EOF
[Unit]
Description=tgrelay: MTProto + SOCKS5 proxy for Telegram
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python $DIR/run_headless.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now tgrelay
sleep 2
systemctl --no-pager --lines=20 status tgrelay || true

echo
echo "Готово. Логи: journalctl -u tgrelay -f"
echo "Порты и прокси: $DIR/.env"
