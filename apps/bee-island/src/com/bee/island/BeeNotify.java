package com.bee.island;

import android.app.Notification;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Stores recent status-bar notifications for chat analysis. */
public class BeeNotify extends NotificationListenerService {

    private static final int CAP = 40;
    private static final Object LOCK = new Object();
    private static final LinkedHashMap<String, Map<String, Object>> ROWS =
            new LinkedHashMap<String, Map<String, Object>>() {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, Map<String, Object>> eldest) {
                    return size() > CAP;
                }
            };

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null) {
            return;
        }
        try {
            String pkg = sbn.getPackageName();
            if (pkg == null || "com.bee.island".equals(pkg)
                    || "android".equals(pkg)
                    || pkg.startsWith("com.android.systemui")) {
                return;
            }
            Notification n = sbn.getNotification();
            if (n == null) {
                return;
            }
            Bundle extras = n.extras;
            CharSequence titleCs = extras == null ? null : extras.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence textCs = extras == null ? null : extras.getCharSequence(Notification.EXTRA_TEXT);
            if (textCs == null && extras != null) {
                textCs = extras.getCharSequence(Notification.EXTRA_BIG_TEXT);
            }
            String title = titleCs == null ? "" : String.valueOf(titleCs).trim();
            String text = textCs == null ? "" : String.valueOf(textCs).trim();
            if (title.isEmpty() && text.isEmpty()) {
                return;
            }
            String key = sbn.getKey();
            if (key == null || key.isEmpty()) {
                key = pkg + "|" + title + "|" + text;
            }
            Map<String, Object> row = new LinkedHashMap<String, Object>();
            row.put("app", pkg);
            row.put("title", title);
            row.put("text", text);
            row.put("when", Long.valueOf(sbn.getPostTime()));
            row.put("key", key);
            synchronized (LOCK) {
                ROWS.remove(key);
                ROWS.put(key, row);
            }
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
    }

    public static List<Map<String, Object>> snapshot() {
        synchronized (LOCK) {
            return new ArrayList<Map<String, Object>>(ROWS.values());
        }
    }

    public static String spokenSummary() {
        List<Map<String, Object>> rows = snapshot();
        if (rows.isEmpty()) {
            return "No new notifications.";
        }
        StringBuilder b = new StringBuilder();
        int n = Math.min(8, rows.size());
        b.append(n).append(" recent. ");
        for (int i = rows.size() - 1; i >= rows.size() - n && i >= 0; i--) {
            Map<String, Object> row = rows.get(i);
            String app = shortApp(String.valueOf(row.get("app")));
            String title = String.valueOf(row.get("title"));
            String text = String.valueOf(row.get("text"));
            b.append(app);
            if (title != null && !title.isEmpty() && !"null".equals(title)) {
                b.append(": ").append(clamp(title, 40));
            }
            if (text != null && !text.isEmpty() && !"null".equals(text)) {
                b.append(" — ").append(clamp(text, 60));
            }
            b.append(". ");
        }
        return b.toString().trim();
    }

    public static String suggestFor(String who) {
        String want = who == null ? "" : who.trim().toLowerCase(Locale.US);
        List<Map<String, Object>> rows = snapshot();
        Map<String, Object> hit = null;
        for (int i = rows.size() - 1; i >= 0; i--) {
            Map<String, Object> row = rows.get(i);
            String blob = (String.valueOf(row.get("title")) + " "
                    + String.valueOf(row.get("text")) + " "
                    + String.valueOf(row.get("app"))).toLowerCase(Locale.US);
            if (want.isEmpty() || blob.contains(want)) {
                hit = row;
                break;
            }
        }
        if (hit == null) {
            return "No matching notification to reply to.";
        }
        String title = String.valueOf(hit.get("title"));
        String text = String.valueOf(hit.get("text"));
        String draft = "Got it — thanks!";
        String low = (title + " " + text).toLowerCase(Locale.US);
        if (low.contains("?")) {
            draft = "Sure, I'll check and get back to you.";
        } else if (low.contains("meet") || low.contains("call")) {
            draft = "Sounds good. What time works?";
        } else if (low.contains("thanks") || low.contains("thank")) {
            draft = "Anytime!";
        }
        String whoLabel = want.isEmpty() ? title : who;
        return "From " + clamp(whoLabel, 32) + ": " + clamp(text, 80)
                + " Suggested reply: " + draft;
    }

    private static String shortApp(String pkg) {
        if (pkg == null) {
            return "App";
        }
        if (pkg.contains("whatsapp")) {
            return "WhatsApp";
        }
        if (pkg.contains("instagram")) {
            return "Instagram";
        }
        if (pkg.contains("gmail")) {
            return "Gmail";
        }
        int dot = pkg.lastIndexOf('.');
        if (dot >= 0 && dot + 1 < pkg.length()) {
            String tail = pkg.substring(dot + 1);
            if (!tail.isEmpty()) {
                return Character.toUpperCase(tail.charAt(0)) + tail.substring(1);
            }
        }
        return pkg;
    }

    private static String clamp(String s, int max) {
        if (s == null) {
            return "";
        }
        String t = s.trim();
        if (t.length() <= max) {
            return t;
        }
        return t.substring(0, Math.max(0, max - 1)) + "…";
    }
}
