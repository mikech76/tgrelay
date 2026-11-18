package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"io"
	"net"
	"strconv"
	"sync"
	"time"
)

const handshakeLen = 64

var tgDCHosts = []string{
	"149.154.175.50",  // DC 1
	"149.154.167.51",  // DC 2
	"149.154.175.100", // DC 3
	"149.154.167.91",  // DC 4
	"91.108.56.100",   // DC 5
}

var validTags = [][4]byte{
	{0xef, 0xef, 0xef, 0xef}, // abridged
	{0xee, 0xee, 0xee, 0xee}, // intermediate
	{0xdd, 0xdd, 0xdd, 0xdd}, // padded intermediate
}

var reservedStarts = [][]byte{
	[]byte("HEAD"), []byte("POST"), []byte("GET "),
	{0xee, 0xee, 0xee, 0xee}, {0xdd, 0xdd, 0xdd, 0xdd},
	{0x16, 0x03, 0x01, 0x02},
}

// MTProto — прокси-сервер Telegram (MTProto) поверх пула.
type MTProto struct {
	secret []byte
	pool   *Pool
	hosts  []string
	stats  *Stats
}

func (m *MTProto) Serve(listener net.Listener) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		go m.handle(conn)
	}
}

func (m *MTProto) handle(client net.Conn) {
	defer client.Close()
	if m.stats != nil {
		m.stats.ConnOpen()
		defer m.stats.ConnClose()
	}
	_ = client.SetDeadline(time.Now().Add(20 * time.Second))

	init := make([]byte, handshakeLen)
	if _, err := io.ReadFull(client, init); err != nil {
		return
	}

	// разбор ключей клиента
	decKey := sha256.Sum256(append(append([]byte{}, init[8:40]...), m.secret...))
	decStream := ctrStream(decKey[:], init[40:56])

	plain := make([]byte, handshakeLen)
	decStream.XORKeyStream(plain, init) // позиция 64 — инициализация уже расшифрована

	tag := plain[56:60]
	if !validTag(tag) {
		logf("неизвестный proto tag: %s", hex.EncodeToString(tag))
		return
	}

	rev := reverse(init[8:56])
	encKey := sha256.Sum256(append(append([]byte{}, rev[:32]...), m.secret...))
	encStream := ctrStream(encKey[:], rev[32:])

	dcID := int16(binary.LittleEndian.Uint16(plain[60:62]))

	relay := buildRelayInit(tag, dcID)

	tgEncKey := relay[8:40]
	tgEncIV := relay[40:56]
	tgEnc := ctrStreamRaw(tgEncKey, tgEncIV)

	tgRev := reverse(relay[8:56])
	tgDec := ctrStreamRaw(tgRev[:32], tgRev[32:])

	// сдвигаем шифратор TG на 64 байта: relay init уже отправлен
	zero := make([]byte, handshakeLen)
	tgEnc.XORKeyStream(zero, zero)

	dcIndex := int(dcID)
	if dcIndex < 0 {
		dcIndex = -dcIndex
	}
	dcIndex--
	if dcIndex < 0 {
		dcIndex = 0
	}
	if dcIndex >= len(tgDCHosts) {
		dcIndex = len(tgDCHosts) - 1
	}
	host := tgDCHosts[dcIndex]
	if len(m.hosts) > 0 && dcID == 0 {
		host = m.hosts[0]
	}

	upstream, err := m.pool.Dial(host, 443)
	if err != nil {
		logf("нет туннеля до %s:443 — %v", host, err)
		return
	}
	defer upstream.Close()

	_ = client.SetDeadline(time.Time{})
	if _, err := upstream.Write(relay); err != nil {
		return
	}
	logf("туннель %s:443", host)

	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		copyCTR(upstream, client, decStream, tgEnc, m.stats, true)
		upstream.Close()
	}()
	go func() {
		defer wg.Done()
		copyCTR(client, upstream, tgDec, encStream, m.stats, false)
		client.Close()
	}()
	wg.Wait()
}

func validTag(tag []byte) bool {
	for _, t := range validTags {
		if tag[0] == t[0] && tag[1] == t[1] && tag[2] == t[2] && tag[3] == t[3] {
			return true
		}
	}
	return false
}

func reverse(b []byte) []byte {
	out := make([]byte, len(b))
	for i := range b {
		out[len(b)-1-i] = b[i]
	}
	return out
}

func ctrStream(key, iv []byte) cipher.Stream { return ctrStreamRaw(key, iv) }

func ctrStreamRaw(key, iv []byte) cipher.Stream {
	block, err := aes.NewCipher(key)
	if err != nil {
		panic(err)
	}
	return cipher.NewCTR(block, iv)
}

// copyCTR читает из src, расшифровывает и заново шифрует в dst.
func copyCTR(dst net.Conn, src net.Conn, dec cipher.Stream, enc cipher.Stream,
	stats *Stats, up bool) {
	buf := make([]byte, 65536)
	for {
		n, err := src.Read(buf)
		if n > 0 {
			dec.XORKeyStream(buf[:n], buf[:n])
			enc.XORKeyStream(buf[:n], buf[:n])
			if _, werr := dst.Write(buf[:n]); werr != nil {
				return
			}
			if stats != nil {
				if up {
					stats.Add(n, 0)
				} else {
					stats.Add(0, n)
				}
			}
		}
		if err != nil {
			return
		}
	}
}

// buildRelayInit создаёт 64-байтовую инициализацию для сервера Telegram.
func buildRelayInit(tag []byte, dcID int16) []byte {
	var rnd []byte
	for {
		rnd = randomUint(handshakeLen)
		if rnd[0] == 0xef {
			continue
		}
		skip := false
		for _, start := range reservedStarts {
			if string(rnd[:4]) == string(start) {
				skip = true
				break
			}
		}
		if skip {
			continue
		}
		if rnd[4] == 0 && rnd[5] == 0 && rnd[6] == 0 && rnd[7] == 0 {
			continue
		}
		break
	}

	encKey := rnd[8:40]
	encIV := rnd[40:56]
	stream := ctrStreamRaw(encKey, encIV)

	encryptedFull := make([]byte, handshakeLen)
	stream.XORKeyStream(encryptedFull, rnd)

	tailPlain := make([]byte, 8)
	copy(tailPlain, tag)
	binary.LittleEndian.PutUint16(tailPlain[4:6], uint16(dcID))
	copy(tailPlain[6:8], randomUint(2))

	result := make([]byte, handshakeLen)
	copy(result, rnd)
	for i := 0; i < 8; i++ {
		keystream := encryptedFull[56+i] ^ rnd[56+i]
		result[56+i] = tailPlain[i] ^ keystream
	}
	return result
}

// HostPort helper для логов и ссылок.
func hostPort(host string, port int) string {
	return net.JoinHostPort(host, strconv.Itoa(port))
}
