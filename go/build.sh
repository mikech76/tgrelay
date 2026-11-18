#!/bin/sh
# Сборка Go-версии: Windows (трей) и Linux (headless).
set -e
cd "$(dirname "$0")"
mkdir -p dist
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath \
    -ldflags "-s -w -H=windowsgui" -o dist/tgrelay.exe .
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath \
    -ldflags "-s -w" -o dist/tgrelay-linux .
ls -lh dist
