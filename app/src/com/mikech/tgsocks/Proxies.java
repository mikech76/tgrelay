package com.mikech.tgsocks;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Разбор списка прокси. Строка может быть со схемой или без:
 *
 * <pre>
 *   user:pass@host:port          тип определится сам (HTTP, потом SOCKS5/4)
 *   http://user:pass@host:port   HTTP CONNECT
 *   https://...                  https-прокси, при отказе — CONNECT по TLS
 *   socks5://...  socks5h://...  SOCKS5
 *   socks://...                  тоже SOCKS5 (пятёрка по умолчанию)
 *   socks4://...  socks4a://...  SOCKS4 / 4a
 * </pre>
 *
 * Порт можно не писать: http 8080, https 443, socks 1080.
 */
public final class Proxies {

    /** По умолчанию список пуст: пользователь вставляет свой в приложении. */
    public static final String DEFAULT = "";

    /** Читает список из assets/default_proxies.txt (если он есть в сборке). */
    public static String readAsset(Context ctx) {
        try (InputStream in = ctx.getAssets().open("default_proxies.txt")) {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) {
                b.write(buf, 0, n);
            }
            return new String(b.toByteArray(), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        }
    }

    public static final class P {
        public final String host;
        public final int port;
        public final String user;
        public final String pass;
        /** http / https / socks5 / socks4; null — определить автоматически. */
        public String kind;

        P(String host, int port, String user, String pass, String kind) {
            this.host = host;
            this.port = port;
            this.user = user;
            this.pass = pass;
            this.kind = kind;
        }

        public String addr() {
            return host + ":" + port;
        }
    }

    private Proxies() {
    }

    /** Убирает комментарий в конце строки: "текст # пояснение" -> "текст". */
    private static String stripComment(String s) {
        for (int i = 1; i < s.length(); i++) {
            if (s.charAt(i) == '#' && Character.isWhitespace(s.charAt(i - 1))) {
                return s.substring(0, i).trim();
            }
        }
        return s;
    }

    private static String kindOf(String scheme) {
        switch (scheme) {
            case "http":
                return "http";
            case "https":
                return "https";
            case "socks":
            case "socks5":
            case "socks5h":
                return "socks5";
            case "socks4":
            case "socks4a":
                return "socks4";
            default:
                return null;
        }
    }

    private static int defaultPort(String kind) {
        if ("http".equals(kind)) {
            return 8080;
        }
        if ("https".equals(kind)) {
            return 443;
        }
        if ("socks5".equals(kind) || "socks4".equals(kind)) {
            return 1080;
        }
        return 8080;
    }

    public static List<P> parse(String raw) {
        List<P> out = new ArrayList<>();
        if (raw == null) {
            return out;
        }
        for (String item : raw.split("[;\\n\\r]+")) {
            item = stripComment(item.trim()).trim();
            if (item.isEmpty() || item.startsWith("#")) {
                continue;
            }

            String scheme = "";
            int sep = item.indexOf("://");
            if (sep > 0) {
                scheme = item.substring(0, sep).trim().toLowerCase();
                item = item.substring(sep + 3);
                if (kindOf(scheme) == null) {
                    continue;               // неизвестная схема — пропускаем
                }
            }
            String kind = scheme.isEmpty() ? null : kindOf(scheme);

            String cred = null;
            String hp = item;
            int at = item.lastIndexOf('@');
            if (at > 0) {
                cred = item.substring(0, at);
                hp = item.substring(at + 1);
            }

            String host;
            String portText;
            if (hp.startsWith("[")) {                  // [IPv6]:port
                int close = hp.indexOf(']');
                if (close < 0) {
                    continue;
                }
                host = hp.substring(1, close);
                portText = hp.substring(close + 1);
                if (portText.startsWith(":")) {
                    portText = portText.substring(1);
                }
            } else {
                int c = hp.lastIndexOf(':');
                if (c <= 0) {
                    host = hp.trim();
                    portText = "";
                } else {
                    host = hp.substring(0, c).trim();
                    portText = hp.substring(c + 1).trim();
                }
            }

            int port;
            if (portText.isEmpty()) {
                port = defaultPort(kind);
            } else {
                try {
                    port = Integer.parseInt(portText);
                } catch (NumberFormatException e) {
                    continue;
                }
            }
            if (host.isEmpty() || port <= 0 || port > 65535) {
                continue;
            }

            String user = "";
            String pass = "";
            if (cred != null) {
                int cc = cred.indexOf(':');
                if (cc > 0) {
                    user = cred.substring(0, cc);
                    pass = cred.substring(cc + 1);
                } else {
                    user = cred;
                }
            }
            out.add(new P(host, port, user, pass, kind));
        }
        return out;
    }
}
