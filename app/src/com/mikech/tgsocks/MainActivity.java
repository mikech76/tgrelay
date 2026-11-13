package com.mikech.tgsocks;

import android.app.Activity;
import android.content.Context;
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

/** Единственный экран: включить/выключить, язык, список прокси, настройка Telegram. */
public class MainActivity extends Activity {

    private static final String NL = System.getProperty("line.separator");

    private TextView status;
    private Button toggle;
    private Button langButton;
    private EditText proxies;
    private SharedPreferences sp;

    @Override
    protected void attachBaseContext(Context base) {
        super.attachBaseContext(LocaleHelper.wrap(base));
    }

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
        title.setText(R.string.title);
        title.setTextSize(22);
        root.addView(title);

        langButton = new Button(this);
        langButton.setText(isRussian() ? R.string.lang_en : R.string.lang_ru);
        langButton.setOnClickListener(v -> switchLanguage());
        root.addView(langButton);

        status = new TextView(this);
        status.setTextSize(15);
        status.setPadding(0, pad, 0, pad);
        root.addView(status);

        toggle = new Button(this);
        toggle.setOnClickListener(v -> toggleProxy());
        root.addView(toggle);

        Button tg = new Button(this);
        tg.setText(R.string.btn_setup);
        tg.setOnClickListener(v -> openTelegram());
        root.addView(tg);

        TextView hint = new TextView(this);
        hint.setText(R.string.proxy_hint);
        hint.setPadding(0, pad, 0, 0);
        root.addView(hint);

        proxies = new EditText(this);
        proxies.setText(sp.getString("proxies", Proxies.readAsset(this)));
        proxies.setTextSize(12);
        proxies.setMinLines(5);
        proxies.setMaxLines(10);
        proxies.setSingleLine(false);
        root.addView(proxies);

        Button save = new Button(this);
        save.setText(R.string.btn_save);
        save.setOnClickListener(v -> {
            sp.edit().putString("proxies", proxies.getText().toString().trim()).apply();
            Toast.makeText(this, R.string.saved, Toast.LENGTH_SHORT).show();
        });
        root.addView(save);

        CheckBox boot = new CheckBox(this);
        boot.setText(R.string.boot_opt);
        boot.setChecked(sp.getBoolean("boot", false));
        boot.setOnCheckedChangeListener(
                (v, checked) -> sp.edit().putBoolean("boot", checked).apply());
        root.addView(boot);

        Button battery = new Button(this);
        battery.setText(R.string.battery);
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

    private boolean isRussian() {
        return "ru".equals(LocaleHelper.current(this));
    }

    private void switchLanguage() {
        LocaleHelper.set(this, isRussian() ? "en" : "ru");
        recreate();
    }

    private void updateUi() {
        boolean on = ProxyService.isRunning();
        if (!on) {
            status.setText(R.string.status_off);
            toggle.setText(R.string.btn_start);
            return;
        }
        Socks5Server s = ProxyService.instance();
        StringBuilder sb = new StringBuilder(getString(R.string.status_on, ProxyService.PORT));
        if (s != null) {
            int alive = s.aliveProxies();
            if (alive >= 0) {
                sb.append(NL).append(getString(R.string.pool_state,
                        alive, s.totalProxies()));
            }
            sb.append(NL).append(getString(R.string.traffic,
                    ProxyService.fmtBytes(this, s.bytesUp()),
                    ProxyService.fmtBytes(this, s.bytesDown())));
            sb.append(NL).append(getString(R.string.uptime,
                            ProxyService.fmtUptime(this, s.uptimeMs())))
                    .append(", ")
                    .append(getString(R.string.connections, s.activeConnections()));
        }
        status.setText(sb.toString());
        toggle.setText(R.string.btn_stop);
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
            Toast.makeText(this, R.string.tg_added, Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(
                        "https://t.me/socks?server=127.0.0.1&port="
                                + ProxyService.PORT)));
            } catch (Exception e2) {
                Toast.makeText(this, R.string.tg_not_found, Toast.LENGTH_LONG).show();
            }
        }
    }

    private void askBattery() {
        if (Build.VERSION.SDK_INT < 23) {
            return;
        }
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (pm != null && pm.isIgnoringBatteryOptimizations(getPackageName())) {
            Toast.makeText(this, R.string.battery_ok, Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            Intent i = new Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:" + getPackageName()));
            startActivity(i);
        } catch (Exception e) {
            Toast.makeText(this, R.string.battery_fail, Toast.LENGTH_SHORT).show();
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
