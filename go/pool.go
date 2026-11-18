package main

import (
	"context"
	"math/rand"
	"net"
	"strconv"
	"sync"
	"time"
)

// Pool — пул апстрим-прокси с проверкой живости.
type Pool struct {
	mu      sync.Mutex
	proxies []*Proxy
	targets []string
}

func NewPool(proxies []*Proxy, targets []string) *Pool {
	return &Pool{proxies: proxies, targets: targets}
}

func (p *Pool) Len() int { return len(p.proxies) }

func (p *Pool) Stats() (int, int) {
	alive := 0
	for _, proxy := range p.proxies {
		if !proxy.dead.Load() {
			alive++
		}
	}
	return alive, len(p.proxies)
}

func (p *Pool) candidates() []*Proxy {
	alive := make([]*Proxy, 0, len(p.proxies))
	for _, proxy := range p.proxies {
		if !proxy.dead.Load() {
			alive = append(alive, proxy)
		}
	}
	if len(alive) == 0 {
		return append(alive, p.proxies...)
	}
	return alive
}

// Dial открывает туннель через пул: до четырёх попыток, мёртвые помечаются.
func (p *Pool) Dial(host string, port int) (net.Conn, error) {
	list := p.candidates()
	rand.Shuffle(len(list), func(i, j int) { list[i], list[j] = list[j], list[i] })

	var lastErr error
	attempts := len(list)
	if attempts > 4 {
		attempts = 4
	}
	for i := 0; i < attempts; i++ {
		proxy := list[i]
		conn, err := openTunnel(proxy, host, port, 15*time.Second)
		if err == nil {
			proxy.dead.Store(false)
			return conn, nil
		}
		proxy.dead.Store(true)
		lastErr = err
		logf("прокси %s не смог: %v", proxy.Addr(), err)
	}
	if lastErr == nil {
		lastErr = errNoProxies
	}
	return nil, lastErr
}

var errNoProxies = &net.OpError{Op: "dial", Net: "proxy", Err: errText("нет прокси в списке")}

type errText string

func (e errText) Error() string { return string(e) }

// HealthLoop раз в interval проверяет каждый прокси и обновляет флаги.
func (p *Pool) HealthLoop(ctx context.Context, interval time.Duration) {
	p.checkAll()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			p.checkAll()
		}
	}
}

func (p *Pool) checkAll() {
	if len(p.targets) == 0 {
		return
	}
	var wg sync.WaitGroup
	for _, proxy := range p.proxies {
		wg.Add(1)
		go func(pr *Proxy) {
			defer wg.Done()
			for _, target := range p.targets {
				host, portText, err := net.SplitHostPort(target)
				if err != nil {
					continue
				}
				port, _ := strconv.Atoi(portText)
				conn, err := openTunnel(pr, host, port, 8*time.Second)
				if err == nil {
					conn.Close()
					pr.dead.Store(false)
					return
				}
			}
			pr.dead.Store(true)
		}(proxy)
	}
	wg.Wait()
	alive, total := p.Stats()
	logf("Health check: %d/%d живых", alive, total)
}
