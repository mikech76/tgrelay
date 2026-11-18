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

// UserPass — одна учётная запись SOCKS5.
type UserPass struct {
	User string
	Pass string
}

// Config — содержимое tgrelay.txt.
type Config struct {
	Proxies   []*Proxy
	MTPort    int // 0 = протокол выключен
	SocksPort int
	SocksHost string
	Secrets   [][]byte // несколько SECRET= — для разных людей
	External  string
	Bypass    []*net.IPNet
	Users     []UserPass
	Hosts     []string // адреса Telegram для проверки живости
	Lang      string

	// первая учётная запись — для ссылок и совместимости
	User string
	Pass string
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

// LoadConfig читает tgrelay.txt: KEY=value, повторы PROXY/SECRET/SOCKS_USER.
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	values := map[string]string{}
	seenOff := map[string]bool{}
	var proxyLines []string
	var secretLines []string
	var userLines []string
	var passLines []string

	for _, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(strings.TrimSuffix(raw, "\r"))
		if line == "" {
			continue
		}
		if strings.HasPrefix(line, "#") {
			body := strings.TrimSpace(strings.TrimPrefix(line, "#"))
			if j := strings.Index(body, "="); j > 0 {
				seenOff[strings.TrimSpace(body[:j])] = true
			}
			continue
		}
		i := strings.Index(line, "=")
		if i <= 0 {
			continue
		}
		key := strings.TrimSpace(line[:i])
		val := unquote(stripComment(line[i+1:]))
		switch key {
		case "PROXY":
			if val != "" {
				proxyLines = append(proxyLines, val)
			}
		case "SECRET":
			if val != "" {
				secretLines = append(secretLines, val)
			}
		case "SOCKS_USER":
			userLines = append(userLines, val)
		case "SOCKS_PASS":
			passLines = append(passLines, val)
		default:
			values[key] = val
		}
	}
	if more := values["PROXIES"]; more != "" {
		proxyLines = append([]string{more}, proxyLines...)
	}
	if more := values["SECRETS"]; more != "" {
		secretLines = append(secretLines, strings.Split(more, ",")...)
	}

	cfg := &Config{
		SocksHost: defaultString(values["SOCKS_HOST"], "127.0.0.1"),
		External:  values["EXTERNAL_HOST"],
		Lang:      strings.ToLower(values["LANG"]),
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

	for _, item := range secretLines {
		for _, part := range strings.Split(item, ",") {
			clean := strings.ReplaceAll(strings.ReplaceAll(strings.TrimSpace(part), " ", ""), "-", "")
			if len(clean) != 32 {
				fmt.Fprintf(os.Stderr, "SECRET пропущен (нужно 32 hex-символа): %s\n", part)
				continue
			}
			raw, derr := hex.DecodeString(clean)
			if derr != nil {
				fmt.Fprintf(os.Stderr, "SECRET пропущен (не hex): %s\n", part)
				continue
			}
			cfg.Secrets = append(cfg.Secrets, raw)
		}
	}
	if len(cfg.Secrets) == 0 {
		cfg.Secrets = [][]byte{make([]byte, 16)}
		_, _ = rand.Read(cfg.Secrets[0])
		fmt.Printf("SECRET пустой — сгенерирован временный: %s\n",
			hex.EncodeToString(cfg.Secrets[0]))
	}

	cfg.MTPort = portValue(values, seenOff, "PROXY_PORT", defaultMTPort)
	cfg.SocksPort = portValue(values, seenOff, "SOCKS_PORT", defaultSocksPort)

	for i, user := range userLines {
		if strings.TrimSpace(user) == "" {
			continue
		}
		pass := ""
		if i < len(passLines) {
			pass = passLines[i]
		}
		cfg.Users = append(cfg.Users, UserPass{User: user, Pass: pass})
	}
	if len(cfg.Users) > 0 {
		cfg.User = cfg.Users[0].User
		cfg.Pass = cfg.Users[0].Pass
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
