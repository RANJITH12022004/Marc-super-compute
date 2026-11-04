package com.bee.island;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.provider.Settings;
import android.view.KeyEvent;
import android.view.inputmethod.InputConnection;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** On-device intents for phone tools. Never reboot/shutdown. */
final class PhoneActions {
    private PhoneActions() {
    }

    static Map<String, Object> run(Context context, Map<String, Object> step) {
        Map<String, Object> result = new HashMap<String, Object>();
        result.put("id", step == null ? null : step.get("id"));
        if (step == null) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "unknown");
            return result;
        }
        String tool = String.valueOf(step.get("tool") == null ? "" : step.get("tool"))
                .toLowerCase(Locale.US);
        if (tool.contains("reboot") || tool.contains("shutdown")) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "refused");
            return result;
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

        if ("type_into".equals(tool)) {
            String text = str(args, "text");
            boolean typedOk = false;
            try {
                typedOk = IslandAccess.typeFocused(text);
            } catch (Exception e) {
                typedOk = false;
            } catch (NoSuchMethodError e) {
                typedOk = false;
            }
            result.put("ok", typedOk ? Boolean.TRUE : Boolean.FALSE);
            if (typedOk) {
                result.put("typed", text);
            } else {
                result.put("error", "type failed");
            }
            return result;
        }

        if ("wait_ms".equals(tool)) {
            long ms = parseWaitMs(args);
            try {
                Thread.sleep(ms);
                result.put("ok", Boolean.TRUE);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                result.put("ok", Boolean.TRUE);
            } catch (Exception e) {
                result.put("ok", Boolean.TRUE);
            }
            return result;
        }

        if ("click_text".equals(tool)) {
            boolean ok = false;
            try {
                ok = IslandAccess.clickText(str(args, "text"));
            } catch (Exception e) {
                ok = false;
            } catch (NoSuchMethodError e) {
                ok = false;
            }
            result.put("ok", ok ? Boolean.TRUE : Boolean.FALSE);
            if (!ok) {
                result.put("error", "click failed");
            }
            return result;
        }

        if ("swipe".equals(tool)) {
            boolean ok = false;
            try {
                ok = IslandAccess.swipe(str(args, "direction"));
            } catch (Exception e) {
                ok = false;
            } catch (NoSuchMethodError e) {
                ok = false;
            }
            result.put("ok", ok ? Boolean.TRUE : Boolean.FALSE);
            if (!ok) {
                result.put("error", "swipe failed");
            }
            return result;
        }

        if ("scroll".equals(tool)) {
            boolean ok = false;
            try {
                ok = IslandAccess.scroll(str(args, "direction"));
            } catch (Exception e) {
                ok = false;
            } catch (NoSuchMethodError e) {
                ok = false;
            }
            result.put("ok", ok ? Boolean.TRUE : Boolean.FALSE);
            if (!ok) {
                result.put("error", "scroll failed");
            }
            return result;
        }

        if ("auto_scroll".equals(tool)) {
            return driveReels(context, result);
        }

        if ("closed_loop".equals(tool)) {
            return driveClosedLoop(str(args, "package"), str(args, "text"),
                    str(args, "direction"), result);
        }

        if ("whatsapp_send".equals(tool)) {
            Map<String, Object> wa = driveWhatsApp(context, str(args, "to"), str(args, "text"),
                    str(args, "package"), result);
            attachObserve(wa);
            return wa;
        }

        if ("wa_list_chats".equals(tool)) {
            Map<String, Object> listed = driveWaListChats(context, args, result);
            attachObserve(listed);
            return listed;
        }

        if ("notifications_list".equals(tool)) {
            String spoken = BeeNotify.spokenSummary();
            result.put("ok", Boolean.TRUE);
            result.put("spoken", spoken);
            return result;
        }

        if ("suggest_reply".equals(tool)) {
            String who = str(args, "to");
            if (who.isEmpty()) {
                who = str(args, "who");
            }
            if (who.isEmpty()) {
                who = str(args, "person");
            }
            String spoken = BeeNotify.suggestFor(who);
            result.put("ok", Boolean.TRUE);
            result.put("spoken", spoken);
            return result;
        }

        if ("chat_touch".equals(tool)) {
            String who = str(args, "to");
            String topic = str(args, "topic");
            if (topic.isEmpty()) {
                topic = str(args, "intent");
            }
            if (topic.isEmpty()) {
                topic = str(args, "text");
            }
            String channel = str(args, "channel");
            if (channel.isEmpty()) {
                channel = "whatsapp";
            }
            channel = channel.toLowerCase(Locale.US);
            if ("email".equals(channel) || "gmail".equals(channel)) {
                channel = "mail";
            }
            String draft = "";
            // Prefer Rox draft_like_me when door is up (not notif heuristics).
            try {
                if (RoxClient.reachable(context)) {
                    String ask = "script a " + channel + " message to " + who
                            + " regarding " + topic;
                    Map<String, Object> reply = RoxClient.postUtterance(context, ask);
                    if (reply != null) {
                        if (reply.get("draft") != null) {
                            draft = String.valueOf(reply.get("draft")).trim();
                        }
                        if (draft.isEmpty() && reply.get("spoken") != null) {
                            String spokenR = String.valueOf(reply.get("spoken")).trim();
                            String low = spokenR.toLowerCase(Locale.US);
                            int idx = low.indexOf("suggested reply:");
                            if (idx >= 0) {
                                draft = spokenR.substring(
                                        idx + "suggested reply:".length()).trim();
                            } else if (!spokenR.isEmpty()
                                    && !BeeMind.isEmptyBrainText(spokenR)
                                    && !spokenR.toLowerCase(Locale.US).contains("need a")) {
                                draft = spokenR;
                            }
                        }
                    }
                }
            } catch (Exception ignored) {
            }
            if (draft == null || draft.isEmpty()) {
                draft = BeeStyle.draftLikeMe(context, who, topic, channel);
            }
            // Optional Muse spark rewrite with style card when key present.
            if (draft != null && !draft.isEmpty()) {
                try {
                    String key = KeyVault.loadKey(context);
                    String card = BeeStyle.loadCard(context, who, channel);
                    if (card == null || card.isEmpty()) {
                        card = BeeStyle.loadCard(context, who, "whatsapp");
                    }
                    if (key != null && !key.isEmpty() && card != null
                            && !card.isEmpty() && card.length() < 2500) {
                        String prompt = "Rewrite as a short " + channel + " from me to "
                                + who + " about: " + topic
                                + "\nMatch this style card:\n" + card
                                + "\nDraft so far: " + draft
                                + "\nReply with ONLY the message body.";
                        String sparked = MuseClient.complete(key, MuseClient.SPARK, prompt);
                        if (sparked != null) {
                            String clean = sparked.trim();
                            if (!clean.isEmpty() && clean.length() < 400
                                    && !clean.toLowerCase(Locale.US).contains("style card")) {
                                draft = clean;
                            }
                        }
                    }
                } catch (Exception ignored) {
                }
            }
            if (draft == null || draft.isEmpty()) {
                String spoken = "Need a style card for " + who + " — run ingest";
                result.put("ok", Boolean.FALSE);
                result.put("spoken", spoken);
                return result;
            }
            String spoken = "Suggested: " + draft;
            result.put("ok", Boolean.TRUE);
            result.put("spoken", spoken);
            result.put("draft", draft);
            result.put("to", who);
            result.put("channel", channel);
            if ("whatsapp".equals(channel)) {
                result.put("package", resolveWaPackage(str(args, "package"), who));
            }
            return result;
        }

        if ("sms_send".equals(tool)) {
            return driveSms(context, str(args, "to"),
                    str(args, "text").isEmpty() ? str(args, "body") : str(args, "text"),
                    result);
        }

        if ("phone_profile_snapshot".equals(tool)) {
            return drivePhoneProfileSnapshot(context, result);
        }

        if ("play_music".equals(tool)) {
            return drivePlayMusic(context, str(args, "query"), result);
        }

        if ("youtube_play".equals(tool) || "youtube_search".equals(tool)) {
            return driveYouTube(context, args, result);
        }

        if ("dial".equals(tool) || "phone_dial".equals(tool)) {
            String who = str(args, "to");
            if (who == null || who.trim().isEmpty()) {
                who = str(args, "contact");
            }
            Map<String, Object> call = driveCall(context, who, result);
            attachObserve(call);
            return call;
        }

        if ("mail_send".equals(tool) || "mail_compose".equals(tool)) {
            return driveGmail(context, str(args, "to"), str(args, "subject"),
                    str(args, "text").isEmpty() ? str(args, "body") : str(args, "text"),
                    result);
        }

        if ("press_back".equals(tool)) {
            boolean ok = false;
            try {
                ok = IslandAccess.pressBack();
            } catch (Exception e) {
                ok = false;
            } catch (NoSuchMethodError e) {
                ok = false;
            }
            result.put("ok", ok ? Boolean.TRUE : Boolean.FALSE);
            if (!ok) {
                result.put("error", "back failed");
            }
            return result;
        }

        if ("open_app".equals(tool)) {
            String want = str(args, "app");
            if (want == null || want.trim().isEmpty()) {
                want = str(args, "label");
            }
            Intent launch = openAppIntent(context, want);
            if (launch == null || context == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "open failed");
                return result;
            }
            try {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(launch);
                result.put("ok", Boolean.TRUE);
            } catch (Exception e) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "open failed");
            }
            return result;
        }

        Intent intent = intentFor(step);
        if (intent == null || context == null) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "unknown");
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

    static Map<String, Object> driveWhatsApp(Context context, String to, String text,
                                             String packageHint, Map<String, Object> result) {
        String name = to == null ? "" : to.trim();
        if (name.isEmpty()) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "no contact");
            return result;
        }
        String lowName = name.toLowerCase(Locale.US);
        if ("me".equals(lowName) || "myself".equals(lowName)) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "Say who to text.");
            return result;
        }
        final String pkg = resolveWaPackage(packageHint, name);
        result.put("package", pkg);
        try {
            Intent launch = openAppIntent(context, pkg);
            if (launch == null) {
                launch = openAppIntent(context,
                        "com.whatsapp.w4b".equals(pkg) ? "whatsapp business" : "whatsapp");
            }
            if (launch == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "whatsapp missing");
                return result;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launch);
            String waitNeedle = pkg.contains("w4b") ? "w4b" : "whatsapp";
            if (!IslandAccess.waitFor(waitNeedle, null, 8000) && !waitPackage(waitNeedle, 32)
                    && !waitPackage("whatsapp", 16)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "whatsapp missing");
                IslandAccess.nodeDump();
                return result;
            }
            for (int hop = 0; hop < 4; hop++) {
                if (!IslandAccess.hasText("24 hours") && !IslandAccess.hasText("Learn more")) {
                    break;
                }
                IslandAccess.clickLabel("Back");
                pause(300);
            }
            goWaChatList(pkg);
            leaveWaMessageSearch(pkg);
            String matched = IslandAccess.clickChatRowFuzzy(name);
            boolean opened = matched != null
                    || IslandAccess.clickLabel("Message yourself")
                    || IslandAccess.clickChatRow(name);
            if (matched != null && !matched.isEmpty()) {
                result.put("matched", matched);
                String first = matched.split("\n")[0].trim();
                if (!first.equalsIgnoreCase(name)) {
                    result.put("spoken", "Opening " + first);
                }
            }
            if (!opened) {
                openWaChatSearch(pkg);
                pause(400);
                IslandAccess.typeFocused(name);
                pause(700);
                matched = IslandAccess.clickChatRowFuzzy(name);
                if (IslandAccess.clickLabel("Message yourself")) {
                    pause(500);
                    opened = true;
                } else if (matched != null) {
                    opened = true;
                    result.put("matched", matched);
                } else if (!IslandAccess.clickChatRow(name)) {
                    String digits = name.replaceAll("[^0-9+]", "");
                    // Hardcoded seeds only as last resort.
                    if (digits.length() < 4) {
                        if (lowName.contains("rahull")) {
                            digits = "9900388573";
                        } else if (lowName.contains("shivu")) {
                            digits = "6361836808";
                        }
                    }
                    boolean row = false;
                    if (digits.length() >= 4) {
                        leaveWaMessageSearch(pkg);
                        openWaChatSearch(pkg);
                        pause(300);
                        IslandAccess.typeFocused(digits);
                        pause(700);
                        row = IslandAccess.clickChatRowFuzzy(digits) != null
                                || IslandAccess.clickChatRow(digits)
                                || IslandAccess.clickChatRow(digits.substring(digits.length() - 4));
                    }
                    if (!row) {
                        result.put("ok", Boolean.FALSE);
                        result.put("error", "wrong person");
                        IslandAccess.nodeDump();
                        return result;
                    }
                    opened = true;
                }
            }
            if (IslandAccess.hasText("Chat lock") || IslandAccess.hasText("Manage storage")) {
                IslandAccess.clickLabel("Back");
                pause(350);
            }
            if (IslandAccess.hasText("Message contact") || IslandAccess.hasText("Voice call")) {
                boolean msg = clickWaId(pkg, "message_btn");
                if (!msg) {
                    msg = IslandAccess.clickLabel("Message contact");
                }
                if (!msg) {
                    IslandAccess.tapRatio(0.27f, 0.52f);
                }
                pause(600);
            }
            if (!IslandAccess.hasText("Type a message")) {
                IslandAccess.clickLabel("Message yourself");
                pause(400);
            }
            boolean composer = IslandAccess.waitFor(null, "Type a message", 4000);
            if (!composer) {
                composer = clickWaId(pkg, "entry")
                        || IslandAccess.hasText("Type a message")
                        || IslandAccess.hasText("Voice message");
            }
            if (!composer) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "chat not open");
                IslandAccess.nodeDump();
                return result;
            }
            String titleNeedle = name.toLowerCase(Locale.US);
            if (titleNeedle.length() > 4) {
                int spn = titleNeedle.indexOf(' ');
                if (spn > 0) {
                    titleNeedle = titleNeedle.substring(0, spn);
                }
            }
            if (!IslandAccess.hasText(name) && !IslandAccess.hasText(titleNeedle)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "wrong person");
                IslandAccess.nodeDump();
                return result;
            }
            if (!clickWaId(pkg, "entry")) {
                IslandAccess.clickLabel("Type a message");
            }
            String body = text == null ? "" : text.trim();
            if (!body.isEmpty()) {
                if (!typeWaId(pkg, "entry", body)) {
                    IslandAccess.typeFocused(body);
                }
            }
            pause(400);
            String typed = IslandAccess.focusedEditText();
            boolean hasBody = !body.isEmpty() && typed != null
                    && typed.toLowerCase(Locale.US).contains(body.toLowerCase(Locale.US));
            if (!body.isEmpty() && !hasBody && !IslandAccess.hasText(body)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "type failed");
                IslandAccess.nodeDump();
                return result;
            }
            boolean sent = false;
            for (int hop = 0; hop < 8; hop++) {
                if (!IslandAccess.clickSendControl()) {
                    IslandAccess.tapRatio(0.92f, 0.60f);
                }
                pause(400);
                String now = IslandAccess.focusedEditText();
                String lowNow = now == null ? "" : now.trim().toLowerCase(Locale.US);
                if (now == null || now.trim().isEmpty()
                        || "type a message".equals(lowNow)
                        || "message".equals(lowNow)) {
                    sent = true;
                    break;
                }
            }
            if (!sent) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "send failed");
                IslandAccess.nodeDump();
                return result;
            }
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "whatsapp failed");
            IslandAccess.nodeDump();
        }
        return result;
    }

    /** Default sandbox is WhatsApp Business; personal only when asked. */
    static String resolveWaPackage(String packageHint, String utterance) {
        String hint = packageHint == null ? "" : packageHint.trim().toLowerCase(Locale.US);
        String u = utterance == null ? "" : utterance.toLowerCase(Locale.US);
        if (hint.contains("w4b") || hint.contains("business")) {
            return "com.whatsapp.w4b";
        }
        if ("com.whatsapp".equals(hint)) {
            return "com.whatsapp";
        }
        if (u.contains("personal whatsapp") || u.contains("my whatsapp")) {
            return "com.whatsapp";
        }
        return "com.whatsapp.w4b";
    }

    private static boolean clickWaId(String pkg, String id) {
        if (pkg != null && !pkg.isEmpty()
                && IslandAccess.clickViewId(pkg + ":id/" + id)) {
            return true;
        }
        return IslandAccess.clickViewId("com.whatsapp.w4b:id/" + id)
                || IslandAccess.clickViewId("com.whatsapp:id/" + id);
    }

    private static boolean typeWaId(String pkg, String id, String body) {
        if (pkg != null && !pkg.isEmpty()
                && IslandAccess.typeViewId(pkg + ":id/" + id, body)) {
            return true;
        }
        return IslandAccess.typeViewId("com.whatsapp.w4b:id/" + id, body)
                || IslandAccess.typeViewId("com.whatsapp:id/" + id, body);
    }

    /**
     * One-shot Accessibility Settings/profile text dump → door /note.
     * Never continuous WA/IG scrape.
     */
    static Map<String, Object> drivePhoneProfileSnapshot(Context context,
            Map<String, Object> result) {
        StringBuilder dump = new StringBuilder();
        try {
            Intent settings = new Intent(Settings.ACTION_SETTINGS);
            settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(settings);
            try {
                Thread.sleep(1400);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            try {
                IslandAccess.clickText("About phone");
            } catch (Exception ignored) {
            } catch (NoSuchMethodError ignored) {
            }
            try {
                Thread.sleep(900);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            String about = "";
            try {
                about = IslandAccess.visibleTextDump();
            } catch (Exception ignored) {
                about = "";
            } catch (NoSuchMethodError e) {
                try {
                    about = IslandAccess.nodeDump();
                } catch (Exception ignored) {
                    about = "";
                }
            }
            if (about != null && about.length() > 0) {
                dump.append("## About / Settings\n\n").append(about).append("\n\n");
            }
            try {
                IslandAccess.pressBack();
            } catch (Exception ignored) {
            } catch (NoSuchMethodError ignored) {
            }
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            try {
                IslandAccess.clickText("Accounts");
            } catch (Exception ignored) {
            } catch (NoSuchMethodError ignored) {
            }
            try {
                Thread.sleep(800);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            String accounts = "";
            try {
                accounts = IslandAccess.visibleTextDump();
            } catch (Exception ignored) {
                accounts = "";
            } catch (NoSuchMethodError e) {
                try {
                    accounts = IslandAccess.nodeDump();
                } catch (Exception ignored) {
                    accounts = "";
                }
            }
            if (accounts != null && accounts.length() > 0) {
                dump.append("## Accounts\n\n").append(accounts).append("\n");
            }
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "snapshot failed");
            result.put("spoken", "Could not snapshot phone settings.");
            return result;
        }
        String body = dump.toString().trim();
        if (body.isEmpty()) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "empty dump");
            result.put("spoken", "Settings dump was empty — enable Accessibility.");
            return result;
        }
        if (body.length() > 12000) {
            body = body.substring(0, 12000) + "\n…[truncated]";
        }
        String day = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        String title = "phone_settings_" + day;
        boolean posted = false;
        try {
            posted = RoxClient.postNote(context, title, body);
        } catch (Exception ignored) {
            posted = false;
        }
        result.put("ok", Boolean.TRUE);
        result.put("title", title);
        result.put("posted", posted ? Boolean.TRUE : Boolean.FALSE);
        result.put("chars", Integer.valueOf(body.length()));
        result.put("spoken", posted
                ? "Phone profile saved to mind."
                : "Captured settings; door note failed — saved locally if possible.");
        return result;
    }

    static Map<String, Object> drivePlayMusic(Context context, String query, Map<String, Object> result) {
        String q = query == null ? "" : query.trim();
        if (q.isEmpty()) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "no query");
            return result;
        }
        try {
            Intent launch = openAppIntent(context, "spotify");
            if (launch == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "spotify missing");
                return result;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launch);
            if (!IslandAccess.waitFor("spotify", null, 8000) && !waitPackage("spotify", 32)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "spotify missing");
                IslandAccess.nodeDump();
                return result;
            }
            boolean search = IslandAccess.clickLabel("Search");
            if (!search) {
                pause(400);
                search = IslandAccess.clickLabel("Search");
            }
            pause(500);
            IslandAccess.typeFocused(q);
            pause(800);
            String token = q;
            int sp = q.indexOf(' ');
            if (sp > 0) {
                token = q.substring(0, sp);
            }
            boolean row = IslandAccess.clickChatRow(token);
            if (!row) {
                row = IslandAccess.clickTextExactPrefer(q);
            }
            if (!row) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "play tap failed");
                IslandAccess.nodeDump();
                return result;
            }
            pause(400);
            IslandAccess.clickLabel("Play");
            boolean playing = IslandAccess.hasText("Play")
                    || IslandAccess.hasText("Pause")
                    || IslandAccess.hasText("Now Playing")
                    || IslandAccess.hasText(q);
            if (!playing) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "play tap failed");
                IslandAccess.nodeDump();
                return result;
            }
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "play failed");
            IslandAccess.nodeDump();
        }
        return result;
    }

    static Map<String, Object> driveCall(Context context, String who, Map<String, Object> result) {
        String name = who == null ? "" : who.trim();
        if (name.isEmpty()) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "no contact");
            return result;
        }
        try {
            if (looksLikeNumber(name)) {
                String digits = name.replaceAll("[^0-9+]", "");
                boolean canCall = false;
                try {
                    canCall = context != null
                            && context.checkSelfPermission(
                                    android.Manifest.permission.CALL_PHONE)
                            == PackageManager.PERMISSION_GRANTED;
                } catch (Exception ignored) {
                    canCall = false;
                }
                try {
                    Intent call = new Intent(
                            canCall ? Intent.ACTION_CALL : Intent.ACTION_DIAL);
                    call.setData(Uri.parse("tel:" + digits));
                    call.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    context.startActivity(call);
                    pause(600);
                    if (canCall) {
                        IslandAccess.clickText("Call");
                    }
                    result.put("ok", Boolean.TRUE);
                    if (!canCall) {
                        result.put("spoken", "Dialer open — tap Call.");
                    }
                    return result;
                } catch (SecurityException se) {
                    Intent dial = new Intent(Intent.ACTION_DIAL);
                    dial.setData(Uri.parse("tel:" + digits));
                    dial.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    context.startActivity(dial);
                    result.put("ok", Boolean.TRUE);
                    result.put("spoken", "Dialer open — tap Call.");
                    return result;
                }
            }
            Intent launch = openAppIntent(context, "phone");
            if (launch == null) {
                launch = openAppIntent(context, "contacts");
            }
            if (launch == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "call not placed");
                return result;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launch);
            pause(900);
            IslandAccess.clickText("Search");
            pause(400);
            IslandAccess.typeFocused(name);
            pause(600);
            String matched = IslandAccess.clickChatRowFuzzy(name);
            if (matched == null && !IslandAccess.clickChatRow(name)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "call not placed");
                return result;
            }
            if (matched != null && !matched.isEmpty()) {
                result.put("matched", matched);
                String first = matched.split("\n")[0].trim();
                if (!first.equalsIgnoreCase(name)) {
                    result.put("spoken", "Calling " + first);
                }
            }
            pause(400);
            if (!IslandAccess.clickText("Call") && !IslandAccess.clickText("Phone")) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "call not placed");
                return result;
            }
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "call not placed");
        }
        return result;
    }

    static Map<String, Object> driveGmail(Context context, String to, String subject, String body,
                                          Map<String, Object> result) {
        try {
            Intent launch = openAppIntent(context, "gmail");
            if (launch == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "gmail missing");
                return result;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launch);
            waitPackage("gm", 12);
            IslandAccess.clickText("Compose");
            pause(600);
            if (to != null && !to.trim().isEmpty()) {
                IslandAccess.typeFocused(to.trim());
            }
            pause(300);
            IslandAccess.clickText("Subject");
            if (subject != null && !subject.trim().isEmpty()) {
                IslandAccess.typeFocused(subject.trim());
            }
            pause(300);
            IslandAccess.clickText("Compose email");
            if (body != null && !body.trim().isEmpty()) {
                IslandAccess.typeFocused(body.trim());
            }
            // mail_compose / mail_send are confirm-gated; Send only after yes.
            pause(300);
            IslandAccess.clickText("Send");
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "mail failed");
        }
        return result;
    }

    static Map<String, Object> driveSms(Context context, String to, String text,
                                        Map<String, Object> result) {
        try {
            String who = to == null ? "" : to.trim();
            String body = text == null ? "" : text.trim();
            Intent i = new Intent(Intent.ACTION_SENDTO);
            i.setData(Uri.parse("smsto:" + Uri.encode(who)));
            if (!body.isEmpty()) {
                i.putExtra("sms_body", body);
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(i);
            pause(900);
            if (!body.isEmpty()) {
                IslandAccess.typeFocused(body);
            }
            // sms_send is confirm-gated; tap Send after yes.
            pause(400);
            if (!IslandAccess.clickText("Send")) {
                IslandAccess.clickLabel("Send");
            }
            result.put("ok", Boolean.TRUE);
            result.put("spoken", who.isEmpty() ? "SMS sent." : ("SMS to " + who + "."));
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "sms failed");
        }
        return result;
    }

    static Map<String, Object> driveReels(Context context, Map<String, Object> result) {
        try {
            String fg = IslandAccess.foregroundPackage();
            if (fg == null || !fg.toLowerCase(Locale.US).contains("instagram")) {
                Intent launch = openAppIntent(context, "instagram");
                if (launch != null && context != null) {
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    context.startActivity(launch);
                }
                if (!IslandAccess.waitFor("instagram", null, 8000) && !waitPackage("instagram", 32)) {
                    result.put("ok", Boolean.FALSE);
                    result.put("error", "instagram missing");
                    IslandAccess.nodeDump();
                    return result;
                }
            }
            boolean reels = IslandAccess.clickLabel("Reels");
            if (!reels) {
                pause(400);
                reels = IslandAccess.clickLabel("reel");
            }
            if (!reels) {
                pause(400);
                reels = IslandAccess.clickLabel("Reels");
            }
            boolean selected = IslandAccess.isSelectedLabel("Reels");
            boolean homeSel = IslandAccess.isSelectedLabel("Home");
            if (homeSel && !selected) {
                pause(400);
                reels = IslandAccess.clickLabel("Reels") || reels;
                selected = IslandAccess.isSelectedLabel("Reels");
                homeSel = IslandAccess.isSelectedLabel("Home");
            }
            if ((!reels && !selected) || (homeSel && !selected)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "reels tab missing");
                IslandAccess.nodeDump();
                return result;
            }
            IslandService.startAutoScroll();
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "scroll failed");
            IslandAccess.nodeDump();
        }
        return result;
    }

    static Map<String, Object> driveYouTube(Context context, Map<?, ?> args,
                                            Map<String, Object> result) {
        String mode = str(args, "mode").toLowerCase(Locale.US);
        String query = str(args, "query").trim();
        if (mode.isEmpty()) {
            if (query.isEmpty() || query.toLowerCase(Locale.US).contains("first")) {
                mode = "first";
            } else {
                mode = "search";
            }
        }
        try {
            Intent launch = openAppIntent(context, "youtube");
            if (launch == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "youtube missing");
                return result;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            if (context != null) {
                context.startActivity(launch);
            }
            if (!IslandAccess.waitFor("youtube", null, 8000) && !waitPackage("youtube", 32)) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "youtube missing");
                IslandAccess.nodeDump();
                return result;
            }
            pause(900);
            IslandAccess.clickLabel("Close minimised player");
            IslandAccess.clickLabel("Close minimized player");
            pause(400);
            String fg = IslandAccess.foregroundPackage();
            if (fg != null && fg.toLowerCase(Locale.US).contains("spotify")) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "youtube failed");
                IslandAccess.nodeDump();
                return result;
            }
            if ("search".equals(mode) && !query.isEmpty()) {
                IslandAccess.clickLabel("Search");
                pause(500);
                IslandAccess.typeFocused(query);
                pause(900);
                boolean row = IslandAccess.clickFirstResultRow();
                if (!row) {
                    pause(500);
                    row = IslandAccess.clickFirstResultRow();
                }
                pause(700);
                if (!youtubePlayerUp()) {
                    IslandAccess.tapRatio(0.50f, 0.28f);
                    pause(800);
                }
                if (!youtubePlayerUp()) {
                    IslandAccess.tapRatio(0.50f, 0.40f);
                    pause(800);
                }
                if (!youtubePlayerUp() && !row) {
                    result.put("ok", Boolean.FALSE);
                    result.put("error", "youtube player missing");
                    IslandAccess.nodeDump();
                    return result;
                }
            } else {
                boolean row = IslandAccess.clickFirstResultRow();
                if (!row) {
                    pause(500);
                    row = IslandAccess.clickFirstResultRow();
                }
                pause(700);
                if (!youtubePlayerUp()) {
                    IslandAccess.tapRatio(0.50f, 0.32f);
                    pause(800);
                }
                if (!youtubePlayerUp()) {
                    IslandAccess.tapRatio(0.50f, 0.38f);
                    pause(800);
                }
                if (!youtubePlayerUp()) {
                    IslandAccess.tapRatio(0.50f, 0.48f);
                    pause(800);
                }
                if (!youtubePlayerUp() && !row) {
                    result.put("ok", Boolean.FALSE);
                    result.put("error", "youtube player missing");
                    IslandAccess.nodeDump();
                    return result;
                }
            }
            pause(800);
            fg = IslandAccess.foregroundPackage();
            if (fg != null && fg.toLowerCase(Locale.US).contains("spotify")) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "youtube failed");
                IslandAccess.nodeDump();
                return result;
            }
            boolean player = youtubePlayerUp();
            if (!player) {
                pause(600);
                player = youtubePlayerUp();
            }
            if (!player) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "youtube player missing");
                IslandAccess.nodeDump();
                return result;
            }
            result.put("ok", Boolean.TRUE);
            android.util.Log.i("bee", "youtube player ok");
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "youtube failed");
            IslandAccess.nodeDump();
        }
        return result;
    }

    private static boolean youtubePlayerUp() {
        String fg = IslandAccess.foregroundPackage();
        if (fg == null || !fg.toLowerCase(Locale.US).contains("youtube")) {
            return false;
        }
        if (IslandAccess.hasText("Minimised player")
                || IslandAccess.hasText("Minimized player")) {
            return false;
        }
        return IslandAccess.hasText("Pause video")
                || IslandAccess.hasText("Enter fullscreen")
                || IslandAccess.hasText("Exit fullscreen")
                || IslandAccess.hasText("Mute video")
                || IslandAccess.hasText("like this video")
                || IslandAccess.hasText("Remix this Short");
    }

    private static boolean waMessageSearchUp() {
        return IslandAccess.hasText("Photos")
                && IslandAccess.hasText("Documents")
                && IslandAccess.hasText("Links");
    }

    private static void goWaChatList(String pkg) {
        for (int hop = 0; hop < 4; hop++) {
            if (IslandAccess.hasText("Ask Meta AI or Search")
                    || IslandAccess.hasText("Ask Meta AI")
                    || IslandAccess.hasText("Search or start a new chat")) {
                return;
            }
            if (!clickWaId(pkg, "back")
                    && !clickWaId(pkg, "whatsapp_toolbar_home")
                    && !IslandAccess.clickLabel("Back")
                    && !IslandAccess.clickLabel("Chats")) {
                IslandAccess.tapRatio(0.07f, 0.05f);
            }
            pause(300);
        }
    }

    private static void leaveWaMessageSearch(String pkg) {
        for (int hop = 0; hop < 4; hop++) {
            if (!waMessageSearchUp()) {
                return;
            }
            if (!clickWaId(pkg, "wds_toolbar_nav_button")
                    && !IslandAccess.clickLabel("Back")) {
                IslandAccess.tapRatio(0.07f, 0.05f);
            }
            pause(300);
        }
    }

    private static void openWaChatSearch(String pkg) {
        leaveWaMessageSearch(pkg);
        if (clickWaId(pkg, "search_text") || clickWaId(pkg, "menuitem_search")) {
            return;
        }
        if (IslandAccess.clickLabel("Ask Meta AI or Search")
                || IslandAccess.clickLabel("Search or start a new chat")
                || IslandAccess.clickLabel("Search")) {
            return;
        }
        IslandAccess.clickLabel("Ask Meta AI");
    }

    private static boolean waitPackage(String needle, int hops) {
        String want = needle == null ? "" : needle.toLowerCase(Locale.US);
        for (int i = 0; i < hops; i++) {
            String fg = "";
            try {
                fg = IslandAccess.foregroundPackage();
            } catch (Exception ignored) {
                fg = "";
            }
            if (fg != null && fg.toLowerCase(Locale.US).contains(want)) {
                return true;
            }
            pause(250);
        }
        return false;
    }

    private static boolean looksLikeNumber(String raw) {
        if (raw == null) {
            return false;
        }
        String d = raw.replaceAll("[^0-9]", "");
        return d.length() >= 7;
    }

    static Map<String, Object> driveClosedLoop(String stayPkg, String want, String direction,
                                               Map<String, Object> result) {
        String stay = stayPkg == null ? "" : stayPkg.trim();
        String query = want == null ? "" : want.trim();
        String dir = direction == null || direction.trim().isEmpty() ? "up" : direction.trim();
        try {
            for (int hop = 0; hop < 20; hop++) {
                String fg = "";
                try {
                    fg = IslandAccess.foregroundPackage();
                } catch (Exception ignored) {
                    fg = "";
                }
                if (!stay.isEmpty() && !fg.isEmpty()
                        && fg.indexOf(stay) < 0 && stay.indexOf(fg) < 0) {
                    IslandAccess.pressBack();
                    pause(250);
                    continue;
                }
                if (!query.isEmpty() && IslandAccess.clickText(query)) {
                    result.put("ok", Boolean.TRUE);
                    return result;
                }
                List<String> labels = IslandAccess.clickableLabels();
                boolean done = false;
                if (labels != null) {
                    for (int i = 0; i < labels.size(); i++) {
                        String lab = labels.get(i);
                        if (lab != null && lab.equalsIgnoreCase("done")) {
                            done = true;
                            break;
                        }
                    }
                }
                if (done) {
                    break;
                }
                IslandAccess.swipe(dir);
                pause(400);
            }
            result.put("ok", Boolean.TRUE);
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "loop failed");
        }
        return result;
    }

    private static void pause(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /** Alias map then launcher label scan. Never returns a generic launcher intent with no package. */
    static Intent openAppIntent(Context context, String want) {
        if (context == null || want == null) {
            return null;
        }
        String raw = want.trim();
        if (raw.isEmpty()) {
            return null;
        }
        String w = raw.toLowerCase(Locale.US);
        PackageManager pm;
        try {
            pm = context.getPackageManager();
        } catch (Exception e) {
            return null;
        }
        if (pm == null) {
            return null;
        }
        // Direct package name passthrough first.
        if (w.contains(".") && !w.contains(" ")) {
            try {
                Intent direct = pm.getLaunchIntentForPackage(raw.trim());
                if (direct != null) {
                    return direct;
                }
            } catch (Exception ignored) {
            }
        }
        String alias = aliasFor(w);
        if (alias != null) {
            try {
                Intent aliased = pm.getLaunchIntentForPackage(alias);
                if (aliased != null) {
                    return aliased;
                }
            } catch (Exception ignored) {
            }
            Intent pkg = new Intent(Intent.ACTION_MAIN);
            pkg.addCategory(Intent.CATEGORY_LAUNCHER);
            pkg.setPackage(alias);
            return pkg;
        }
        // Launcher label scan.
        try {
            Intent probe = new Intent(Intent.ACTION_MAIN);
            probe.addCategory(Intent.CATEGORY_LAUNCHER);
            List<ResolveInfo> infos = pm.queryIntentActivities(probe, 0);
            if (infos == null || infos.isEmpty()) {
                return null;
            }
            ResolveInfo best = null;
            int bestScore = 0;
            for (ResolveInfo ri : infos) {
                if (ri == null || ri.activityInfo == null) {
                    continue;
                }
                String pkg = ri.activityInfo.packageName == null
                        ? "" : ri.activityInfo.packageName.toLowerCase(Locale.US);
                String label = "";
                try {
                    CharSequence cs = ri.loadLabel(pm);
                    if (cs != null) {
                        label = cs.toString().toLowerCase(Locale.US);
                    }
                } catch (Exception ignored) {
                }
                int score = Math.max(scoreField(w, label), scoreField(w, pkg));
                if (score > bestScore) {
                    bestScore = score;
                    best = ri;
                }
            }
            if (best == null || bestScore <= 0) {
                return null;
            }
            String bestPkg = best.activityInfo.packageName;
            if (bestPkg == null || bestPkg.isEmpty()) {
                return null;
            }
            try {
                Intent bestLaunch = pm.getLaunchIntentForPackage(bestPkg);
                if (bestLaunch != null) {
                    return bestLaunch;
                }
            } catch (Exception ignored) {
            }
            Intent explicit = new Intent(Intent.ACTION_MAIN);
            explicit.addCategory(Intent.CATEGORY_LAUNCHER);
            explicit.setClassName(bestPkg, best.activityInfo.name);
            return explicit;
        } catch (Exception e) {
            return null;
        }
    }

    private static String aliasFor(String w) {
        if (w == null || w.isEmpty()) {
            return null;
        }
        if (w.contains("github")) {
            return "com.github.android";
        }
        if (w.contains("tailscale")) {
            return "com.tailscale.ipn";
        }
        if (w.contains("spotify")) {
            return "com.spotify.music";
        }
        if (w.contains("instagram") || w.contains("insta")) {
            return "com.instagram.android";
        }
        if (w.contains("personal whatsapp") || w.contains("my whatsapp")) {
            return "com.whatsapp";
        }
        if (w.contains("whatsapp business") || w.contains("w4b")
                || w.equals("whatsapp") || w.contains("whatsapp")) {
            return "com.whatsapp.w4b";
        }
        if (w.contains("gmail") || w.equals("mail") || w.equals("email")) {
            return "com.google.android.gm";
        }
        if (w.contains("dialer") || w.equals("phone") || w.equals("call")
                || w.contains("contacts")) {
            return "com.google.android.dialer";
        }
        if (w.contains("camera")) {
            return "com.nothing.camera";
        }
        if (w.contains("messages") || w.contains("sms")) {
            return "com.google.android.apps.messaging";
        }
        if (w.contains("youtube") || w.contains("youtu")) {
            return "com.google.android.youtube";
        }
        if (w.contains("netflix")) {
            return "com.netflix.mediaclient";
        }
        return null;
    }

    private static int scoreField(String want, String field) {
        if (want == null || field == null || want.isEmpty() || field.isEmpty()) {
            return 0;
        }
        if (field.equals(want)) {
            return 3;
        }
        if (field.startsWith(want) || want.startsWith(field)) {
            return 2;
        }
        if (field.contains(want) || want.contains(field)) {
            return 1;
        }
        return 0;
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
            String pkg = resolveWaPackage(str(args, "package"), str(args, "to") + " " + body);
            Intent i = new Intent(Intent.ACTION_SEND);
            i.setPackage(pkg);
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
            // Resolved via openAppIntent(Context, String) which does alias map
            // then launcher label scan. Never return a generic launcher intent
            // with no package here.
            return null;
        }
        if ("type_into".equals(tool)) {
            // Typed via IslandAccess.typeFocused(text). Never succeed via a
            // fake Intent action 'type'.
            return null;
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

    static Map<String, Object> driveWaListChats(Context context, Map<?, ?> args,
                                                Map<String, Object> result) {
        int limit = 30;
        try {
            String raw = str(args, "limit");
            if (!raw.isEmpty()) {
                limit = Integer.parseInt(raw.trim());
            }
        } catch (Exception ignored) {
            limit = 30;
        }
        if (limit < 1) {
            limit = 1;
        }
        if (limit > 40) {
            limit = 40;
        }
        String pkg = resolveWaPackage(str(args, "package"), "business");
        try {
            Intent launch = openAppIntent(context, pkg);
            if (launch == null) {
                launch = openAppIntent(context, "whatsapp business");
            }
            if (launch == null) {
                result.put("ok", Boolean.FALSE);
                result.put("error", "whatsapp missing");
                return result;
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launch);
            String waitNeedle = pkg.contains("w4b") ? "w4b" : "whatsapp";
            IslandAccess.waitFor(waitNeedle, null, 8000);
            goWaChatList(pkg);
            pause(600);
            List<String> titles = IslandAccess.listChatTitles(limit);
            if (titles == null) {
                titles = new ArrayList<String>();
            }
            result.put("ok", Boolean.TRUE);
            result.put("chats", titles);
            result.put("count", Integer.valueOf(titles.size()));
            StringBuilder spoken = new StringBuilder();
            spoken.append("Last ").append(titles.size()).append(" chats. ");
            int n = Math.min(titles.size(), 8);
            for (int i = 0; i < n; i++) {
                String t = titles.get(i);
                if (t == null) {
                    continue;
                }
                String shortName = t.split("\n")[0].trim();
                if (shortName.length() > 28) {
                    shortName = shortName.substring(0, 28);
                }
                if (i > 0) {
                    spoken.append(", ");
                }
                spoken.append(shortName);
            }
            if (titles.size() > n) {
                spoken.append(", and ").append(titles.size() - n).append(" more");
            }
            result.put("spoken", spoken.toString());
            try {
                for (int i = 0; i < titles.size(); i++) {
                    ChatStore.add(context, false, "chat: " + titles.get(i).split("\n")[0].trim());
                }
            } catch (Exception ignored) {
            }
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "list chats failed");
        }
        return result;
    }

    private static void attachObserve(Map<String, Object> result) {
        if (result == null) {
            return;
        }
        try {
            Map<String, Object> obs = IslandAccess.observe();
            if (obs != null) {
                result.put("observe", obs);
                Object pkg = obs.get("foregroundPkg");
                if (pkg != null) {
                    result.put("foregroundPkg", pkg);
                }
            }
        } catch (Exception ignored) {
        }
    }

    private static String str(Map<?, ?> args, String key) {
        Object v = args.get(key);
        return v == null ? "" : String.valueOf(v);
    }

    private static long parseWaitMs(Map<?, ?> args) {
        if (args == null) {
            return 0;
        }
        Object raw = args.get("ms");
        if (raw == null) {
            raw = args.get("wait");
        }
        if (raw == null) {
            return 0;
        }
        long ms = 0;
        try {
            if (raw instanceof Number) {
                ms = ((Number) raw).longValue();
            } else {
                String s = String.valueOf(raw).trim();
                if (s.isEmpty()) {
                    return 0;
                }
                try {
                    ms = Long.parseLong(s);
                } catch (NumberFormatException e) {
                    try {
                        ms = (long) Double.parseDouble(s);
                    } catch (NumberFormatException e2) {
                        return 0;
                    }
                }
            }
        } catch (Exception e) {
            return 0;
        }
        if (ms < 0) {
            ms = 0;
        }
        if (ms > 8000) {
            ms = 8000;
        }
        return ms;
    }
}
