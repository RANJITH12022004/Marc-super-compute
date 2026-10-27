package com.bee.island;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Same ask() DAG for island tap, Chat composer, and ACTION_ASK.
 * Confirm-before-act: tools NEVER auto-run. runAsk only stages a
 * PendingPlan and speaks the this-or-that prompt; finish() runs
 * only from an explicit confirm with pending steps.
 * Phone tools run on device; laptop/server go to Rox or "laptop offline".
 */
final class AskRouter {
    private AskRouter() {
    }

    static void handle(final Context context, final String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return;
        }
        final String text = raw.trim();
        ChatStore.add(context, true, text);
        String kind = BeeAsk.classifyVoice(text);
        if ("refuse".equals(kind)) {
            speak(context, "No.");
            return;
        }
        if ("cancel".equals(kind)) {
            PendingPlan.clear();
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
                speak(context, BeeAsk.clampLine("Got you \u2014 didn\u2019t catch an action."));
            }
            return;
        }
        if (BeeMind.isMind(text)) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    BeeMind.handle(context, text);
                }
            }, "bee-mind").start();
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
        Map<String, Object> plan = BeeAsk.planAsk(text);
        String kind = String.valueOf(plan.get("kind"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> steps = castSteps(plan.get("steps"));
        if ("refuse".equals(kind)) {
            speak(context, "No.");
            return;
        }
        if ("local_fast".equals(kind) || "dag".equals(kind)) {
            if (steps.isEmpty()) {
                speak(context, BeeAsk.clampLine("Got you \u2014 didn\u2019t catch an action."));
                return;
            }
            String prompt = BeeAsk.thisOrThat(steps);
            PendingPlan.set(steps, prompt);
            speak(context, prompt);
            return;
        }
        if ("spark".equals(kind) || "wonder".equals(kind)) {
            String key = KeyVault.loadKey(context);
            if (key == null || key.isEmpty()) {
                speak(context, "Add a Muse key in Setup.");
                return;
            }
            String model = "wonder".equals(kind) ? KeyVault.wonder(context) : KeyVault.spark(context);
            try {
                String mind = BeeMind.injectContext(context);
                String raw = MuseClient.complete(key, model, text, mind);
                List<Map<String, Object>> tools = MuseClient.parseFunctionCalls(raw);
                if (tools.isEmpty()) {
                    tools = BeeAsk.splitUtterance(text);
                }
                if (tools.isEmpty()) {
                    speak(context, BeeAsk.clampLine("Got you \u2014 didn\u2019t catch an action."));
                    return;
                }
                String prompt = BeeAsk.thisOrThat(tools);
                PendingPlan.set(tools, prompt);
                speak(context, prompt);
            } catch (Exception e) {
                speak(context, "Failed.");
            }
            return;
        }
        // Confused / weak parse: ack only, never auto-run.
        if (steps.isEmpty()) {
            speak(context, BeeAsk.clampLine("Got you \u2014 didn\u2019t catch an action."));
            return;
        }
        String prompt = BeeAsk.thisOrThat(steps);
        PendingPlan.set(steps, prompt);
        speak(context, prompt);
    }

    static void finish(Context context, List<Map<String, Object>> steps) {
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
        List<String> names = new ArrayList<String>();
        boolean anyOffline = false;
        boolean anyOk = false;
        for (Map<String, Object> r : results) {
            if (r == null) {
                continue;
            }
            if (Boolean.TRUE.equals(r.get("ok"))) {
                anyOk = true;
            }
            Object err = r.get("error");
            if (err != null && String.valueOf(err).toLowerCase(Locale.US).contains("laptop offline")) {
                anyOffline = true;
            }
            Object tool = r.get("tool");
            if (tool != null) {
                names.add(String.valueOf(tool));
            }
        }
        String line = BeeAsk.lineFor("wave", names);
        if (line.isEmpty()) {
            line = anyOk ? "Done." : "Failed.";
        }
        if (anyOffline) {
            line = BeeAsk.clampLine(line.isEmpty() ? "laptop offline" : line + " \u00b7 laptop offline");
        }
        speak(context, line);
    }

    static void speak(final Context context, final String line) {
        final String clamped = BeeAsk.clampLine(line);
        new Handler(Looper.getMainLooper()).post(new Runnable() {
            @Override
            public void run() {
                ChatStore.add(context, false, clamped);
            }
        });
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
