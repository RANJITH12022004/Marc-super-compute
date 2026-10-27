package com.bee.island;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.view.KeyEvent;
import android.view.inputmethod.InputConnection;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** On-device intents for phone tools. Never reboot/shutdown. */
final class PhoneActions {
    private PhoneActions() {
    }

    static Map<String, Object> run(Context context, Map<String, Object> step) {
        Map<String, Object> result = new HashMap<String, Object>();
        result.put("id", step == null ? null : step.get("id"));
        Intent intent = intentFor(step);
        if (intent == null || context == null) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "unknown");
            return result;
        }
        if ("type".equals(intent.getAction())) {
            result.put("ok", Boolean.TRUE);
            result.put("typed", intent.getStringExtra("text"));
            return result;
        }
        try {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "open failed");
        }
        return result;
    }

    static Intent intentFor(Map<String, Object> step) {
        if (step == null) {
            return null;
        }
        String tool = String.valueOf(step.get("tool") == null ? "" : step.get("tool"))
                .toLowerCase(Locale.US);
        if (tool.contains("reboot") || tool.contains("shutdown")) {
            return null;
        }
        if ("music_play".equals(tool)) {
            tool = "play_music";
        } else if ("phone_dial".equals(tool)) {
            tool = "dial";
        } else if ("app_open".equals(tool)) {
            tool = "open_app";
        } else if ("type".equals(tool)) {
            tool = "type_into";
        }
        Map<?, ?> args = step.get("args") instanceof Map ? (Map<?, ?>) step.get("args") : new HashMap<String, Object>();
        if ("whatsapp_send".equals(tool)) {
            String body = str(args, "text");
            Intent i = new Intent(Intent.ACTION_SEND);
            i.setPackage("com.whatsapp");
            i.setType("text/plain");
            i.putExtra(Intent.EXTRA_TEXT, body);
            i.putExtra("sms_body", body);
            return i;
        }
        if ("play_music".equals(tool)) {
            String query = str(args, "query");
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setPackage("com.spotify.music");
            if (query.isEmpty()) {
                i.setData(Uri.parse("market://details?id=com.spotify.music"));
            } else {
                i.setData(Uri.parse("spotify:search:" + Uri.encode(query)));
            }
            return i;
        }
        if ("mail_compose".equals(tool)) {
            Intent i = new Intent(Intent.ACTION_SENDTO);
            i.setData(Uri.parse("mailto:" + str(args, "to")));
            i.putExtra(Intent.EXTRA_SUBJECT, str(args, "subject"));
            return i;
        }
        if ("dial".equals(tool)) {
            Intent i = new Intent(Intent.ACTION_DIAL);
            i.setData(Uri.parse("tel:" + str(args, "to")));
            return i;
        }
        if ("open_app".equals(tool)) {
            String app = str(args, "app").toLowerCase(Locale.US);
            Intent i = new Intent(Intent.ACTION_MAIN);
            i.addCategory(Intent.CATEGORY_LAUNCHER);
            if (app.contains("spotify")) {
                i.setPackage("com.spotify.music");
            } else if (app.contains("youtube") || app.contains("youtu")) {
                i.setPackage("com.google.android.youtube");
            } else if (app.contains(".") && !app.contains(" ")) {
                i.setPackage(str(args, "app"));
            }
            return i;
        }
        if ("type_into".equals(tool)) {
            Intent i = new Intent("type");
            i.putExtra("text", str(args, "text"));
            return i;
        }
        return null;
    }

    static void typeInto(InputConnection ic, String text) {
        if (ic == null || text == null) {
            return;
        }
        ic.commitText(text, 1);
        ic.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER));
    }

    private static String str(Map<?, ?> args, String key) {
        Object v = args.get(key);
        return v == null ? "" : String.valueOf(v);
    }
}
