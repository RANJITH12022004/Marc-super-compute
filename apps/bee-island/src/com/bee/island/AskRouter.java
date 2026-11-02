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
        if ("local_fast".equals(kind) || "dag".equals(kind)) {
            if (namedRemote) {
                leftover(context, text, steps);
                return;
            }
            if (needsMuseForVagueHands(steps)) {
                leftover(context, text, steps);
                return;
            }
            actOrConfirm(context, steps);
            return;
        }
        leftover(context, text, steps);
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
        if (RoxClient.reachable(context)) {
            Map<String, Object> reply = RoxClient.postUtterance(context, text);
            if (Boolean.TRUE.equals(reply.get("ok"))) {
                List<Map<String, Object>> phoneSteps = castSteps(reply.get("phone_steps"));
                spoken = reply.get("spoken") == null ? "" : String.valueOf(reply.get("spoken")).trim();
                if (spoken.isEmpty() && reply.get("reply") != null) {
                    spoken = String.valueOf(reply.get("reply")).trim();
                }
                phoneSteps = stripBrainTools(phoneSteps);
                if (!phoneSteps.isEmpty()) {
                    actOrConfirm(context, phoneSteps, spoken);
                    return;
                }
                if (!spoken.isEmpty()) {
                    speak(context, spoken);
                    return;
                }
            }
        }
        List<Map<String, Object>> phoneOnly = deviceSteps(localSteps, false);
        List<Map<String, Object>> remoteOnly = deviceSteps(localSteps, true);
        if (namedRemote || !remoteOnly.isEmpty()) {
            if (phoneOnly.isEmpty()) {
                speak(context, "laptop offline");
                return;
            }
            speak(context, "laptop offline");
        }
        String key = KeyVault.loadKey(context);
        if ((key == null || key.isEmpty()) && phoneOnly.isEmpty()) {
            speak(context, "Add a Muse key in Setup.");
            return;
        }
        List<Map<String, Object>> tools = sparkPhone(context, text);
        if (tools.isEmpty()) {
            tools = phoneOnly;
        } else {
            tools = deviceSteps(tools, false);
        }
        if (tools.isEmpty()) {
            tools = BeeAsk.splitUtterance(text);
            tools = deviceSteps(tools, false);
        }
        if (tools.isEmpty()) {
            if (!spoken.isEmpty()) {
                speak(context, spoken);
                return;
            }
            if (BeeMind.isMind(text)) {
                speak(context, BeeAsk.clampSpeak("Brain empty — run ingest."));
                return;
            }
            speak(context, BeeAsk.clampSpeak("Didn't catch that."));
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
            speak(context, BeeAsk.clampSpeak("Didn't catch that."));
            return;
        }
        if (BeeAsk.needsConfirm(steps)) {
            String prompt = BeeAsk.thisOrThat(steps);
            PendingPlan.set(steps, prompt);
            try {
                IslandService s = IslandService.current();
                if (s != null) {
                    s.showConfirmPulse();
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
            String pkg = touchDraft.get("package") == null
                    ? "com.whatsapp.w4b" : String.valueOf(touchDraft.get("package"));
            if (!draft.isEmpty() && !to.isEmpty()) {
                List<Map<String, Object>> send = new ArrayList<Map<String, Object>>();
                Map<String, Object> step = new HashMap<String, Object>();
                step.put("tool", "whatsapp_send");
                Map<String, Object> args = new HashMap<String, Object>();
                args.put("to", to);
                String body = draft;
                String lowDraft = draft.toLowerCase(Locale.US);
                int idx = lowDraft.indexOf("suggested reply:");
                if (idx >= 0) {
                    body = draft.substring(idx + "suggested reply:".length()).trim();
                }
                args.put("text", body);
                args.put("package", pkg);
                step.put("args", args);
                step.put("device", "phone");
                send.add(step);
                String prompt = "Send to " + to + "?";
                PendingPlan.set(send, prompt);
                String line = resultSpoken;
                if (line.isEmpty()) {
                    line = "Suggested: " + body;
                }
                line = line + " Say confirm to send.";
                speak(context, line);
                return;
            }
        }
        if (clickFail && !recovering) {
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
                || "chat_touch".equals(tool);
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
            return "Failed.";
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
                speakTts(context, clamped);
            }
        });
    }

    private static void speakTts(Context context, final String line) {
        if (context == null || line == null || line.isEmpty()) {
            return;
        }
        if (tts == null) {
            ttsReady = false;
            tts = new TextToSpeech(context.getApplicationContext(), new TextToSpeech.OnInitListener() {
                @Override
                public void onInit(int status) {
                    ttsReady = status == TextToSpeech.SUCCESS;
                    if (ttsReady && tts != null) {
                        try {
                            tts.setLanguage(Locale.US);
                            tts.speak(line, TextToSpeech.QUEUE_FLUSH, null, "bee");
                        } catch (Exception ignored) {
                        }
                    }
                }
            });
            return;
        }
        if (ttsReady) {
            try {
                tts.speak(line, TextToSpeech.QUEUE_FLUSH, null, "bee");
            } catch (Exception ignored) {
            }
        }
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
            tools = MuseClient.parseFunctionCalls(raw);
            String spoken = MuseClient.extractOutputText(raw);
            if (spoken != null && !spoken.trim().isEmpty()) {
                lastSpoken = BeeAsk.clampSpeak(spoken);
            }
            if (tools.isEmpty()) {
                tools = BeeAsk.splitUtterance(text);
            }
        } catch (Exception ignored) {
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
