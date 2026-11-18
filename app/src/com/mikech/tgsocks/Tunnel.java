package com.mikech.tgsocks;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.List;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Туннель до цели через апстрим-прокси: HTTP CONNECT, HTTPS, SOCKS5, SOCKS4.
 *
 * Тип берётся из схемы в списке прокси (http://, https://, socks5://,
 * socks://, socks4://, socks4a://), а если схемы нет — определяется сам:
 * сначала HTTP, потом SOCKS5, потом SOCKS4. Найденный тип запоминается
 * в {@link Proxies.P#kind}, чтобы следующие подключения шли напрямую.
 */
public final class Tunnel {

    /** Таймаут одной попытки при автоопределении типа прокси. */
    private static final int PROBE_TIMEOUT_MS = 4000;

    private static final String[] AUTO_ORDER = {"http", "socks5", "socks4"};

    public static final class Conn {
        public final Socket socket;
        public final InputStream in;
        public final OutputStream out;

        Conn(Socket socket, InputStream in, OutputStream out) {
            this.socket = socket;
            this.in = in;
            this.out = out;
        }
    }

    private Tunnel() {
    }

    public static Conn open(Proxies.P p, String host, int port, int timeoutMs)
            throws IOException {
        String kind = p.kind == null ? "" : p.kind.toLowerCase();
        if (!kind.isEmpty()) {
            return connect(p, host, port, timeoutMs, kind);
        }

        List<String> errors = new ArrayList<>();
        int probe = Math.min(timeoutMs, PROBE_TIMEOUT_MS);
        for (String attempt : AUTO_ORDER) {
            try {
                Conn conn = connect(p, host, port, probe, attempt);
                p.kind = attempt;
                return conn;
            } catch (IOException e) {
                errors.add(name(attempt) + ": " + e.getMessage());
            }
        }
        throw new IOException("прокси не отвечает ни как HTTP, ни как SOCKS — "
                + join(errors));
    }

    static String name(String kind) {
        switch (kind) {
            case "http":
                return "HTTP CONNECT";
            case "https":
                return "HTTPS CONNECT";
            case "socks5":
                return "SOCKS5";
            case "socks4":
                return "SOCKS4";
            default:
                return "авто";
        }
    }

    private static Conn connect(Proxies.P p, String host, int port, int timeoutMs,
                                String kind) throws IOException {
        if ("http".equals(kind)) {
            return httpConnect(p, host, port, timeoutMs, false);
        }
        if ("https".equals(kind)) {
            try {
                return httpConnect(p, host, port, timeoutMs, false);
            } catch (IOException e) {
                return httpConnect(p, host, port, timeoutMs, true);
            }
        }
        if ("socks5".equals(kind)) {
            return socks5Connect(p, host, port, timeoutMs);
        }
        if ("socks4".equals(kind)) {
            return socks4Connect(p, host, port, timeoutMs);
        }
        throw new IOException("неизвестный тип прокси: " + kind);
    }

    /** Открыть TCP до прокси и настроить таймауты. */
    private static Socket openSocket(Proxies.P p, int timeoutMs) throws IOException {
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress(p.host, p.port), timeoutMs);
            s.setTcpNoDelay(true);
            s.setSoTimeout(timeoutMs);
            return s;
        } catch (IOException e) {
            closeQuietly(s);
            throw e;
        }
    }

    // --- HTTP CONNECT ------------------------------------------------------

    private static Conn httpConnect(Proxies.P p, String host, int port,
                                    int timeoutMs, boolean tls) throws IOException {
        Socket raw = openSocket(p, timeoutMs);
        Socket s = raw;
        try {
            if (tls) {
                s = startTls(raw, p.host, p.port);
            }
            OutputStream out = s.getOutputStream();
            InputStream in = new BufferedInputStream(s.getInputStream());

            String target = (host.indexOf(':') >= 0 ? "[" + host + "]" : host) + ":" + port;
            StringBuilder req = new StringBuilder();
            req.append("CONNECT ").append(target).append(" HTTP/1.1\r\n");
            req.append("Host: ").append(target).append("\r\n");
            if (!p.user.isEmpty()) {
                String cred = p.user + ":" + p.pass;
                req.append("Proxy-Authorization: Basic ").append(base64(cred)).append("\r\n");
            }
            req.append("\r\n");
            out.write(req.toString().getBytes(StandardCharsets.ISO_8859_1));
            out.flush();

            String status = readLine(in);
            if (status == null || !status.contains(" 200")) {
                throw new IOException("proxy: " + status);
            }
            while (true) {
                String line = readLine(in);
                if (line == null || line.isEmpty()) {
                    break;
                }
            }
            s.setSoTimeout(0);
            return new Conn(s, in, out);
        } catch (IOException e) {
            closeQuietly(s);
            if (s != raw) {
                closeQuietly(raw);
            }
            throw e;
        }
    }

    private static Socket startTls(Socket raw, String host, int port) throws IOException {
        try {
            SSLContext ctx = SSLContext.getInstance("TLS");
            ctx.init(null, new TrustManager[]{TRUST_ALL}, null);
            SSLSocketFactory f = ctx.getSocketFactory();
            SSLSocket ssl = (SSLSocket) f.createSocket(raw, host, port, true);
            ssl.startHandshake();
            return ssl;
        } catch (IOException e) {
            throw e;
        } catch (Exception e) {
            throw new IOException("TLS: " + e);
        }
    }

    private static final X509TrustManager TRUST_ALL = new X509TrustManager() {
        @Override
        public void checkClientTrusted(X509Certificate[] chain, String authType) {
        }

        @Override
        public void checkServerTrusted(X509Certificate[] chain, String authType) {
        }

        @Override
        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
    };

    // --- SOCKS5 (RFC 1928 + RFC 1929) --------------------------------------

    private static Conn socks5Connect(Proxies.P p, String host, int port,
                                      int timeoutMs) throws IOException {
        Socket s = openSocket(p, timeoutMs);
        try {
            OutputStream out = s.getOutputStream();
            InputStream in = new BufferedInputStream(s.getInputStream());

            byte[] methods = p.user.isEmpty()
                    ? new byte[]{0x00}
                    : new byte[]{0x00, 0x02};
            out.write(new byte[]{0x05, (byte) methods.length});
            out.write(methods);
            out.flush();

            byte[] hello = readN(in, 2);
            if (hello[0] != 0x05) {
                throw new IOException("это не SOCKS5");
            }
            int method = hello[1] & 0xff;
            if (method == 0x02) {
                if (p.user.isEmpty()) {
                    throw new IOException("SOCKS5 требует логин и пароль");
                }
                byte[] u = p.user.getBytes(StandardCharsets.UTF_8);
                byte[] pw = p.pass.getBytes(StandardCharsets.UTF_8);
                ByteArrayOutputStream auth = new ByteArrayOutputStream();
                auth.write(0x01);
                auth.write(u.length);
                auth.write(u);
                auth.write(pw.length);
                auth.write(pw);
                out.write(auth.toByteArray());
                out.flush();
                byte[] answer = readN(in, 2);
                if ((answer[1] & 0xff) != 0) {
                    throw new IOException("SOCKS5: неверный логин или пароль");
                }
            } else if (method != 0x00) {
                throw new IOException("SOCKS5: неподходящий способ авторизации");
            }

            ByteArrayOutputStream req = new ByteArrayOutputStream();
            req.write(0x05);
            req.write(0x01);
            req.write(0x00);
            req.write(socksAddr(host));
            req.write((port >> 8) & 0xff);
            req.write(port & 0xff);
            out.write(req.toByteArray());
            out.flush();

            byte[] reply = readN(in, 4);
            if ((reply[1] & 0xff) != 0) {
                throw new IOException("SOCKS5: отказ (" + socksError(reply[1] & 0xff) + ")");
            }
            int atyp = reply[3] & 0xff;
            if (atyp == 0x01) {
                readN(in, 4 + 2);
            } else if (atyp == 0x04) {
                readN(in, 16 + 2);
            } else if (atyp == 0x03) {
                int len = readN(in, 1)[0] & 0xff;
                readN(in, len + 2);
            } else {
                throw new IOException("SOCKS5: непонятный адрес в ответе (" + atyp + ")");
            }
            s.setSoTimeout(0);
            return new Conn(s, in, out);
        } catch (IOException e) {
            closeQuietly(s);
            throw e;
        }
    }

    private static byte[] socksAddr(String host) {
        byte[] literal = ipLiteral(host);
        if (literal != null) {
            if (literal.length == 4) {
                byte[] out = new byte[5];
                out[0] = 0x01;
                System.arraycopy(literal, 0, out, 1, 4);
                return out;
            }
            byte[] out = new byte[17];
            out[0] = 0x04;
            System.arraycopy(literal, 0, out, 1, 16);
            return out;
        }
        byte[] name = host.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(0x03);
        out.write(name.length);
        out.write(name, 0, name.length);
        return out.toByteArray();
    }

    private static String socksError(int code) {
        switch (code) {
            case 1:
                return "общий сбой";
            case 2:
                return "правило запрещает";
            case 3:
                return "сеть недоступна";
            case 4:
                return "узел недоступен";
            case 5:
                return "соединение отклонено";
            case 6:
                return "TTL истёк";
            case 7:
                return "команда не поддерживается";
            case 8:
                return "тип адреса не поддерживается";
            default:
                return String.valueOf(code);
        }
    }

    // --- SOCKS4 / 4a -------------------------------------------------------

    private static Conn socks4Connect(Proxies.P p, String host, int port,
                                      int timeoutMs) throws IOException {
        Socket s = openSocket(p, timeoutMs);
        try {
            OutputStream out = s.getOutputStream();
            InputStream in = new BufferedInputStream(s.getInputStream());

            byte[] literal = ipLiteral(host);
            ByteArrayOutputStream req = new ByteArrayOutputStream();
            req.write(0x04);
            req.write(0x01);
            req.write((port >> 8) & 0xff);
            req.write(port & 0xff);
            if (literal != null && literal.length == 4) {
                req.write(literal, 0, 4);
            } else {
                req.write(new byte[]{0, 0, 0, 1});      // SOCKS4a: имя дальше
            }
            req.write(p.user.getBytes(StandardCharsets.UTF_8));
            req.write(0x00);
            if (literal == null || literal.length != 4) {
                req.write(host.getBytes(StandardCharsets.UTF_8));
                req.write(0x00);
            }
            out.write(req.toByteArray());
            out.flush();

            byte[] answer = readN(in, 8);
            if ((answer[1] & 0xff) != 0x5a) {
                throw new IOException("SOCKS4: отказ (" + (answer[1] & 0xff) + ")");
            }
            s.setSoTimeout(0);
            return new Conn(s, in, out);
        } catch (IOException e) {
            closeQuietly(s);
            throw e;
        }
    }

    // --- мелочи ------------------------------------------------------------

    /** IP-литерал в виде байтов (4 или 16) или null, если это имя узла. */
    private static byte[] ipLiteral(String host) {
        String h = host.replace("[", "").replace("]", "");
        if (!h.contains(":") && !h.matches("[0-9.]+")) {
            return null;
        }
        try {
            return InetAddress.getByName(h).getAddress();
        } catch (Exception e) {
            return null;
        }
    }

    private static byte[] readN(InputStream in, int n) throws IOException {
        byte[] buf = new byte[n];
        int got = 0;
        while (got < n) {
            int r = in.read(buf, got, n - got);
            if (r < 0) {
                throw new IOException("прокси закрыл соединение");
            }
            got += r;
        }
        return buf;
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\n') {
                break;
            }
            if (c != '\r') {
                b.write(c);
            }
        }
        if (c == -1 && b.size() == 0) {
            return null;
        }
        return new String(b.toByteArray(), StandardCharsets.ISO_8859_1);
    }

    private static String base64(String text) {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        String abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        StringBuilder out = new StringBuilder();
        int i = 0;
        while (i + 2 < data.length) {
            int n = ((data[i] & 0xff) << 16) | ((data[i + 1] & 0xff) << 8) | (data[i + 2] & 0xff);
            out.append(abc.charAt((n >> 18) & 63)).append(abc.charAt((n >> 12) & 63))
                    .append(abc.charAt((n >> 6) & 63)).append(abc.charAt(n & 63));
            i += 3;
        }
        int rest = data.length - i;
        if (rest == 1) {
            int n = (data[i] & 0xff) << 16;
            out.append(abc.charAt((n >> 18) & 63)).append(abc.charAt((n >> 12) & 63)).append("==");
        } else if (rest == 2) {
            int n = ((data[i] & 0xff) << 16) | ((data[i + 1] & 0xff) << 8);
            out.append(abc.charAt((n >> 18) & 63)).append(abc.charAt((n >> 12) & 63))
                    .append(abc.charAt((n >> 6) & 63)).append('=');
        }
        return out.toString();
    }

    private static String join(List<String> parts) {
        StringBuilder b = new StringBuilder();
        for (String part : parts) {
            if (b.length() > 0) {
                b.append("; ");
            }
            b.append(part);
        }
        return b.toString();
    }

    private static void closeQuietly(Socket s) {
        if (s != null) {
            try {
                s.close();
            } catch (IOException ignored) {
            }
        }
    }
}
