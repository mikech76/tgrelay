package com.mikech.tgsocks;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** Единственный экран: включить/выключить и настроить Telegram. */
public class MainActivity extends Activity {

    private TextView status;
    private Button toggle;
    private EditText proxies;
    private SharedPreferences sp;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        sp = getSharedPreferences("cfg", MODE_PRIVATE);

        float d = getResources().getDisplayMetrics().density;
        int pad = (int) (16 * d);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("Прокси для Telegram");
        title.setTextSize(22);
        root.addView(title);

        status = new TextView(this);
        status.setTextSize(16);
        status.setPadding(0, pad, 0, pad);
        root.addView(status);

        toggle = new Button(this);
        toggle.setOnClickListener(v -> toggleProxy());
        root.addView(toggle);

        Button tg = new Button(this);
        tg.setText("Настроить Telegram");
        tg.setOnClickListener(v -> openTelegram());
        root.addView(tg);

        TextView lbl = new TextView(this);
        lbl.setText("\nПрокси (по одному в строке, формат user:pass@host:port):");
        root.addView(lbl);

        proxies = new EditText(this);
        proxies.setText(sp.getString("proxies", Proxies.readAsset(this)));
        proxies.setTextSize(12);
        proxies.setMinLines(5);
        proxies.setMaxLines(10);
        proxies.setSingleLine(false);
        root.addView(proxies);

        Button save = new Button(this);
        save.setText("Сохранить список");
        save.setOnClickListener(v -> {
            sp.edit().putString("proxies", proxies.getText().toString().trim()).apply();
            Toast.makeText(this, "Сохранено. Перезапусти прокси.",
                    Toast.LENGTH_SHORT).show();
        });
        root.addView(save);

        CheckBox boot = new CheckBox(this);
        boot.setText("Запускать при включении телефона");
        boot.setChecked(sp.getBoolean("boot", false));
        boot.setOnCheckedChangeListener(
                (v, checked) -> sp.edit().putBoolean("boot", checked).apply());
        root.addView(boot);

        Button battery = new Button(this);
        battery.setText("Разрешить работу в фоне");
        battery.setOnClickListener(v -> askBattery());
        root.addView(battery);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);

        askNotifications();
    }

    @Override
    protected void onResume() {
        super.onResume();
        updateUi();
    }

    private void updateUi() {
        boolean on = ProxyService.isRunning();
        if (!on) {
            status.setText("Статус: выключен");
            toggle.setText("Включить");
            return;
        }
        Socks5Server s = ProxyService.instance();
        StringBuilder sb = new StringBuilder("Статус: включён, 127.0.0.1:")
                .append(ProxyService.PORT);
        if (s != null) {
            int alive = s.aliveProxies();
            if (alive >= 0) {
                sb.append("\nПрокси: ").append(alive)
                        .append("/").append(s.totalProxies()).append(" доступны");
            }
            sb.append("\n↑ ").append(ProxyService.fmtBytes(s.bytesUp()))
                    .append("   ↓ ").append(ProxyService.fmtBytes(s.bytesDown()))
                    .append("\nВ работе: ").append(ProxyService.fmtUptime(s.uptimeMs()))
                    .append(", соединений: ").append(s.activeConnections());
        }
        status.setText(sb.toString());
        toggle.setText("Выключить");
    }

    private void toggleProxy() {
        Intent i = new Intent(this, ProxyService.class);
        if (ProxyService.isRunning()) {
            i.setAction(ProxyService.ACTION_STOP);
            startService(i);
        } else if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(i);
        } else {
            startService(i);
        }
        status.postDelayed(this::updateUi, 500);
    }

    private void openTelegram() {
        String link = "tg://socks?server=127.0.0.1&port=" + ProxyService.PORT;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(link)));
            Toast.makeText(this, "В Telegram нажмите «Включить»",
                    Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(
                        "https://t.me/socks?server=127.0.0.1&port="
                                + ProxyService.PORT)));
            } catch (Exception e2) {
                Toast.makeText(this, "Telegram не найден",
                        Toast.LENGTH_LONG).show();
            }
        }
    }

    private void askBattery() {
        if (Build.VERSION.SDK_INT < 23) {
            return;
        }
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (pm != null && pm.isIgnoringBatteryOptimizations(getPackageName())) {
            Toast.makeText(this, "Уже разрешено", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            Intent i = new Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:" + getPackageName()));
            startActivity(i);
        } catch (Exception e) {
            Toast.makeText(this, "Не удалось открыть настройки",
                    Toast.LENGTH_SHORT).show();
        }
    }

    private void askNotifications() {
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                    != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(
                        new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
            }
        }
    }
}
