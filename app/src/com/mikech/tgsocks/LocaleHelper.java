package com.mikech.tgsocks;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.Build;

import java.util.Locale;

/** Выбранный язык приложения: ru или en. По умолчанию — язык системы. */
public final class LocaleHelper {

    private static final String PREFS = "cfg";
    private static final String KEY = "lang";

    private LocaleHelper() {
    }

    public static String current(Context ctx) {
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String lang = sp.getString(KEY, "");
        if (lang == null || lang.isEmpty()) {
            lang = Locale.getDefault().getLanguage();
        }
        return "ru".equals(lang) ? "ru" : "en";
    }

    public static void set(Context ctx, String lang) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(KEY, lang).apply();
    }

    /** Контекст с ресурсами выбранного языка. */
    public static Context wrap(Context ctx) {
        try {
            Locale locale = new Locale(current(ctx));
            Configuration cfg = new Configuration(ctx.getResources().getConfiguration());
            cfg.setLocale(locale);
            if (Build.VERSION.SDK_INT >= 17) {
                cfg.setLayoutDirection(locale);
            }
            return ctx.createConfigurationContext(cfg);
        } catch (Exception e) {
            return ctx;
        }
    }
}
