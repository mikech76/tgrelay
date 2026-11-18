package main

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
)

// Config — содержимое tgrelay.txt.
type Config struct {
	Proxies   []*Proxy
	MTPort    int // 0 = протокол выключен
	SocksPort int
	SocksHost string
	Secret    []byte
	External  string
	Bypass    []*net.IPNet
	User      string
	Pass      string
	Hosts     []string // адреса Telegram для проверки живости
	Lang      string
}

const (
	defaultMTPort    = 55055
	defaultSocksPort = 55056
)

var offValues = map[string]bool{
	"": true, "0": true, "off": true, "none": true, "no": true,
	"disable": true, "disabled": true, "-": true,
}

// stripComment убирает " #..." в конце строки, если решётка стоит после пробела.
func stripComment(v string) string {
	for i := 1; i < len(v); i++ {
		if v[i] == '#' && (v[i-1] == ' ' || v[i-1] == '\t') {
			return strings.TrimSpace(v[:i])
		}
	}
	return strings.TrimSpace(v)
}

func unquote(v string) string {
	if len(v) >= 2 {
		if (v[0] == '"' && v[len(v)-1] == '"') || (v[0] == '\'' && v[len(v)-1] == '\'') {
			return v[1 : len(v)-1]
		}
	}
	return v
}

// LoadConfig читает tgrelay.txt: KEY=value, повторы PROXY=, комментарии.
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	values := map[string]string{}
	seenOff := map[string]bool{}
	var proxyLines []string

	for _, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(strings.TrimSuffix(raw, "\r"))
		if line == "" {
			continue
		}
		if strings.HasPrefix(line, "#") {
			if i := strings.Index(line, "="); i > 0 {
				key := strings.TrimSpace(strings.TrimPrefix(line, "#"))
				if j := strings.Index(key, "="); j > 0 {
					seenOff[strings.TrimSpace(key[:j])] = true
				}
			}
			continue
		}
		i := strings.Index(line, "=")
		if i <= 0 {
			continue
		}
		key := strings.TrimSpace(line[:i])
		val := unquote(stripComment(line[i+1:]))
		if key == "PROXY" {
			if val != "" {
				proxyLines = append(proxyLines, val)
			}
			continue
		}
		values[key] = val
	}
	if more := values["PROXIES"]; more != "" {
		proxyLines = append([]string{more}, proxyLines...)
	}

	cfg := &Config{
		SocksHost: defaultString(values["SOCKS_HOST"], "127.0.0.1"),
		External:  values["EXTERNAL_HOST"],
		User:      values["SOCKS_USER"],
		Lang:      strings.ToLower(values["LANG"]),
		Pass:      values["SOCKS_PASS"],
	}

	for _, item := range strings.Split(strings.Join(proxyLines, ";"), ";") {
		p, perr := parseProxyLine(item)
		if perr != nil {
			fmt.Fprintf(os.Stderr, "прокси пропущен: %v\n", perr)
			continue
		}
		if p != nil {
			cfg.Proxies = append(cfg.Proxies, p)
		}
	}

	cfg.MTPort = portValue(values, seenOff, "PROXY_PORT", defaultMTPort)
	cfg.SocksPort = portValue(values, seenOff, "SOCKS_PORT", defaultSocksPort)

	if hexSecret := strings.ReplaceAll(strings.ReplaceAll(values["SECRET"], " ", ""), "-", ""); len(hexSecret) == 32 {
		if raw, derr := hex.DecodeString(hexSecret); derr == nil {
			cfg.Secret = raw
		}
	}
	if len(cfg.Secret) == 0 {
		cfg.Secret = make([]byte, 16)
		_, _ = rand.Read(cfg.Secret)
		fmt.Printf("SECRET пустой — сгенерирован временный: %s\n", hex.EncodeToString(cfg.Secret))
	}

	for _, item := range strings.Split(values["AUTH_BYPASS"], ",") {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		if !strings.Contains(item, "/") {
			item += "/32"
		}
		if _, network, nerr := net.ParseCIDR(item); nerr == nil {
			cfg.Bypass = append(cfg.Bypass, network)
		}
	}

	hosts := values["TEST_TARGET"]
	if hosts == "" {
		hosts = "149.154.167.51:443,149.154.175.50:443"
	}
	for _, item := range strings.Split(hosts, ",") {
		item = strings.TrimSpace(item)
		if item != "" {
			cfg.Hosts = append(cfg.Hosts, item)
		}
	}
	return cfg, nil
}

func defaultString(v, def string) string {
	if strings.TrimSpace(v) == "" {
		return def
	}
	return v
}

// portValue: ключа нет — default; ключ есть, но пустой/off/закомментирован — 0.
func portValue(values map[string]string, seenOff map[string]bool, key string, def int) int {
	val, ok := values[key]
	if !ok {
		if seenOff[key] {
			return 0
		}
		return def
	}
	val = strings.TrimSpace(strings.ToLower(val))
	if offValues[val] {
		return 0
	}
	n, err := strconv.Atoi(val)
	if err != nil || n <= 0 || n > 65535 {
		return 0
	}
	return n
}
