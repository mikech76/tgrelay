package com.mikech.tgsocks;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/** Фоновый сервис: держит SOCKS5-сервер живым и показывает уведомление. */
public class ProxyService extends Service {

    public static final int PORT = 55056;
    public static final String ACTION_STOP = "com.mikech.tgsocks.STOP";
    private static final String CHANNEL = "proxy";
    private static final int NOTIF_ID = 1;

    private static volatile boolean running = false;
    private Socks5Server server;

    public static boolean isRunning() {
        return running;
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
        Notification n = buildNotification("Прокси включён",
                "127.0.0.1:" + PORT);
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIF_ID, n);
        }
    }

    private void startServer() {
        SharedPreferences sp = getSharedPreferences("cfg", MODE_PRIVATE);
        String raw = sp.getString("proxies", Proxies.readAsset(this));
        server = new Socks5Server(PORT, Proxies.parse(raw), msg -> { });
        try {
            server.start();
            running = true;
        } catch (Exception e) {
            running = false;
            server = null;
            notifyText("Не удалось запустить: " + e.getMessage());
        }
    }

    private void shutdown() {
        if (server != null) {
            server.stop();
            server = null;
        }
        running = false;
        if (Build.VERSION.SDK_INT >= 24) {
            stopForeground(STOP_FOREGROUND_REMOVE);
        } else {
            stopForeground(true);
        }
        stopSelf();
    }

    @Override
    public void onDestroy() {
        if (server != null) {
            server.stop();
            server = null;
        }
        running = false;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void notifyText(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) {
            nm.notify(NOTIF_ID, buildNotification("Прокси", text));
        }
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (nm != null && nm.getNotificationChannel(CHANNEL) == null) {
                NotificationChannel ch = new NotificationChannel(
                        CHANNEL, "Прокси", NotificationManager.IMPORTANCE_LOW);
                ch.setDescription("Локальный SOCKS5 для Telegram");
                nm.createNotificationChannel(ch);
            }
        }
    }

    private Notification buildNotification(String title, String text) {
        Intent open = new Intent(this, MainActivity.class);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, flags);

        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            b = new Notification.Builder(this, CHANNEL);
        } else {
            b = new Notification.Builder(this);
        }
        b.setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentIntent(pi)
                .setOngoing(true);
        return b.build();
    }
}
