package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// Stats — счётчики трафика и соединений для строк состояния.
type Stats struct {
	up   atomic.Uint64
	down atomic.Uint64

	conns      atomic.Int64
	connsTotal atomic.Uint64

	mu        sync.Mutex
	userStats map[string]*userCount
	upRate    float64
	downRate  float64
	lastUp    uint64
	lastDown  uint64
	lastTime  time.Time
	startedAt time.Time
}

type userCount struct {
	up   uint64
	down uint64
}

func NewStats() *Stats {
	return &Stats{startedAt: time.Now(), lastTime: time.Now(),
		userStats: map[string]*userCount{}}
}

// AddUser учитывает байты конкретного пользователя SOCKS5.
func (s *Stats) AddUser(name string, up bool, n int) {
	if name == "" || n <= 0 {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	item, ok := s.userStats[name]
	if !ok {
		item = &userCount{}
		s.userStats[name] = item
	}
	if up {
		item.up += uint64(n)
	} else {
		item.down += uint64(n)
	}
}

// UserLines — строки для status: трафик по каждому логину.
func (s *Stats) UserLines() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]string, 0, len(s.userStats))
	for name, item := range s.userStats {
		out = append(out, fmt.Sprintf("%s: up %s, down %s",
			name, human(float64(item.up)), human(float64(item.down))))
	}
	return out
}

func (s *Stats) Add(up, down int) {
	if up > 0 {
		s.up.Add(uint64(up))
	}
	if down > 0 {
		s.down.Add(uint64(down))
	}
}

func (s *Stats) ConnOpen() {
	s.conns.Add(1)
	s.connsTotal.Add(1)
}

func (s *Stats) ConnClose() { s.conns.Add(-1) }

func (s *Stats) Uptime() time.Duration { return time.Since(s.startedAt) }

type snapshot struct {
	Up, Down         uint64
	UpRate, DownRate float64
	Conns            int64
	ConnsTotal       uint64
}

func (s *Stats) Snapshot() snapshot {
	up, down := s.up.Load(), s.down.Load()
	s.mu.Lock()
	now := time.Now()
	dt := now.Sub(s.lastTime).Seconds()
	if dt >= 0.5 {
		instUp := float64(up-s.lastUp) / dt
		instDown := float64(down-s.lastDown) / dt
		// сглаживание ~5 секунд
		s.upRate = s.upRate*0.7 + instUp*0.3
		s.downRate = s.downRate*0.7 + instDown*0.3
		s.lastUp, s.lastDown, s.lastTime = up, down, now
	}
	upRate, downRate := s.upRate, s.downRate
	s.mu.Unlock()
	return snapshot{
		Up: up, Down: down,
		UpRate: upRate, DownRate: downRate,
		Conns: s.conns.Load(), ConnsTotal: s.connsTotal.Load(),
	}
}

func (s *Stats) state(pool *Pool) string {
	snap := s.Snapshot()
	if snap.UpRate+snap.DownRate > 1024 {
		return "traffic"
	}
	if pool != nil {
		alive, total := pool.Stats()
		if total > 0 && alive == 0 {
			return "error"
		}
	}
	if time.Since(s.startedAt) < 6*time.Second {
		return "starting"
	}
	return "ok"
}

// human переводит байты в «12,4 КБ» по текущему языку.
func human(n float64) string {
	units := []string{"Б", "КБ", "МБ", "ГБ"}
	if lang() == "en" {
		units = []string{"B", "KB", "MB", "GB"}
	}
	value := n
	idx := 0
	for value >= 1024 && idx < len(units)-1 {
		value /= 1024
		idx++
	}
	if idx == 0 {
		return trimNumber(value, 0) + " " + units[0]
	}
	return trimNumber(value, 1) + " " + units[idx]
}

func trimNumber(v float64, digits int) string {
	s := formatFloat(v, digits)
	if lang() == "ru" {
		s = replaceComma(s)
	}
	return s
}
