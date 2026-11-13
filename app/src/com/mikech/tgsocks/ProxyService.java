package com.mikech.tgsocks;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.os.Build;
import android.os.IBinder;

import java.util.Locale;

/** Фоновый сервис: держит SOCKS5-сервер и показывает статистику в уведомлении. */
public class ProxyService extends Service {

    public static final int PORT = 55056;
    public static final String ACTION_STOP = "com.mikech.tgsocks.STOP";
    private static final String CHANNEL = "proxy";
    private static final int NOTIF_ID = 1;

    private static volatile boolean running = false;
    private static volatile Socks5Server instance;

    private Socks5Server server;
    private volatile boolean statsRun = false;
    private Thread statsThread;

    public static boolean isRunning() {
        return running;
    }

    public static Socks5Server instance() {
        return instance;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            shutdown();
            return START_NOT_STICKY;
        }
        startInForeground();
        if (server == null) {
            startServer();
        }
        return START_STICKY;
    }

    private void startInForeground() {
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, buildNotification(),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIF_ID, buildNotification());
        }
    }

    private void startServer() {
        SharedPreferences sp = getSharedPreferences("cfg", MODE_PRIVATE);
        String raw = sp.getString("proxies", Proxies.readAsset(this));
        server = new Socks5Server(PORT, Proxies.parse(raw), msg -> { });
        try {
            server.start();
            running = true;
            instance = server;
            statsRun = true;
            statsThread = new Thread(this::statsLoop, "stats");
            statsThread.setDaemon(true);
            statsThread.start();
        } catch (Exception e) {
            running = false;
            server = null;
            instance = null;
            notifyText("Не удалось запустить: " + e.getMessage());
        }
    }

    private void statsLoop() {
        while (statsRun) {
            try {
                NotificationManager nm =
                        (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
                if (nm != null && server != null) {
                    nm.notify(NOTIF_ID, buildNotification());
                }
            } catch (Exception ignored) {
            }
            try {
                Thread.sleep(5000);
            } catch (InterruptedException e) {
                return;
            }
        }
    }

    private void shutdown() {
        statsRun = false;
        if (statsThread != null) {
            statsThread.interrupt();
            statsThread = null;
        }
        if (server != null) {
            server.stop();
            server = null;
        }
        running = false;
        instance = null;
        if (Build.VERSION.SDK_INT >= 24) {
            stopForeground(STOP_FOREGROUND_REMOVE);
        } else {
            stopForeground(true);
        }
        stopSelf();
    }

    @Override
    public void onDestroy() {
        statsRun = false;
        if (server != null) {
            server.stop();
            server = null;
        }
        running = false;
        instance = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void notifyText(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) {
            nm.notify(NOTIF_ID, buildNotification(text));
        }
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (nm != null && nm.getNotificationChannel(CHANNEL) == null) {
                NotificationChannel ch = new NotificationChannel(
                        CHANNEL, "Прокси", NotificationManager.IMPORTANCE_LOW);
                ch.setDescription("Локальный SOCKS5 для Telegram");
                ch.setShowBadge(false);
                nm.createNotificationChannel(ch);
            }
        }
    }

    public static String fmtBytes(long b) {
        if (b < 1024) {
            return b + " Б";
        }
        if (b < 1024L * 1024) {
            return String.format(Locale.US, "%.0f КБ", b / 1024.0);
        }
        if (b < 1024L * 1024 * 1024) {
            return String.format(Locale.US, "%.1f МБ", b / 1048576.0);
        }
        return String.format(Locale.US, "%.2f ГБ", b / 1073741824.0);
    }

    public static String fmtUptime(long ms) {
        long s = ms / 1000;
        long m = s / 60;
        long h = m / 60;
        long d = h / 24;
        if (d > 0) {
            return d + " д " + (h % 24) + " ч";
        }
        if (h > 0) {
            return h + " ч " + (m % 60) + " мин";
        }
        if (m > 0) {
            return m + " мин";
        }
        return s + " с";
    }

    private Notification buildNotification() {
        return buildNotification(null);
    }

    private Notification buildNotification(String errorText) {
        Intent open = new Intent(this, MainActivity.class);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent piOpen = PendingIntent.getActivity(this, 0, open, flags);

        Intent stop = new Intent(this, ProxyService.class).setAction(ACTION_STOP);
        PendingIntent piStop = PendingIntent.getService(this, 1, stop, flags);

        Socks5Server s = server;
        String title;
        String text;

        if (errorText != null) {
            title = "Прокси: ошибка";
            text = errorText;
        } else if (s == null) {
            title = "Прокси выключен";
            text = "127.0.0.1:" + PORT;
        } else {
            int alive = s.aliveProxies();
            if (alive < 0) {
                title = "Прокси включён";
            } else if (alive == 0) {
                title = "Прокси: нет связи";
            } else {
                title = "Прокси: " + alive + "/" + s.totalProxies() + " доступны";
            }
            text = "↑ " + fmtBytes(s.bytesUp())
                    + "   ↓ " + fmtBytes(s.bytesDown())
                    + "   ·   " + fmtUptime(s.uptimeMs());
        }

        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            b = new Notification.Builder(this, CHANNEL);
        } else {
            b = new Notification.Builder(this);
        }
        b.setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentIntent(piOpen)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setOngoing(true);

        if (s != null && s.aliveProxies() == 0) {
            String err = s.lastError();
            if (err != null && !err.isEmpty()) {
                b.setSubText(err.length() > 60 ? err.substring(0, 60) + "…" : err);
            }
        }

        if (Build.VERSION.SDK_INT >= 23) {
            b.addAction(new Notification.Action.Builder(
                    Icon.createWithResource(this,
                            android.R.drawable.ic_menu_close_clear_cancel),
                    "Стоп", piStop).build());
        }
        return b.build();
    }
}
