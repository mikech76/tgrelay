# tgrelay на Go — экспериментальный спайк

Headless-версия ядра (без трея): конфиг, пул апстримов, MTProto, SOCKS5.

Собрать:

```bash
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o dist/tgrelay-go.exe .
CGO_ENABLED=0 GOOS=linux   GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o dist/tgrelay-go .
```

Размер: ~4,3 МБ (Windows), ~4,2 МБ (Linux) — против 21 МБ и 11 МБ у Python-сборок.
В релизы пока не входит: трея нет, MTProto-протокол проверен не полностью.
