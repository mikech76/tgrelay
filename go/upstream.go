package main

import (
	"bufio"
	"crypto/rand"
	"crypto/tls"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

// Proxy — апстрим-прокси из конфига.
type Proxy struct {
	Host string
	Port int
	User string
	Pass string

	kind atomic.Value // string: "", http, https, socks5, socks4
	dead atomic.Bool
}

func (p *Proxy) Addr() string { return net.JoinHostPort(p.Host, strconv.Itoa(p.Port)) }

func (p *Proxy) Kind() string {
	if v, ok := p.kind.Load().(string); ok {
		return v
	}
	return ""
}

func (p *Proxy) SetKind(k string) { p.kind.Store(k) }

var schemeKind = map[string]string{
	"http":    "http",
	"https":   "https",
	"socks":   "socks5",
	"socks5":  "socks5",
	"socks5h": "socks5",
	"socks4":  "socks4",
	"socks4a": "socks4",
}

var kindPort = map[string]int{
	"http": 8080, "https": 443, "socks5": 1080, "socks4": 1080,
}

var autoOrder = []string{"http", "socks5", "socks4"}

// parseProxyLine разбирает строку со схемой или без неё.
func parseProxyLine(text string) (*Proxy, error) {
	item := stripComment(strings.TrimSpace(text))
	if item == "" || strings.HasPrefix(item, "#") {
		return nil, nil
	}

	scheme := ""
	if i := strings.Index(item, "://"); i > 0 {
		scheme = strings.ToLower(strings.TrimSpace(item[:i]))
		item = item[i+3:]
	}
	kind := ""
	if scheme != "" {
		k, ok := schemeKind[scheme]
		if !ok {
			return nil, fmt.Errorf("неизвестная схема %s:// (есть http, https, socks, socks5, socks4)", scheme)
		}
		kind = k
	}

	user, pass := "", ""
	if i := strings.LastIndex(item, "@"); i > 0 {
		cred := item[:i]
		item = item[i+1:]
		if j := strings.Index(cred, ":"); j >= 0 {
			user, pass = cred[:j], cred[j+1:]
		} else {
			user = cred
		}
	}

	host, portText := "", ""
	if strings.HasPrefix(item, "[") {
		end := strings.Index(item, "]")
		if end < 0 {
			return nil, fmt.Errorf("плохой адрес: %s", text)
		}
		host = item[1:end]
		rest := item[end+1:]
		portText = strings.TrimPrefix(rest, ":")
	} else if i := strings.LastIndex(item, ":"); i > 0 && !strings.Contains(item[i+1:], ":") {
		host, portText = item[:i], item[i+1:]
	} else {
		host = item
	}
	host = strings.Trim(strings.TrimSpace(host), "[]")
	if host == "" || strings.ContainsAny(host, " /") {
		return nil, fmt.Errorf("плохой адрес: %s", text)
	}

	port := 0
	if portText == "" {
		port = kindPort[kind]
		if port == 0 {
			port = 8080
		}
	} else {
		n, err := strconv.Atoi(portText)
		if err != nil || n <= 0 || n > 65535 {
			return nil, fmt.Errorf("плохой порт: %s", text)
		}
		port = n
	}

	p := &Proxy{Host: host, Port: port, User: user, Pass: pass}
	p.SetKind(kind)
	return p, nil
}

// bufConn сохраняет данные, уже прочитанные bufio.Reader при рукопожатии.
type bufConn struct {
	net.Conn
	r *bufio.Reader
}

func (c *bufConn) Read(b []byte) (int, error) { return c.r.Read(b) }

// openTunnel открывает туннель до host:port через прокси.
func openTunnel(p *Proxy, host string, port int, timeout time.Duration) (net.Conn, error) {
	kind := p.Kind()
	if kind != "" {
		return connectKind(p, host, port, timeout, kind)
	}

	var errs []string
	probe := timeout
	if probe > 4*time.Second {
		probe = 4 * time.Second
	}
	for _, attempt := range autoOrder {
		conn, err := connectKind(p, host, port, probe, attempt)
		if err == nil {
			p.SetKind(attempt)
			return conn, nil
		}
		errs = append(errs, kindName(attempt)+": "+err.Error())
	}
	return nil, fmt.Errorf("прокси не отвечает ни как HTTP, ни как SOCKS — %s", strings.Join(errs, "; "))
}

func kindName(kind string) string {
	switch kind {
	case "http":
		return "HTTP CONNECT"
	case "https":
		return "HTTPS CONNECT"
	case "socks5":
		return "SOCKS5"
	case "socks4":
		return "SOCKS4"
	default:
		return "авто"
	}
}

func connectKind(p *Proxy, host string, port int, timeout time.Duration, kind string) (net.Conn, error) {
	switch kind {
	case "http":
		return httpConnect(p, host, port, timeout, false)
	case "https":
		conn, err := httpConnect(p, host, port, timeout, false)
		if err == nil {
			return conn, nil
		}
		return httpConnect(p, host, port, timeout, true)
	case "socks5":
		return socks5Connect(p, host, port, timeout)
	case "socks4":
		return socks4Connect(p, host, port, timeout)
	}
	return nil, fmt.Errorf("неизвестный тип прокси: %s", kind)
}

func dialProxy(p *Proxy, timeout time.Duration) (net.Conn, error) {
	d := net.Dialer{Timeout: timeout}
	conn, err := d.Dial("tcp", p.Addr())
	if err != nil {
		return nil, err
	}
	if tcp, ok := conn.(*net.TCPConn); ok {
		_ = tcp.SetNoDelay(true)
	}
	return conn, nil
}

func httpConnect(p *Proxy, host string, port int, timeout time.Duration, useTLS bool) (net.Conn, error) {
	conn, err := dialProxy(p, timeout)
	if err != nil {
		return nil, err
	}
	if useTLS {
		secure := tls.Client(conn, &tls.Config{InsecureSkipVerify: true})
		if err := secure.Handshake(); err != nil {
			conn.Close()
			return nil, err
		}
		conn = secure
	}
	_ = conn.SetDeadline(time.Now().Add(timeout))

	target := net.JoinHostPort(host, strconv.Itoa(port))
	var req strings.Builder
	req.WriteString("CONNECT " + target + " HTTP/1.1\r\n")
	req.WriteString("Host: " + target + "\r\n")
	if p.User != "" {
		token := base64.StdEncoding.EncodeToString([]byte(p.User + ":" + p.Pass))
		req.WriteString("Proxy-Authorization: Basic " + token + "\r\n")
	}
	req.WriteString("\r\n")
	if _, err := io.WriteString(conn, req.String()); err != nil {
		conn.Close()
		return nil, err
	}

	br := bufio.NewReader(conn)
	status, err := br.ReadString('\n')
	if err != nil {
		conn.Close()
		return nil, err
	}
	if !strings.Contains(status, " 200") {
		conn.Close()
		return nil, fmt.Errorf("proxy: %s", strings.TrimSpace(status))
	}
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			conn.Close()
			return nil, err
		}
		if line == "\r\n" || line == "\n" {
			break
		}
	}
	_ = conn.SetDeadline(time.Time{})
	return &bufConn{Conn: conn, r: br}, nil
}

func socks5Connect(p *Proxy, host string, port int, timeout time.Duration) (net.Conn, error) {
	conn, err := dialProxy(p, timeout)
	if err != nil {
		return nil, err
	}
	_ = conn.SetDeadline(time.Now().Add(timeout))
	br := bufio.NewReader(conn)

	methods := []byte{0x00}
	if p.User != "" {
		methods = []byte{0x00, 0x02}
	}
	if _, err := conn.Write(append([]byte{0x05, byte(len(methods))}, methods...)); err != nil {
		conn.Close()
		return nil, err
	}
	head := make([]byte, 2)
	if _, err := io.ReadFull(br, head); err != nil {
		conn.Close()
		return nil, err
	}
	if head[0] != 0x05 {
		conn.Close()
		return nil, errors.New("это не SOCKS5")
	}
	switch head[1] {
	case 0x02:
		if p.User == "" {
			conn.Close()
			return nil, errors.New("SOCKS5 требует логин и пароль")
		}
		auth := []byte{0x01, byte(len(p.User))}
		auth = append(auth, p.User...)
		auth = append(auth, byte(len(p.Pass)))
		auth = append(auth, p.Pass...)
		if _, err := conn.Write(auth); err != nil {
			conn.Close()
			return nil, err
		}
		answer := make([]byte, 2)
		if _, err := io.ReadFull(br, answer); err != nil {
			conn.Close()
			return nil, err
		}
		if answer[1] != 0 {
			conn.Close()
			return nil, errors.New("SOCKS5: неверный логин или пароль")
		}
	case 0x00:
		// без авторизации
	default:
		conn.Close()
		return nil, errors.New("SOCKS5: неподходящий способ авторизации")
	}

	req := []byte{0x05, 0x01, 0x00}
	req = append(req, socksAddr(host)...)
	req = append(req, byte(port>>8), byte(port))
	if _, err := conn.Write(req); err != nil {
		conn.Close()
		return nil, err
	}

	reply := make([]byte, 4)
	if _, err := io.ReadFull(br, reply); err != nil {
		conn.Close()
		return nil, err
	}
	if reply[1] != 0 {
		conn.Close()
		return nil, fmt.Errorf("SOCKS5: отказ (%d)", reply[1])
	}
	switch reply[3] {
	case 0x01:
		_, err = io.CopyN(io.Discard, br, 4+2)
	case 0x04:
		_, err = io.CopyN(io.Discard, br, 16+2)
	case 0x03:
		length := make([]byte, 1)
		if _, err = io.ReadFull(br, length); err == nil {
			_, err = io.CopyN(io.Discard, br, int64(length[0])+2)
		}
	default:
		conn.Close()
		return nil, fmt.Errorf("SOCKS5: непонятный адрес в ответе (%d)", reply[3])
	}
	if err != nil {
		conn.Close()
		return nil, err
	}
	_ = conn.SetDeadline(time.Time{})
	return &bufConn{Conn: conn, r: br}, nil
}

func socksAddr(host string) []byte {
	if ip := net.ParseIP(host); ip != nil {
		if v4 := ip.To4(); v4 != nil {
			return append([]byte{0x01}, v4...)
		}
		return append([]byte{0x04}, ip.To16()...)
	}
	name := []byte(host)
	return append([]byte{0x03, byte(len(name))}, name...)
}

func socks4Connect(p *Proxy, host string, port int, timeout time.Duration) (net.Conn, error) {
	conn, err := dialProxy(p, timeout)
	if err != nil {
		return nil, err
	}
	_ = conn.SetDeadline(time.Now().Add(timeout))
	br := bufio.NewReader(conn)

	req := []byte{0x04, 0x01, byte(port >> 8), byte(port)}
	ip := net.ParseIP(host)
	if ip != nil && ip.To4() != nil {
		req = append(req, ip.To4()...)
		req = append(req, p.User...)
		req = append(req, 0x00)
	} else {
		req = append(req, 0, 0, 0, 1) // SOCKS4a: имя узла дальше
		req = append(req, p.User...)
		req = append(req, 0x00)
		req = append(req, host...)
		req = append(req, 0x00)
	}
	if _, err := conn.Write(req); err != nil {
		conn.Close()
		return nil, err
	}
	answer := make([]byte, 8)
	if _, err := io.ReadFull(br, answer); err != nil {
		conn.Close()
		return nil, err
	}
	if answer[1] != 0x5a {
		conn.Close()
		return nil, fmt.Errorf("SOCKS4: отказ (%d)", answer[1])
	}
	_ = conn.SetDeadline(time.Time{})
	return &bufConn{Conn: conn, r: br}, nil
}

// randomUint читает случайные байты (для инициализаций MTProto).
func randomUint(n int) []byte {
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		panic(err)
	}
	return buf
}
