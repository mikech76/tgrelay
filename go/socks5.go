package main

import (
	"bufio"
	"crypto/subtle"
	"encoding/binary"
	"io"
	"net"
	"strconv"
	"time"
)

// Socks5 — локальный SOCKS5-сервер, трафик идёт через пул.
type Socks5 struct {
	pool   *Pool
	users  []UserPass
	bypass []*net.IPNet
	stats  *Stats
}

func (s *Socks5) Serve(listener net.Listener) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		go s.handle(conn)
	}
}

func (s *Socks5) handle(client net.Conn) {
	defer client.Close()
	if s.stats != nil {
		s.stats.ConnOpen()
		defer s.stats.ConnClose()
	}
	_ = client.SetDeadline(time.Now().Add(20 * time.Second))

	br := bufio.NewReader(client)
	head := make([]byte, 2)
	if _, err := io.ReadFull(br, head); err != nil {
		return
	}
	if head[0] != 0x05 {
		return
	}
	methods := make([]byte, int(head[1]))
	if _, err := io.ReadFull(br, methods); err != nil {
		return
	}

	login := ""
	trusted := s.isTrusted(client.RemoteAddr())
	wantAuth := !trusted && len(s.users) > 0
	hasAuth := false
	hasNone := false
	for _, m := range methods {
		if m == 0x02 {
			hasAuth = true
		}
		if m == 0x00 {
			hasNone = true
		}
	}

	method := byte(0xff)
	switch {
	case wantAuth && hasAuth:
		method = 0x02
	case hasNone && (trusted || len(s.users) == 0):
		method = 0x00
	case hasAuth:
		method = 0x02
	}
	if _, err := client.Write([]byte{0x05, method}); err != nil {
		return
	}
	if method == 0xff {
		return
	}

	if method == 0x02 {
		if _, err := io.ReadFull(br, head); err != nil || head[0] != 0x01 {
			return
		}
		ulen := int(head[1])
		user := make([]byte, ulen)
		if _, err := io.ReadFull(br, user); err != nil {
			return
		}
		plenByte := make([]byte, 1)
		if _, err := io.ReadFull(br, plenByte); err != nil {
			return
		}
		passwd := make([]byte, int(plenByte[0]))
		if _, err := io.ReadFull(br, passwd); err != nil {
			return
		}
		ok := false
		for _, account := range s.users {
			match := subtle.ConstantTimeCompare(user, []byte(account.User)) == 1 &&
				subtle.ConstantTimeCompare(passwd, []byte(account.Pass)) == 1
			if match {
				ok = true
				login = account.User
				break
			}
		}
		answer := []byte{0x01, 0x01}
		if ok {
			answer[1] = 0x00
		}
		if _, err := client.Write(answer); err != nil {
			return
		}
		if !ok {
			return
		}
	}

	req := make([]byte, 4)
	if _, err := io.ReadFull(br, req); err != nil {
		return
	}
	if req[0] != 0x05 || req[1] != 0x01 {
		_, _ = client.Write([]byte{0x05, 0x07, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}

	host, err := readTarget(br, req[3])
	if err != nil {
		_, _ = client.Write([]byte{0x05, 0x08, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}
	portBuf := make([]byte, 2)
	if _, err := io.ReadFull(br, portBuf); err != nil {
		return
	}
	port := int(binary.BigEndian.Uint16(portBuf))

	upstream, err := s.pool.Dial(host, port)
	if err != nil {
		logf("нет туннеля до %s:%d — %v", host, port, err)
		_, _ = client.Write([]byte{0x05, 0x05, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}
	defer upstream.Close()

	if _, err := client.Write([]byte{0x05, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0}); err != nil {
		return
	}
	_ = client.SetDeadline(time.Time{})
	logf("%s -> %s:%d", client.RemoteAddr(), host, port)

	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(&countWriter{w: upstream, stats: s.stats, up: true, user: login}, br)
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(&countWriter{w: client, stats: s.stats, user: login}, upstream)
		done <- struct{}{}
	}()
	<-done
}

func (s *Socks5) isTrusted(addr net.Addr) bool {
	tcp, ok := addr.(*net.TCPAddr)
	if !ok {
		return false
	}
	for _, network := range s.bypass {
		if network.Contains(tcp.IP) {
			return true
		}
	}
	return false
}

func readTarget(r io.Reader, atyp byte) (string, error) {
	switch atyp {
	case 0x01:
		buf := make([]byte, 4)
		if _, err := io.ReadFull(r, buf); err != nil {
			return "", err
		}
		return net.IP(buf).String(), nil
	case 0x03:
		length := make([]byte, 1)
		if _, err := io.ReadFull(r, length); err != nil {
			return "", err
		}
		name := make([]byte, int(length[0]))
		if _, err := io.ReadFull(r, name); err != nil {
			return "", err
		}
		return string(name), nil
	case 0x04:
		buf := make([]byte, 16)
		if _, err := io.ReadFull(r, buf); err != nil {
			return "", err
		}
		return net.IP(buf).String(), nil
	}
	return "", errBadAddr
}

var errBadAddr = errText("неподдерживаемый тип адреса")

// socksLink собирает tg://socks-ссылку.
func socksLink(host string, port int, user, pass string) string {
	link := "tg://socks?server=" + host + "&port=" + strconv.Itoa(port)
	if user != "" {
		link += "&user=" + user + "&pass=" + pass
	}
	return link
}

// countWriter считает байты для строки состояния.
type countWriter struct {
	w     io.Writer
	stats *Stats
	up    bool
	user  string
}

func (c *countWriter) Write(p []byte) (int, error) {
	n, err := c.w.Write(p)
	if n > 0 && c.stats != nil {
		if c.up {
			c.stats.Add(n, 0)
		} else {
			c.stats.Add(0, n)
		}
		c.stats.AddUser(c.user, c.up, n)
	}
	return n, err
}
