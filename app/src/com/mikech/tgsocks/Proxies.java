package com.mikech.tgsocks;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Разбор списка HTTP-прокси вида  user:pass@host:port;host:port */
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

        P(String host, int port, String user, String pass) {
            this.host = host;
            this.port = port;
            this.user = user;
            this.pass = pass;
        }

        public String addr() {
            return host + ":" + port;
        }
    }

    private Proxies() {
    }

    public static List<P> parse(String raw) {
        List<P> out = new ArrayList<>();
        if (raw == null) {
            return out;
        }
        for (String item : raw.split("[;\\n\\r]+")) {
            item = item.trim();
            if (item.isEmpty() || item.startsWith("#")) {
                continue;
            }
            String cred = null;
            String hp = item;
            int at = item.lastIndexOf('@');
            if (at > 0) {
                cred = item.substring(0, at);
                hp = item.substring(at + 1);
            }
            int c = hp.lastIndexOf(':');
            if (c <= 0) {
                continue;
            }
            String host = hp.substring(0, c).trim();
            int port;
            try {
                port = Integer.parseInt(hp.substring(c + 1).trim());
            } catch (NumberFormatException e) {
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
            out.add(new P(host, port, user, pass));
        }
        return out;
    }
}
