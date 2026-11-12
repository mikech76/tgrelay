package com.mikech.tgsocks;

import android.util.Base64;
import android.util.Log;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Локальный SOCKS5-сервер. Принимает соединения только с 127.0.0.1
 * и передаёт их через пул HTTP CONNECT-прокси.
 * Трафик не расшифровывается: SOCKS5 передаёт только адрес и порт.
 */
public class Socks5Server {

    public interface Logger {
        void line(String msg);
    }

    private static final int CONNECT_TIMEOUT_MS = 7000;
    private static final int BUF = 16384;
    private static final String TAG = "tgsocks";

    private final int port;
    private final List<Proxies.P> proxies;
    private final Logger log;

    private ServerSocket serverSocket;
    private Thread acceptThread;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private volatile String lastError = "";
    private volatile Proxies.P preferred;

    public Socks5Server(int port, List<Proxies.P> proxies, Logger log) {
        this.port = port;
        this.proxies = proxies;
        this.log = log;
    }

    public synchronized void start() throws IOException {
        if (running.get()) {
            return;
        }
        ServerSocket ss = new ServerSocket();
        ss.setReuseAddress(true);
        ss.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port));
        serverSocket = ss;
        running.set(true);
        acceptThread = new Thread(this::acceptLoop, "socks-accept");
        acceptThread.setDaemon(true);
        acceptThread.start();
        log.line("Слушаю 127.0.0.1:" + port + ", прокси: " + proxies.size());
    }

    public synchronized void stop() {
        running.set(false);
        if (serverSocket != null) {
            try {
                serverSocket.close();
            } catch (IOException ignored) {
            }
            serverSocket = null;
        }
    }

    public boolean isRunning() {
        return running.get();
    }

    public String lastError() {
        return lastError;
    }

    private void acceptLoop() {
        while (running.get()) {
            try {
                Socket client = serverSocket.accept();
                Thread t = new Thread(() -> handle(client), "socks-client");
                t.setDaemon(true);
                t.start();
            } catch (IOException e) {
                if (running.get()) {
                    log.line("accept: " + e.getMessage());
                }
            }
        }
    }

    private void handle(Socket client) {
        Socket upstreamSocket = null;
        try {
            client.setTcpNoDelay(true);
            InputStream cin = new BufferedInputStream(client.getInputStream());
            OutputStream cout = client.getOutputStream();

            int ver = cin.read();
            int nm = cin.read();
            if (ver != 5 || nm < 0) {
                return;
            }
            readFully(cin, new byte[nm]);
            cout.write(new byte[]{5, 0});
            cout.flush();

            int v = cin.read();
            int cmd = cin.read();
            cin.read();
            int atyp = cin.read();
            if (v != 5 || cmd != 1) {
                reply(cout, 7);
                return;
            }

            String host;
            if (atyp == 1) {
                byte[] a = new byte[4];
                readFully(cin, a);
                host = (a[0] & 0xff) + "." + (a[1] & 0xff) + "."
                        + (a[2] & 0xff) + "." + (a[3] & 0xff);
            } else if (atyp == 3) {
                int len = cin.read();
                if (len <= 0) {
                    reply(cout, 8);
                    return;
                }
                byte[] d = new byte[len];
                readFully(cin, d);
                host = new String(d, StandardCharsets.ISO_8859_1);
            } else if (atyp == 4) {
                byte[] a = new byte[16];
                readFully(cin, a);
                host = InetAddress.getByAddress(a).getHostAddress();
            } else {
                reply(cout, 8);
                return;
            }
            int dport = (cin.read() << 8) | cin.read();

            Upstream up = dial(host, dport);
            if (up == null) {
                reply(cout, 5);
                log.line("нет туннеля до " + host + ":" + dport + " — " + lastError);
                return;
            }
            upstreamSocket = up.socket;

            cout.write(new byte[]{5, 0, 0, 1, 0, 0, 0, 0, 0, 0});
            cout.flush();

            Socket upSock = up.socket;
            Thread a = new Thread(() -> pump(cin, up.out, client, upSock), "socks-c2u");
            Thread b = new Thread(() -> pump(up.in, cout, upSock, client), "socks-u2c");
            a.setDaemon(true);
            b.setDaemon(true);
            a.start();
            b.start();
            a.join();
            b.join();
        } catch (Exception e) {
            // нормальный случай: клиент закрыл соединение
            Log.d(TAG, "client end: " + e);
        } finally {
            closeQuietly(client);
            closeQuietly(upstreamSocket);
        }
    }

    private void pump(InputStream in, OutputStream out, Socket a, Socket b) {
        byte[] buf = new byte[BUF];
        try {
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                out.flush();
            }
        } catch (IOException ignored) {
        } finally {
            closeQuietly(a);
            closeQuietly(b);
        }
    }

    private static final class Upstream {
        final Socket socket;
        final InputStream in;
        final OutputStream out;

        Upstream(Socket socket, InputStream in, OutputStream out) {
            this.socket = socket;
            this.in = in;
            this.out = out;
        }
    }

    private Upstream dial(String host, int port) {
        if (proxies.isEmpty()) {
            lastError = "список прокси пуст";
            return null;
        }
        List<Proxies.P> list = new ArrayList<>(proxies);
        Collections.shuffle(list);
        Proxies.P pref = preferred;
        if (pref != null && list.remove(pref)) {
            list.add(0, pref);
        }
        int attempts = Math.min(5, list.size());
        int[] ports = port == 443 ? new int[]{443} : new int[]{port, 443};
        for (int i = 0; i < attempts; i++) {
            Proxies.P p = list.get(i);
            for (int targetPort : ports) {
                try {
                    Upstream up = connectVia(p, host, targetPort);
                    preferred = p;
                    log.line("туннель " + host + ":" + targetPort + " через " + p.addr());
                    Log.i(TAG, "tunnel " + host + ":" + targetPort + " via " + p.addr());
                    return up;
                } catch (Exception e) {
                    lastError = p.addr() + ": " + e.getMessage();
                    Log.w(TAG, "fail " + p.addr() + " -> " + host + ":" + targetPort
                            + ": " + e);
                }
            }
        }
        Log.w(TAG, "no tunnel to " + host + ":" + port);
        return null;
    }

    private Upstream connectVia(Proxies.P p, String host, int port) throws IOException {
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress(p.host, p.port), CONNECT_TIMEOUT_MS);
            s.setTcpNoDelay(true);
            s.setSoTimeout(CONNECT_TIMEOUT_MS);

            OutputStream out = s.getOutputStream();
            InputStream in = new BufferedInputStream(s.getInputStream());

            String target = (host.indexOf(':') >= 0 ? "[" + host + "]" : host) + ":" + port;
            StringBuilder req = new StringBuilder();
            req.append("CONNECT ").append(target).append(" HTTP/1.1\r\n");
            req.append("Host: ").append(target).append("\r\n");
            if (!p.user.isEmpty()) {
                String cred = p.user + ":" + p.pass;
                String b64 = Base64.encodeToString(
                        cred.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
                req.append("Proxy-Authorization: Basic ").append(b64).append("\r\n");
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
            return new Upstream(s, in, out);
        } catch (IOException e) {
            closeQuietly(s);
            throw e;
        }
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

    private static void readFully(InputStream in, byte[] buf) throws IOException {
        int off = 0;
        while (off < buf.length) {
            int n = in.read(buf, off, buf.length - off);
            if (n < 0) {
                throw new IOException("eof");
            }
            off += n;
        }
    }

    private static void reply(OutputStream out, int code) throws IOException {
        out.write(new byte[]{5, (byte) code, 0, 1, 0, 0, 0, 0, 0, 0});
        out.flush();
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
