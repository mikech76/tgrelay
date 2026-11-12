package com.mikech.tgsocks;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

/** Автозапуск после включения телефона, если включена галочка. */
public class BootReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        SharedPreferences sp = context.getSharedPreferences("cfg", Context.MODE_PRIVATE);
        if (!sp.getBoolean("boot", false)) {
            return;
        }
        Intent svc = new Intent(context, ProxyService.class);
        if (Build.VERSION.SDK_INT >= 26) {
            context.startForegroundService(svc);
        } else {
            context.startService(svc);
        }
    }
}
