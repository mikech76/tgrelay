package main

import (
	"fmt"
	"net"
	"strconv"
)

// Servers — поднятые протоколы.
type Servers struct {
	listeners []net.Listener
	cfg       *Config
	pool      *Pool
	stats     *Stats
}

func StartServers(cfg *Config, pool *Pool, stats *Stats) (*Servers, error) {
	s := &Servers{cfg: cfg, pool: pool, stats: stats}

	if cfg.MTPort != 0 {
		listener, err := net.Listen("tcp", "0.0.0.0:"+strconv.Itoa(cfg.MTPort))
		if err != nil {
			return nil, fmt.Errorf("MTProto: %w", err)
		}
		s.listeners = append(s.listeners, listener)
		mt := &MTProto{secrets: cfg.Secrets, pool: pool, hosts: cfg.Hosts, stats: stats}
		go mt.Serve(listener)
		logf("MTProto слушает 0.0.0.0:%d", cfg.MTPort)
	}

	if cfg.SocksPort != 0 {
		addr := net.JoinHostPort(cfg.SocksHost, strconv.Itoa(cfg.SocksPort))
		listener, err := net.Listen("tcp", addr)
		if err != nil {
			s.Close()
			return nil, fmt.Errorf("SOCKS5: %w", err)
		}
		s.listeners = append(s.listeners, listener)
		s5 := &Socks5{pool: pool, users: cfg.Users,
			bypass: cfg.Bypass, stats: stats}
		go s5.Serve(listener)
		logf("SOCKS5 слушает %s", addr)
	}
	return s, nil
}

func (s *Servers) Close() {
	for _, listener := range s.listeners {
		_ = listener.Close()
	}
}
