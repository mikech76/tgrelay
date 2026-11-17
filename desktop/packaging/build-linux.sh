#!/usr/bin/env bash
# =============================================================================
#  Сборка Linux-бинарника tgrelay — один файл, Python на сервере не нужен.
#
#  Запуск (из папки desktop):
#      bash packaging/build-linux.sh
#
#  Собирается в python:3.12-slim-bullseye (glibc 2.31):
#  работает на Debian 11+, Ubuntu 20.04+, Fedora 33+, RHEL 9+ (x86_64).
#
#  Результат: dist/tgrelay-linux-x86_64
# =============================================================================
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="python:3.12-slim-bullseye"

# путь для докера: в Git Bash /c/... — докеру нужен C:/...
if command -v cygpath >/dev/null 2>&1; then
    SRC="$(cygpath -m "$SRC")"
fi

echo "== контейнер сборки: $IMAGE =="
# MSYS не должен превращать /src в C:/Program Files/Git/src
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
docker run --rm -v "$SRC:/src" -w /src "$IMAGE" bash -lc '
    set -euo pipefail
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends binutils >/dev/null
    echo "python: $(python --version)"
    # чистый venv: в образе и так ничего лишнего, но venv - гарантия
    python -m venv /tmp/buildenv
    /tmp/buildenv/bin/pip install --quiet -r requirements.txt pyinstaller
    /tmp/buildenv/bin/python -m PyInstaller --noconfirm --clean --onefile \
        --name tgrelay-linux-x86_64 \
        --add-data "/src/.env.example:." \
        --specpath packaging --workpath packaging/work --distpath dist \
        run_headless.py
    chmod +x /src/dist/tgrelay-linux-x86_64
'

# контейнер пишет от root — возвращаем владение рабочему пользователю
if [ "$(id -u)" -eq 0 ]; then
    chown -R "$(stat -c '%u:%g' "$SRC")" "$SRC/dist" "$SRC/packaging" 2>/dev/null || true
fi

ls -lh "$SRC/dist/tgrelay-linux-x86_64"
echo "Готово: $SRC/dist/tgrelay-linux-x86_64"
echo "Проверка: ./dist/tgrelay-linux-x86_64"
