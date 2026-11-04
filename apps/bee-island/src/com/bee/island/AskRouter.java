package com.bee.island;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Same ask() DAG for island tap, Chat composer, and ACTION_ASK.
 * Everyday open/play/type/search run immediately. Confirm-gated
 * send tools (PRD CONFIRM_TOOLS) stage a PendingPlan. Leftovers
 * go to Rox POST /utterance with session_id=phone.
 */
final class AskRouter {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static volatile String lastSpoken = "";
    private static volatile String lastAsk = "";
    private static volatile boolean recovering;
    private static TextToSpeech tts;
    private static boolean ttsReady;

    private AskRouter() {
    }

    static String lastSpoken() {
        return lastSpoken == null ? "" : lastSpoken;
    }

    static void handle(final Context context, final String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return;
        }
        final String text = raw.trim();
        lastAsk = text;
        ChatStore.add(context, true, text);
        String kind = BeeAsk.classifyVoice(text);
        if ("refuse".equals(kind)) {
            speak(context, "No.");
            return;
        }
        if ("cancel".equals(kind)) {
            PendingPlan.clear();
            IslandService.stopAutoScroll();
            speak(context, "Cancelled.");
            return;
        }
        if ("confirm".equals(kind)) {
            if (PendingPlan.hasPending()) {
                final List<Map<String, Object>> pending = PendingPlan.get();
                PendingPlan.clear();
                new Thread(new Runnable() {
                    @Override
                    public void run() {
                        finish(context, pending);
                    }
                }, "bee-run").start();
            } else {
                speak(context, BeeAsk.clampLine("Nothing to confirm."));
            }
            return;
        }
        if (BeeMind.isMind(text)) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    boolean handled = false;
                    try {
                        handled = BeeMind.handle(context, text);
                    } catch (Exception ignored) {
                        handled = false;
                    }
                    if (!handled) {
                        // Door empty → Muse leftover (RAG / utterance), never Unknown.
                        leftover(context, text, new ArrayList<Map<String, Object>>());
                    }
                }
            }, "bee-mind").start();
            return;
        }
        if (BeeAsk.isGreeting(text)) {
            speak(context, "Hi.");
            return;
        }
        new Thread(new Runnable() {
            @Override
            public void run() {
                runAsk(context, text);
            }
        }, "bee-ask").start();
    }

    static void runAsk(Context context, String text) {
        lastAsk = text == null ? "" : text;
        Map<String, Object> plan = BeeAsk.planAsk(text);
        String kind = String.valueOf(plan.get("kind"));
        List<Map<String, Object>> steps = castSteps(plan.get("steps"));
        if ("refuse".equals(kind)) {
            speak(context, "No.");
            return;
        }
        boolean namedRemote = namedRemote(text, steps);
        // Agentic default: hands / compound / script / chats → Muse first.
        if (needsMusePlan(text, kind, steps) || namedRemote) {
            leftover(context, text, steps);
            return;
        }
        if ("local_fast".equals(kind) && isTrivialLocal(steps)) {
            actOrConfirm(context, steps);
            return;
        }
        leftover(context, text, steps);
    }

    /** True when Muse must tokenize/plan (not local regex alone). */
    private static boolean needsMusePlan(String text, String kind, List<Map<String, Object>> steps) {
        if ("dag".equals(kind) || "spark".equals(kind) || "wonder".equals(kind)) {
            return true;
        }
        String low = text == null ? "" : text.toLowerCase(Locale.US);
        if (low.matches("(?s).*\\b(?:script|draft|write)\\b.*\\b(?:message|msg|text)\\b.*")) {
            return true;
        }
        if (low.contains("last") && (low.contains("chat") || low.contains("chats"))) {
            return true;
        }
        if (low.contains("b chat") || low.contains("business whatsapp")
                || low.contains("show chats") || low.contains("list chats")) {
            return true;
        }
        if (needsMuseForVagueHands(steps)) {
            return true;
        }
        return hasHandsTool(steps);
    }

    private static boolean hasHandsTool(List<Map<String, Object>> steps) {
        if (steps == null) {
            return false;
        }
        for (int i = 0; i < steps.size(); i++) {
            Map<String, Object> step = steps.get(i);
            if (step == null) {
                continue;
            }
            String tool = step.get("tool") == null ? "" : String.valueOf(step.get("tool"));
            if ("whatsapp_send".equals(tool) || "dial".equals(tool)
                    || "wa_list_chats".equals(tool) || "mail_compose".equals(tool)
                    || "mail_send".equals(tool) || "instagram_send".equals(tool)
                    || "sms_send".equals(tool) || "chat_touch".equals(tool)
                    || "suggest_reply".equals(tool)) {
                return true; // sms/mail included for Muse-first hands path
            }
        }
        return false;
    }

    /** Only open_app (no args compound) stays truly local_fast. */
    private static boolean isTrivialLocal(List<Map<String, Object>> steps) {
        if (steps == null || steps.size() != 1) {
            return false;
        }
        Map<String, Object> step = steps.get(0);
        if (step == null) {
            return false;
        }
        String tool = step.get("tool") == null ? "" : String.valueOf(step.get("tool"));
        return "open_app".equals(tool) || "press_back".equals(tool)
                || "wait_ms".equals(tool) || "notifications_list".equals(tool);
    }

    private static boolean needsMuseForVagueHands(List<Map<String, Object>> steps) {
        if (steps == null || steps.isEmpty()) {
            return false;
        }
        for (int i = 0; i < steps.size(); i++) {
            Map<String, Object> step = steps.get(i);
            if (step == null) {
                continue;
            }
            String tool = step.get("tool") == null ? "" : String.valueOf(step.get("tool"));
            Map<?, ?> args = step.get("args") instanceof Map ? (Map<?, ?>) step.get("args") : null;
            String to = arg(args, "to");
            if (to.isEmpty()) {
                to = arg(args, "contact");
            }
            if (("whatsapp_send".equals(tool) || "dial".equals(tool))
                    && BeeAsk.isVagueContact(to)) {
                return true;
            }
        }
        return false;
    }

    static void leftover(Context context, String text, List<Map<String, Object>> localSteps) {
        boolean namedRemote = namedRemote(text, localSteps);
        String spoken = "";
        List<Map<String, Object>> phoneOnly = deviceSteps(localSteps, false);
        List<Map<String, Object>> remoteOnly = deviceSteps(localSteps, true);
        boolean hasKey = KeyVault.hasKey(context);

        // Muse-first when Setup key exists — Rox is enrichment, not a gate.
        List<Map<String, Object>> tools = new ArrayList<Map<String, Object>>();
        if (hasKey) {
            try {
                IslandService svc = IslandService.current();
                if (svc != null) {
                    svc.setIslandLine(BeeAsk.lineFor("plan"));
                }
            } catch (Exception ignored) {
            }
            tools = sparkPhone(context, text);
            tools = deviceSteps(tools, false);
        }

        if (RoxClient.reachable(context)) {
            Map<String, Object> reply = RoxClient.postUtterance(context, text);
            if (Boolean.TRUE.equals(reply.get("ok"))) {
                List<Map<String, Object>> phoneSteps = castSteps(reply.get("phone_steps"));
                spoken = reply.get("spoken") == null ? "" : String.valueOf(reply.get("spoken")).trim();
                if (spoken.isEmpty() && reply.get("reply") != null) {
                    spoken = String.valueOf(reply.get("reply")).trim();
                }
                phoneSteps = stripBrainTools(phoneSteps);
                // Prefer richer door plan when Muse returned nothing.
                if (tools.isEmpty() && !phoneSteps.isEmpty()) {
                    actOrConfirm(context, phoneSteps, spoken);
                    return;
                }
                if (tools.isEmpty() && !spoken.isEmpty() && phoneSteps.isEmpty()) {
                    speak(context, spoken);
                    return;
                }
                if (!phoneSteps.isEmpty() && phoneSteps.size() > tools.size()) {
                    tools = phoneSteps;
                }
            }
        }

        // Laptop-named steps: never abandon when Muse key can replan for phone.
        if ((namedRemote || !remoteOnly.isEmpty()) && tools.isEmpty() && phoneOnly.isEmpty()) {
            if (hasKey) {
                tools = sparkPhone(context, text);
                tools = deviceSteps(tools, false);
            }
            if (tools.isEmpty() && !hasKey) {
                speak(context, BeeAsk.clampSpeak("Door's down; add a Muse key in Setup."));
                return;
            }
            if (tools.isEmpty()) {
                speak(context, BeeAsk.clampSpeak("Door's down; handling it here."));
            }
        }

        if (!hasKey && tools.isEmpty() && phoneOnly.isEmpty() && !RoxClient.reachable(context)) {
            speak(context, "Add a Muse key in Setup.");
            return;
        }

        if (tools.isEmpty()) {
            tools = phoneOnly;
        }
        if (tools.isEmpty()) {
            tools = BeeAsk.splitUtterance(text);
            tools = deviceSteps(tools, false);
        }
        if (tools.isEmpty()) {
            if (!spoken.isEmpty() && !BeeMind.isEmptyBrainText(spoken)) {
                speak(context, spoken);
                return;
            }
            if (BeeMind.isMind(text)) {
                try {
                    BeeMind.ensureSeeded(context);
                    String low = text.toLowerCase(Locale.US);
                    boolean doing = low.contains("what was i doing")
                            || low.contains("what am i doing")
                            || low.contains("what will you do")
                            || low.contains("what are you doing")
                            || low.matches("(?s).*\\bwhat\\b.*\\bdoing\\b.*");
                    String local = doing
                            ? BeeMind.speakable(BeeMind.whatWasIDoing(context))
                            : BeeMind.speakable(BeeMind.whoAmI(context));
                    if (local != null && !local.isEmpty() && !BeeMind.isEmptyBrainText(local)) {
                        speak(context, local);
                        return;
                    }
                } catch (Exception ignored) {
                }
                speak(context, BeeAsk.clampSpeak(
                        "Mind's thin here — run ingest on the laptop."));
                return;
            }
            speak(context, BeeAsk.clampSpeak("Missed that — say it once more."));
            return;
        }
        String line = spoken;
        if (line.isEmpty()) {
            line = lastSpokenPlan(context, text);
        }
        actOrConfirm(context, tools, line);
    }

    static void actOrConfirm(Context context, List<Map<String, Object>> steps) {
        actOrConfirm(context, steps, "");
    }

    static void actOrConfirm(Context context, List<Map<String, Object>> steps, String spoken) {
        if (steps == null || steps.isEmpty()) {
            speak(context, BeeAsk.clampSpeak("Missed that — say it once more."));
            return;
        }
        if (BeeAsk.needsConfirm(steps)) {
            String island = BeeAsk.thisOrThat(steps);
            String prompt = BeeAsk.confirmSpeak(steps);
            PendingPlan.set(steps, prompt);
            try {
                IslandService s = IslandService.current();
                if (s != null) {
                    s.showConfirmPulse(island.isEmpty() ? prompt : island);
                    // Hear yes/cancel after the confirm TTS.
                    s.listenAfterConfirm(prompt);
                }
            } catch (Exception ignored) {
            }
            speak(context, prompt);
            return;
        }
        finish(context, steps, spoken);
    }

    static void finish(Context context, List<Map<String, Object>> steps) {
        finish(context, steps, "");
    }

    static void finish(Context context, List<Map<String, Object>> steps, String spoken) {
        String before = spoken == null ? "" : spoken.trim();
        if (before.isEmpty()) {
            before = spokenFor(steps);
        }
        // Notification tools speak only after reading the tray.
        if (!before.isEmpty() && !isQuietTool(steps)) {
            speak(context, before);
        }
        final boolean laptopOk = RoxClient.reachable(context);
        List<Map<String, Object>> results = BeeAsk.dispatch(steps,
                new BeeAsk.StepRunner() {
                    @Override
                    public Map<String, Object> run(Map<String, Object> step) {
                        return PhoneActions.run(context, step);
                    }
                },
                new BeeAsk.StepRunner() {
                    @Override
                    public Map<String, Object> run(Map<String, Object> step) {
                        return RoxClient.postUtterance(context, step);
                    }
                },
                laptopOk);
        boolean anyOffline = false;
        boolean anyOk = false;
        boolean clickFail = false;
        String resultSpoken = "";
        Map<String, Object> touchDraft = null;
        for (Map<String, Object> r : results) {
            if (r == null) {
                continue;
            }
            if (Boolean.TRUE.equals(r.get("ok"))) {
                anyOk = true;
            }
            Object spokenObj = r.get("spoken");
            if (spokenObj != null) {
                String s = String.valueOf(spokenObj).trim();
                if (!s.isEmpty()) {
                    resultSpoken = s;
                }
            }
            if (r.get("draft") != null && r.get("to") != null) {
                touchDraft = r;
            }
            Object err = r.get("error");
            String errText = err == null ? "" : String.valueOf(err).toLowerCase(Locale.US);
            if (errText.contains("laptop offline")) {
                anyOffline = true;
            }
            if (errText.contains("click")) {
                clickFail = true;
            }
        }
        if (touchDraft != null && isChatTouch(steps)) {
            String draft = String.valueOf(touchDraft.get("draft")).trim();
            String to = String.valueOf(touchDraft.get("to")).trim();
            String channel = touchDraft.get("channel") == null
                    ? "" : String.valueOf(touchDraft.get("channel")).trim().toLowerCase(Locale.US);
            if (channel.isEmpty() && steps.get(0) != null
                    && steps.get(0).get("args") instanceof Map) {
                Object ch = ((Map<?, ?>) steps.get(0).get("args")).get("channel");
                channel = ch == null ? "" : String.valueOf(ch).trim().toLowerCase(Locale.US);
            }
            String pkg = touchDraft.get("package") == null
                    ? "com.whatsapp.w4b" : String.valueOf(touchDraft.get("package"));
            if (!draft.isEmpty() && !to.isEmpty()) {
                List<Map<String, Object>> send = new ArrayList<Map<String, Object>>();
                Map<String, Object> step = new HashMap<String, Object>();
                String sendTool = "whatsapp_send";
                if ("sms".equals(channel)) {
                    sendTool = "sms_send";
                } else if ("mail".equals(channel) || "email".equals(channel)
                        || "gmail".equals(channel)) {
                    sendTool = "mail_compose";
                }
                step.put("tool", sendTool);
                Map<String, Object> args = new HashMap<String, Object>();
                args.put("to", to);
                String body = draft;
                String lowDraft = draft.toLowerCase(Locale.US);
                int idx = lowDraft.indexOf("suggested reply:");
                if (idx >= 0) {
                    body = draft.substring(idx + "suggested reply:".length()).trim();
                }
                args.put("text", body);
                if ("mail_compose".equals(sendTool)) {
                    args.put("body", body);
                    args.put("subject", "");
                }
                if ("whatsapp_send".equals(sendTool)) {
                    args.put("package", pkg);
                }
                step.put("args", args);
                step.put("device", "phone");
                send.add(step);
                String prompt = BeeAsk.confirmSpeak(send);
                PendingPlan.set(send, prompt);
                String line = resultSpoken;
                if (line.isEmpty()) {
                    line = "Suggested: " + body;
                }
                line = line + " Say yes to send.";
                try {
                    IslandService s = IslandService.current();
                    if (s != null) {
                        s.showConfirmPulse(BeeAsk.thisOrThat(send));
                        s.listenAfterConfirm(line);
                    }
                } catch (Exception ignored) {
                }
                speak(context, BeeAsk.clampSpeak(line));
                return;
            }
        }
        // Closed-loop: one Muse replan when a hands step failed.
        if (!anyOk && !recovering) {
            recovering = true;
            try {
                StringBuilder failCtx = new StringBuilder();
                failCtx.append("Previous plan failed. Repair with phone tools only.\n");
                failCtx.append("Original: ").append(lastAsk == null ? "" : lastAsk).append("\n");
                for (Map<String, Object> r : results) {
                    if (r == null || Boolean.TRUE.equals(r.get("ok"))) {
                        continue;
                    }
                    failCtx.append("error=").append(r.get("error"));
                    if (r.get("observe") != null) {
                        failCtx.append(" observe=").append(String.valueOf(r.get("observe")));
                    }
                    failCtx.append("\n");
                }
                try {
                    String termux = TermuxBridge.diagnose(context, failCtx.toString());
                    if (termux != null && !termux.isEmpty()) {
                        failCtx.append(termux).append("\n");
                    }
                } catch (Exception ignored) {
                }
                List<Map<String, Object>> retry = sparkPhone(context, failCtx.toString());
                if (retry != null && !retry.isEmpty()) {
                    finish(context, retry, spoken);
                    return;
                }
            } finally {
                recovering = false;
            }
        } else if (clickFail && !recovering) {
            recovering = true;
            try {
                List<Map<String, Object>> retry = sparkPhone(context, lastAsk);
                if (retry != null && !retry.isEmpty()) {
                    finish(context, retry, spoken);
                    return;
                }
            } finally {
                recovering = false;
            }
        }
        boolean unknownFail = false;
        String specificErr = "";
        for (Map<String, Object> r : results) {
            if (r == null || Boolean.TRUE.equals(r.get("ok"))) {
                continue;
            }
            Object err = r.get("error");
            String errText = err == null ? "" : String.valueOf(err);
            String lowErr = errText.toLowerCase(Locale.US);
            if (lowErr.contains("unknown")) {
                unknownFail = true;
            }
            if (specificErr.isEmpty() && !errText.isEmpty()
                    && !lowErr.equals("unknown")
                    && !lowErr.contains("laptop offline")) {
                specificErr = errText;
            }
        }
        if (!anyOk && unknownFail && !recovering && lastAsk != null && !lastAsk.isEmpty()) {
            recovering = true;
            try {
                leftover(context, lastAsk, new ArrayList<Map<String, Object>>());
                return;
            } finally {
                recovering = false;
            }
        }
        String line = resultSpoken;
        if (line.isEmpty()) {
            line = doneLine(steps, anyOk);
        }
        if (line.isEmpty()) {
            line = spoken == null ? "" : spoken.trim();
        }
        if (line.isEmpty()) {
            if (anyOk) {
                line = "Done.";
            } else if (!specificErr.isEmpty()) {
                line = specificErr;
            } else {
                line = "Failed.";
            }
        }
        if (anyOffline) {
            line = line.isEmpty() ? "laptop offline" : line + " \u00b7 laptop offline";
        }
        try {
            if (anyOk && !anyOffline) {
                BeeMind.recordOk(context, line);
                IslandService svc = IslandService.current();
                if (svc != null) {
                    svc.showActing();
                }
            } else {
                BeeMind.recordFail(context, line);
            }
        } catch (Exception ignored) {
        }
        speak(context, line);
    }

    private static List<Map<String, Object>> stripBrainTools(List<Map<String, Object>> steps) {
        List<Map<String, Object>> out = new ArrayList<Map<String, Object>>();
        if (steps == null) {
            return out;
        }
        for (int i = 0; i < steps.size(); i++) {
            Map<String, Object> step = steps.get(i);
            if (step == null) {
                continue;
            }
            String tool = step.get("tool") == null ? "" : String.valueOf(step.get("tool"));
            if (BeeAsk.isBrainTool(tool)) {
                continue;
            }
            out.add(step);
        }
        return out;
    }

    static String spokenFor(List<Map<String, Object>> steps) {
        if (steps == null || steps.isEmpty()) {
            return "";
        }
        Map<String, Object> first = steps.get(0);
        if (first == null) {
            return "";
        }
        String tool = first.get("tool") == null ? "" : String.valueOf(first.get("tool"));
        Map<?, ?> args = first.get("args") instanceof Map ? (Map<?, ?>) first.get("args") : null;
        String to = arg(args, "to");
        if (to.isEmpty()) {
            to = arg(args, "contact");
        }
        if ("whatsapp_send".equals(tool)) {
            return to.isEmpty() ? "Texting them." : ("Texting " + to + ".");
        }
        if ("wa_list_chats".equals(tool)) {
            return "Listing chats.";
        }
        if ("dial".equals(tool)) {
            return to.isEmpty() ? "Calling." : ("Calling " + to + ".");
        }
        if ("mail_send".equals(tool) || "mail_compose".equals(tool)) {
            return to.isEmpty() ? "Emailing." : ("Emailing " + to + ".");
        }
        if ("play_music".equals(tool)) {
            String q = arg(args, "query");
            return q.isEmpty() ? "Playing it." : ("Playing " + q + ".");
        }
        if ("youtube_play".equals(tool) || "youtube_search".equals(tool)) {
            return "Opening YouTube.";
        }
        if ("auto_scroll".equals(tool)) {
            return "Scrolling Reels.";
        }
        if ("open_app".equals(tool)) {
            String app = arg(args, "app");
            if (app.isEmpty()) {
                app = arg(args, "label");
            }
            return app.isEmpty() ? "Opening it." : ("Opening " + app + ".");
        }
        if ("notifications_list".equals(tool) || "suggest_reply".equals(tool)) {
            return "";
        }
        if ("phone_profile_snapshot".equals(tool)) {
            return "Capturing phone settings once.";
        }
        return "";
    }

    private static boolean isQuietTool(List<Map<String, Object>> steps) {
        if (steps == null || steps.isEmpty() || steps.get(0) == null) {
            return false;
        }
        String tool = steps.get(0).get("tool") == null
                ? "" : String.valueOf(steps.get(0).get("tool"));
        return "notifications_list".equals(tool)
                || "suggest_reply".equals(tool)
                || "chat_touch".equals(tool)
                || "wa_list_chats".equals(tool);
    }

    private static boolean isChatTouch(List<Map<String, Object>> steps) {
        if (steps == null || steps.isEmpty() || steps.get(0) == null) {
            return false;
        }
        String tool = steps.get(0).get("tool") == null
                ? "" : String.valueOf(steps.get(0).get("tool"));
        return "chat_touch".equals(tool);
    }

    static String doneLine(List<Map<String, Object>> steps, boolean ok) {
        if (!ok) {
            return "That didn't land. Trying another way.";
        }
        if (steps == null || steps.isEmpty()) {
            return "Done.";
        }
        Map<String, Object> first = steps.get(0);
        String tool = first == null || first.get("tool") == null
                ? "" : String.valueOf(first.get("tool"));
        Map<?, ?> args = first != null && first.get("args") instanceof Map
                ? (Map<?, ?>) first.get("args") : null;
        String to = arg(args, "to");
        if (to.isEmpty()) {
            to = arg(args, "contact");
        }
        if ("whatsapp_send".equals(tool)) {
            return to.isEmpty() ? "Sent." : ("Sent to " + to + ".");
        }
        if ("dial".equals(tool)) {
            return to.isEmpty() ? "Calling." : ("Calling " + to + ".");
        }
        if ("play_music".equals(tool)) {
            String q = arg(args, "query");
            return q.isEmpty() ? "Playing it." : ("Playing " + q + ".");
        }
        if ("youtube_play".equals(tool) || "youtube_search".equals(tool)) {
            return "Playing.";
        }
        if ("auto_scroll".equals(tool)) {
            return "Scrolling Reels.";
        }
        if ("mail_send".equals(tool) || "mail_compose".equals(tool)) {
            return to.isEmpty() ? "Emailed." : ("Emailed " + to + ".");
        }
        if ("notifications_list".equals(tool) || "suggest_reply".equals(tool)) {
            return "";
        }
        return "Done.";
    }

    private static String arg(Map<?, ?> args, String key) {
        if (args == null || key == null) {
            return "";
        }
        Object v = args.get(key);
        return v == null ? "" : String.valueOf(v).trim();
    }

    static void speak(final Context context, final String line) {
        final String clamped = BeeAsk.clampSpeak(line);
        lastSpoken = clamped;
        MAIN.post(new Runnable() {
            @Override
            public void run() {
                ChatStore.add(context, false, clamped);
                try {
                    context.getSharedPreferences("bee_island", Context.MODE_PRIVATE)
                            .edit()
                            .putString("last_spoken", clamped)
                            .apply();
                } catch (Exception ignored) {
                }
                try {
                    IslandService svc = IslandService.current();
                    if (svc != null) {
                        // In-pill mission line (40 chars); full text still TTS.
                        svc.setIslandLine(BeeAsk.clampLine(clamped));
                    }
                } catch (Exception ignored) {
                }
                speakTts(context, clamped);
            }
        });
    }

    static void stopTts() {
        try {
            if (tts != null) {
                tts.stop();
            }
        } catch (Exception ignored) {
        }
    }

    private static void speakTts(Context context, final String line) {
        if (context == null || line == null || line.isEmpty()) {
            return;
        }
        final boolean armConfirmMic = PendingPlan.hasPending();
        final String utterId = armConfirmMic ? "bee_confirm" : "bee";
        if (tts == null) {
            ttsReady = false;
            tts = new TextToSpeech(context.getApplicationContext(), new TextToSpeech.OnInitListener() {
                @Override
                public void onInit(int status) {
                    ttsReady = status == TextToSpeech.SUCCESS;
                    if (ttsReady && tts != null) {
                        try {
                            tts.setLanguage(Locale.US);
                            attachTtsListener();
                            tts.speak(line, TextToSpeech.QUEUE_FLUSH, null, utterId);
                        } catch (Exception ignored) {
                        }
                    }
                    // Never arm mic when TTS failed to init — fallback timer handles it.
                }
            });
            return;
        }
        if (ttsReady) {
            try {
                attachTtsListener();
                tts.speak(line, TextToSpeech.QUEUE_FLUSH, null, utterId);
            } catch (Exception ignored) {
            }
        }
        // If TTS not ready yet, IslandService.listenAfterConfirm fallback timer opens mic.
    }

    private static void attachTtsListener() {
        if (tts == null) {
            return;
        }
        try {
            tts.setOnUtteranceProgressListener(new android.speech.tts.UtteranceProgressListener() {
                @Override
                public void onStart(String utteranceId) {
                }

                @Override
                public void onDone(String utteranceId) {
                    if ("bee_confirm".equals(utteranceId)) {
                        notifyConfirmListenReady();
                    }
                }

                @Override
                public void onError(String utteranceId) {
                    if ("bee_confirm".equals(utteranceId)) {
                        notifyConfirmListenReady();
                    }
                }
            });
        } catch (Exception ignored) {
        }
    }

    private static void notifyConfirmListenReady() {
        MAIN.post(new Runnable() {
            @Override
            public void run() {
                try {
                    IslandService svc = IslandService.current();
                    if (svc != null) {
                        svc.listenAfterConfirmReady();
                    }
                } catch (Exception ignored) {
                }
            }
        });
    }

    private static List<Map<String, Object>> sparkPhone(Context context, String text) {
        List<Map<String, Object>> tools = new ArrayList<Map<String, Object>>();
        String key = KeyVault.loadKey(context);
        if (key == null || key.isEmpty()) {
            return tools;
        }
        try {
            String mind = BeeMind.injectContext(context);
            String model = KeyVault.spark(context);
            if (mind != null && mind.length() > 800) {
                model = KeyVault.wonder(context);
            }
            String raw = MuseClient.completeRaw(key, model, text, mind);
            if (raw == null || raw.trim().isEmpty()) {
                lastSpoken = BeeAsk.clampSpeak("Couldn't reach Muse.");
                return tools;
            }
            tools = MuseClient.parseFunctionCalls(raw);
            String spoken = MuseClient.extractOutputText(raw);
            if (spoken != null && !spoken.trim().isEmpty()) {
                lastSpoken = BeeAsk.clampSpeak(spoken);
            }
            if (tools.isEmpty()) {
                tools = BeeAsk.splitUtterance(text);
            }
        } catch (Exception e) {
            lastSpoken = BeeAsk.clampSpeak("Couldn't reach Muse.");
        }
        return tools;
    }

    private static String lastSpokenPlan(Context context, String text) {
        String s = lastSpoken;
        return s == null ? "" : s;
    }

    private static boolean namedRemote(String text, List<Map<String, Object>> steps) {
        String low = text == null ? "" : text.toLowerCase(Locale.US);
        if (low.contains("on my laptop") || low.contains("on the server")
                || low.contains("on my server") || low.contains("on the laptop")) {
            return true;
        }
        return !deviceSteps(steps, true).isEmpty();
    }

    private static List<Map<String, Object>> deviceSteps(List<Map<String, Object>> steps, boolean remote) {
        List<Map<String, Object>> out = new ArrayList<Map<String, Object>>();
        if (steps == null) {
            return out;
        }
        for (Map<String, Object> step : steps) {
            if (step == null || step.get("tool") == null) {
                continue;
            }
            Object deviceObj = step.get("device");
            String device = deviceObj == null ? "phone" : String.valueOf(deviceObj).toLowerCase(Locale.US);
            boolean isRemote = "laptop".equals(device) || "server".equals(device);
            if (isRemote == remote) {
                out.add(step);
            }
        }
        return out;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> castSteps(Object raw) {
        List<Map<String, Object>> out = new ArrayList<Map<String, Object>>();
        if (!(raw instanceof List)) {
            return out;
        }
        for (Object o : (List<?>) raw) {
            if (o instanceof Map) {
                out.add((Map<String, Object>) o);
            }
        }
        return out;
    }
}
