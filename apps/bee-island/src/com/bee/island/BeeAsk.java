package com.bee.island;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Bee ask DAG (no Android imports). Mirrors bee_ask.py + bee_island.py.
 * Needle is never enabled on the live path.
 */
public final class BeeAsk {

    public static final String SPARK_MODEL = "muse-spark-1.3";
    public static final String WONDER_MODEL = "muse-wonder-1.0";
    public static final int ISLAND_MAX = 40;
    public static final int SPEAK_MAX = 240;

    public static final Set<String> CONFIRM_TOOLS = Collections.unmodifiableSet(
            new HashSet<String>(Arrays.asList(
                    "whatsapp_send",
                    "dial",
                    "instagram_send",
                    "sms_send",
                    "mail_compose",
                    "mail_send",
                    "calendar_create",
                    "open_food_search")));

    /** Brain tools must never hit PhoneActions. */
    public static boolean isBrainTool(String tool) {
        if (tool == null) {
            return false;
        }
        String t = tool.trim().toLowerCase(Locale.US);
        return "mind_recall".equals(t)
                || "mind_note".equals(t)
                || "whoami".equals(t)
                || "who_am_i".equals(t);
    }

    public static boolean isVagueContact(String to) {
        if (to == null) {
            return true;
        }
        String t = to.trim().toLowerCase(Locale.US);
        if (t.isEmpty()) {
            return true;
        }
        return "someone".equals(t)
                || "somebody".equals(t)
                || "a friend".equals(t)
                || "them".equals(t)
                || "him".equals(t)
                || "her".equals(t);
    }

    private static final Pattern CLAUSE_SPLIT = Pattern.compile(
            "\\s*;\\s*"
                    + "|\\s*,?\\s*\\bafter\\s+that\\b\\s*,?\\s*"
                    + "|\\s*,?\\s*\\band\\s+then\\b\\s*,?\\s*"
                    + "|\\s*,?\\s*\\bthen\\b\\s*,?\\s*"
                    + "|\\s*(?:,\\s*(?:and\\s+)?|\\band\\b\\s+)"
                    + "(?=(?:text|whatsapp|play|email|mail|call|dial|open|auto\\s*scroll|scroll|swipe|tap|click|type|search)\\b)",
            Pattern.CASE_INSENSITIVE);

    private BeeAsk() {
    }

    public static boolean needleEnabled() {
        return false;
    }

    public static boolean needsConfirm(String tool) {
        if (tool == null) {
            return false;
        }
        String t;
        try {
            t = tool.trim();
        } catch (Exception e) {
            return false;
        }
        return CONFIRM_TOOLS.contains(t);
    }

    public static boolean needsConfirm(Map<?, ?> step) {
        if (step == null) {
            return false;
        }
        Object toolObj;
        try {
            toolObj = step.get("tool");
        } catch (Exception e) {
            return false;
        }
        if (toolObj instanceof String) {
            return needsConfirm((String) toolObj);
        }
        return false;
    }

    public static boolean needsConfirm(List<?> steps) {
        if (steps == null) {
            return false;
        }
        List<?> seq;
        try {
            seq = new ArrayList<Object>(steps);
        } catch (Exception e) {
            return false;
        }
        for (Object s : seq) {
            if (s instanceof String) {
                if (needsConfirm((String) s)) {
                    return true;
                }
            } else if (s instanceof Map) {
                if (needsConfirm((Map<?, ?>) s)) {
                    return true;
                }
            } else if (s instanceof List) {
                List<?> nested = (List<?>) s;
                if (!nested.isEmpty() && nested.get(0) instanceof String) {
                    if (needsConfirm((String) nested.get(0))) {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    public static String clampLine(String value) {
        if (value == null) {
            return "";
        }
        String s = value.trim().replaceAll("\\s+", " ");
        if (s.length() > ISLAND_MAX) {
            return s.substring(0, ISLAND_MAX);
        }
        return s;
    }

    public static String clampSpeak(String value) {
        if (value == null) {
            return "";
        }
        String s = value.trim().replaceAll("\\s+", " ");
        if (s.length() > SPEAK_MAX) {
            return s.substring(0, SPEAK_MAX);
        }
        return s;
    }

    public static String lineFor(String state) {
        return lineFor(state, null);
    }

    public static String lineFor(String state, List<String> agents) {
        if ("idle".equals(state)) {
            return "";
        }
        if ("listen".equals(state)) {
            return "Listening…";
        }
        if ("plan".equals(state)) {
            return "On it.";
        }
        if ("confirm".equals(state)) {
            return "Say yes or cancel.";
        }
        if ("done".equals(state)) {
            return "Done.";
        }
        if ("fail".equals(state)) {
            return "That didn't land.";
        }
        if ("wave".equals(state)) {
            if (agents == null || agents.isEmpty()) {
                return "";
            }
            StringBuilder b = new StringBuilder();
            for (String a : agents) {
                if (a == null) {
                    continue;
                }
                String t = a.trim();
                if (t.isEmpty()) {
                    continue;
                }
                if (b.length() > 0) {
                    b.append(" · ");
                }
                b.append(t);
            }
            return clampLine(b.toString());
        }
        return "";
    }

    public static boolean skipMuse(String text) {
        if (text == null) {
            return false;
        }
        String low = text.toLowerCase(Locale.US);
        if (low.contains("on my laptop") || low.contains("on the server")) {
            return false;
        }
        if (low.matches("(?s).*\\bdemo\\b.*")) {
            return false;
        }
        if (low.contains("email")) {
            return false;
        }
        // Text/WA/script: local only when contact looks real; vague → Muse leftover.
        // Hands / chats / script → Muse-first (AskRouter); skipMuse stays false for those.
        if (low.contains("last") && (low.contains("chat") || low.contains("chats"))
                || low.contains("list chats") || low.contains("show chats")
                || low.contains("b chat") || low.contains("business whatsapp")) {
            return false;
        }
        if (low.matches("(?s).*\\b(?:script|draft|write)\\b.*\\b(?:message|msg|text)\\b.*")) {
            return false;
        }
        if (low.contains("whatsapp") || low.contains("text ")) {
            List<Map<String, Object>> probe = splitUtterance(text);
            if (probe != null && !probe.isEmpty()) {
                Object argsObj = probe.get(0).get("args");
                if (argsObj instanceof Map) {
                    Object to = ((Map<?, ?>) argsObj).get("to");
                    if (isVagueContact(to == null ? "" : String.valueOf(to))) {
                        return false;
                    }
                }
            }
            return true;
        }
        if (low.matches("(?s).*\\b(?:call|dial)\\b.*")) {
            List<Map<String, Object>> probe = splitUtterance(text);
            if (probe != null && !probe.isEmpty()) {
                Object argsObj = probe.get(0).get("args");
                if (argsObj instanceof Map) {
                    Object to = ((Map<?, ?>) argsObj).get("to");
                    if (to == null) {
                        to = ((Map<?, ?>) argsObj).get("contact");
                    }
                    if (isVagueContact(to == null ? "" : String.valueOf(to))) {
                        return false;
                    }
                } else {
                    return false;
                }
            }
            return true;
        }
        if (low.contains("notification") || low.contains("suggest reply")
                || low.contains("what should i reply")) {
            return true;
        }
        if (low.matches("(?s).*\\b(?:touch|tell|ping)\\b.*\\b(?:about|re|regarding)\\b.*")
                || low.matches("(?s).*\\bmessage\\b.+\\babout\\b.*")) {
            return true;
        }
        if (low.matches("(?s).*\\bplay\\b.*")
                || low.contains("reels")
                || low.contains("auto scroll")
                || low.contains("autoscroll")) {
            return false;
        }
        if ((low.contains("instagram") || low.contains("insta"))
                && (low.contains("scroll") || low.contains("reel"))) {
            return false;
        }
        if ((low.contains("youtube") || low.contains("youtu"))
                && (low.contains("play") || low.contains("search") || low.contains("first"))) {
            return false;
        }
        List<String> clauses = splitClauses(text);
        if (clauses.size() > 1) {
            return false;
        }
        if (text.contains(";")
                || low.matches("(?s).*\\bafter\\s+that\\b.*")
                || low.matches("(?s).*\\bthen\\b.*")) {
            return false;
        }
        if (low.matches("(?s).*\\band\\b\\s+(?:text|whatsapp|play|email|mail|call|dial|open|type)\\b.*")) {
            return false;
        }
        if (low.matches("(?s).*,\\s*(?:and\\s+)?(?:text|whatsapp|play|email|mail|call|dial|open)\\b.*")) {
            return false;
        }
        if (low.matches("(?s).*\\b(?:scroll|swipe|tap|click)\\b.*")) {
            return false;
        }
        String stripped = low.trim();
        if (stripped.startsWith("type ") || "type".equals(stripped)) {
            return true;
        }
        if (stripped.startsWith("open ") || "open".equals(stripped)) {
            return true;
        }
        if (stripped.matches("open\\s+\\S(?s).*")) {
            return true;
        }
        if (stripped.matches("play\\b(?s).*")) {
            return true;
        }
        if (low.contains("youtube")) {
            return true;
        }
        if (low.contains("google")) {
            return true;
        }
        if (stripped.startsWith("search ") || "search".equals(stripped)) {
            return true;
        }
        if (stripped.matches("search\\b(?s).*")) {
            return true;
        }
        if (low.matches("(?s).*\\bopen\\s+\\S+.*\\btype\\s+.+")) {
            return true;
        }
        return false;
    }

    public static List<String> splitClauses(String text) {
        List<String> out = new ArrayList<String>();
        if (text == null || text.trim().isEmpty()) {
            return out;
        }
        String[] parts = CLAUSE_SPLIT.split(text);
        for (String p : parts) {
            if (p == null) {
                continue;
            }
            String s = p.trim();
            if (!s.isEmpty()) {
                out.add(s);
            }
        }
        return out;
    }

    public static String stripVoice(String text) {
        String low = text == null ? "" : text.toLowerCase(Locale.US);
        return low.trim().replaceAll("^[?.!,\\s]+|[?.!,\\s]+$", "").trim();
    }

    public static boolean isGreeting(String text) {
        String stripped = stripVoice(text);
        return "hi".equals(stripped)
                || "hello".equals(stripped)
                || "hey".equals(stripped)
                || "hey marc".equals(stripped)
                || "hey mark".equals(stripped)
                || "hey bee".equals(stripped);
    }

    public static String classifyVoice(String text) {
        String low = text == null ? "" : text.toLowerCase(Locale.US);
        if (low.contains("reboot")
                || low.contains("shutdown")
                || low.contains("sudo")
                || low.contains("poweroff")
                || low.contains("rm -rf")) {
            return "refuse";
        }
        String stripped = stripVoice(text);
        if ("yes".equals(stripped)
                || "yeah".equals(stripped)
                || "yep".equals(stripped)
                || "ok".equals(stripped)
                || "okay".equals(stripped)
                || "confirm".equals(stripped)
                || "send".equals(stripped)
                || "send it".equals(stripped)
                || "do it".equals(stripped)
                || "go ahead".equals(stripped)
                || "please".equals(stripped)
                || "that".equals(stripped)) {
            return "confirm";
        }
        if ("no".equals(stripped)
                || "nope".equals(stripped)
                || "cancel".equals(stripped)
                || "stop".equals(stripped)) {
            return "cancel";
        }
        return "ask";
    }

    /**
     * Full TTS confirm line (includes WhatsApp message body). Island line
     * stays short via {@link #thisOrThat} / {@link #clampLine}.
     */
    public static String confirmSpeak(List<?> steps) {
        if (steps == null || steps.isEmpty()) {
            return "Say yes to confirm.";
        }
        try {
            if (steps.size() > 1) {
                return clampSpeak("Do these " + steps.size() + " actions? Say yes.");
            }
        } catch (Exception e) {
            return "Say yes to confirm.";
        }
        Object first;
        try {
            first = steps.get(0);
        } catch (Exception e) {
            return "Say yes to confirm.";
        }
        if (!(first instanceof Map)) {
            return "Say yes to confirm.";
        }
        Map<?, ?> row = (Map<?, ?>) first;
        String t = row.get("tool") == null ? "" : String.valueOf(row.get("tool"));
        Map<?, ?> args = null;
        Object rawArgs = row.get("args");
        if (rawArgs instanceof Map) {
            args = (Map<?, ?>) rawArgs;
        }
        if ("whatsapp_send".equals(t) || "sms_send".equals(t)) {
            String to = normSpace(argString(args, "to"));
            String text = normSpace(argString(args, "text"));
            if (text.isEmpty()) {
                text = normSpace(argString(args, "body"));
            }
            String kind = "sms_send".equals(t) ? "SMS" : "WhatsApp";
            if (to.isEmpty()) {
                return clampSpeak(text.isEmpty()
                        ? ("Send " + kind + "? Say yes.")
                        : ("Send: " + text + ". Say yes."));
            }
            if (text.isEmpty()) {
                return clampSpeak("Message " + to + "? Say yes.");
            }
            return clampSpeak(kind + " " + to + ": " + text + ". Say yes to send.");
        }
        if ("mail_compose".equals(t) || "mail_send".equals(t)) {
            String to = normSpace(argString(args, "to"));
            String subject = normSpace(argString(args, "subject"));
            String body = normSpace(argString(args, "text"));
            if (body.isEmpty()) {
                body = normSpace(argString(args, "body"));
            }
            String bits = to.isEmpty() ? "email" : ("email " + to);
            if (!subject.isEmpty()) {
                bits = bits + ", " + subject;
            }
            if (!body.isEmpty()) {
                bits = bits + ": " + body;
            }
            return clampSpeak(bits + ". Say yes to send.");
        }
        if ("dial".equals(t)) {
            String to = normSpace(argString(args, "to"));
            if (to.isEmpty()) {
                to = normSpace(argString(args, "contact"));
            }
            return clampSpeak(to.isEmpty()
                    ? "Place the call? Say yes."
                    : ("Call " + to + "? Say yes."));
        }
        String shortPrompt = thisOrThat(steps);
        if (shortPrompt == null || shortPrompt.isEmpty()) {
            return "Say yes to confirm.";
        }
        if (shortPrompt.endsWith("?")) {
            return clampSpeak(shortPrompt + " Say yes.");
        }
        return clampSpeak(shortPrompt + ". Say yes.");
    }

    public static String thisOrThat(List<?> steps) {
        if (steps == null || steps.isEmpty()) {
            return "";
        }
        int n;
        try {
            n = steps.size();
        } catch (Exception e) {
            return "";
        }
        if (n == 0) {
            return "";
        }
        if (n > 1) {
            return "Do this: " + n + " tools?";
        }
        Object first;
        try {
            first = steps.get(0);
        } catch (Exception e) {
            return "Do this: 1 tool?";
        }
        if (!(first instanceof Map)) {
            return "Do this: 1 tool?";
        }
        Map<?, ?> row = (Map<?, ?>) first;
        Object toolObj = row.get("tool");
        if (toolObj == null) {
            return "Do this: 1 tool?";
        }
        String t;
        try {
            t = String.valueOf(toolObj);
        } catch (Exception e) {
            return "Do this: 1 tool?";
        }
        if (t == null || t.trim().isEmpty()) {
            return "Do this: 1 tool?";
        }
        Map<?, ?> args = null;
        Object rawArgs = row.get("args");
        if (rawArgs instanceof Map) {
            args = (Map<?, ?>) rawArgs;
        }
        String label;
        try {
            if ("play_music".equals(t)) {
                String q = normSpace(argString(args, "query"));
                label = q.isEmpty() ? "play music" : ("play " + q).trim();
            } else if ("whatsapp_send".equals(t)) {
                String to = normSpace(argString(args, "to"));
                String text = normSpace(argString(args, "text"));
                if (text.isEmpty()) {
                    text = normSpace(argString(args, "body"));
                }
                if (to.isEmpty()) {
                    label = text.isEmpty() ? "send text" : ("send: " + text);
                } else if (text.isEmpty()) {
                    label = ("text " + to).trim();
                } else {
                    label = ("text " + to + ": " + text).trim();
                }
            } else if ("mail_compose".equals(t)) {
                String to = normSpace(argString(args, "to"));
                label = to.isEmpty() ? "send email" : ("email " + to).trim();
            } else if ("dial".equals(t)) {
                String to = normSpace(argString(args, "to"));
                if (to.isEmpty()) {
                    to = normSpace(argString(args, "contact"));
                }
                label = to.isEmpty() ? "call" : ("call " + to).trim();
            } else if ("open_app".equals(t)) {
                String app = normSpace(argString(args, "app"));
                label = app.isEmpty() ? "open app" : ("open " + app).trim();
            } else if ("type_into".equals(t)) {
                String txt = normSpace(argString(args, "text"));
                label = txt.isEmpty() ? "type" : ("type " + txt).trim();
            } else {
                label = t.replace('_', ' ').trim();
                if (label.isEmpty()) {
                    label = "1 tool";
                }
            }
        } catch (Exception e) {
            label = t.replace('_', ' ').trim();
            if (label.isEmpty()) {
                label = "1 tool";
            }
        }
        label = normSpace(label);
        if (label.isEmpty()) {
            return "Do this: 1 tool?";
        }
        String s = "Do this: " + label + "?";
        if (s.length() <= ISLAND_MAX) {
            return s;
        }
        int maxLabel = ISLAND_MAX - "Do this: ".length() - "?".length();
        if (maxLabel < 1) {
            maxLabel = 1;
        }
        if (label.length() > maxLabel) {
            label = label.substring(0, maxLabel).replaceAll("\\s+$", "");
        }
        s = "Do this: " + label + "?";
        if (s.length() > ISLAND_MAX) {
            s = s.substring(0, ISLAND_MAX);
        }
        return s;
    }

    public static Map<String, Object> decide(String kind, List<?> pending) {
        boolean hasPending = false;
        try {
            hasPending = pending != null && !pending.isEmpty();
        } catch (Exception e) {
            hasPending = false;
        }
        String k = null;
        try {
            k = kind == null ? null : kind.trim().toLowerCase(Locale.US);
        } catch (Exception e) {
            k = null;
        }
        String action;
        if ("confirm".equals(k)) {
            action = hasPending ? "run" : "ack";
        } else if ("cancel".equals(k)) {
            action = "drop";
        } else if ("refuse".equals(k)) {
            action = "refuse";
        } else if ("ask".equals(k)) {
            if (!hasPending) {
                action = "ack";
            } else if (needsConfirm(pending)) {
                action = "ask";
            } else {
                action = "run";
            }
        } else {
            if (!hasPending) {
                action = "ack";
            } else if (needsConfirm(pending)) {
                action = "ask";
            } else {
                action = "run";
            }
        }
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("action", action);
        return out;
    }

    public static List<Map<String, Object>> splitUtterance(String text) {
        List<Map<String, Object>> steps = new ArrayList<Map<String, Object>>();
        if (text != null) {
            String lowAll = text.toLowerCase(Locale.US);
            if ((lowAll.contains("youtube") || lowAll.contains("youtu"))
                    && (lowAll.contains("play") || lowAll.contains("search") || lowAll.contains("first"))) {
                Map<String, Object> row = new HashMap<String, Object>();
                row.put("id", "s1");
                row.put("tool", "youtube_play");
                Map<String, String> args = new HashMap<String, String>();
                if (lowAll.contains("first") && (lowAll.contains("play") || lowAll.contains("video"))) {
                    args.put("mode", "first");
                } else {
                    args.put("mode", "search");
                    Matcher yq = Pattern.compile("(?i)(?:search(?:\\s+for)?|play)\\s+(.+)$").matcher(text);
                    if (yq.find()) {
                        args.put("query", nz(yq.group(1)));
                    }
                }
                row.put("args", args);
                row.put("device", "phone");
                row.put("after", new ArrayList<String>());
                steps.add(row);
                return steps;
            }
            if ((lowAll.contains("instagram") || lowAll.contains("insta"))
                    && lowAll.contains("scroll")) {
                Map<String, Object> row = new HashMap<String, Object>();
                row.put("id", "s1");
                row.put("tool", "auto_scroll");
                Map<String, String> args = new HashMap<String, String>();
                args.put("direction", "up");
                row.put("args", args);
                row.put("device", "phone");
                row.put("after", new ArrayList<String>());
                steps.add(row);
                return steps;
            }
            Matcher wa = Pattern.compile(
                    "(?is)open\\s+whats?app.*?search\\s+(\\S+).*?(?:text|message)(?:\\s+him|\\s+her|\\s+them)?\\s+(.+)$")
                    .matcher(text);
            if (wa.find()) {
                Map<String, Object> row = new HashMap<String, Object>();
                row.put("id", "s1");
                row.put("tool", "whatsapp_send");
                Map<String, String> args = new HashMap<String, String>();
                args.put("to", nz(wa.group(1)).replaceAll("[,;.:]+$", "").replaceAll("'s$", ""));
                args.put("text", nz(wa.group(2)));
                row.put("args", args);
                row.put("device", "phone");
                row.put("after", new ArrayList<String>());
                steps.add(row);
                return steps;
            }
            Matcher sp = Pattern.compile("(?i)open\\s+spotify\\s+(?:and\\s+)?play\\s+(.+)$")
                    .matcher(text);
            if (sp.find()) {
                Map<String, Object> row = new HashMap<String, Object>();
                row.put("id", "s1");
                row.put("tool", "play_music");
                Map<String, String> args = new HashMap<String, String>();
                args.put("query", nz(sp.group(1)));
                row.put("args", args);
                row.put("device", "phone");
                row.put("after", new ArrayList<String>());
                steps.add(row);
                return steps;
            }
        }
        List<String> clauses = splitClauses(text);
        String lowText = text == null ? "" : text.toLowerCase(Locale.US);
        int pos = 0;
        int[] starts = new int[clauses.size()];
        int[] ends = new int[clauses.size()];
        for (int i = 0; i < clauses.size(); i++) {
            String cl = clauses.get(i).toLowerCase(Locale.US);
            int idx = lowText.indexOf(cl, pos);
            if (idx < 0) {
                idx = pos;
            }
            starts[i] = idx;
            ends[i] = idx + cl.length();
            pos = ends[i];
        }
        for (int i = 0; i < clauses.size(); i++) {
            Map<String, Object> tool = clauseToTool(clauses.get(i));
            if (tool == null || tool.get("tool") == null) {
                continue;
            }
            String sid = "s" + (steps.size() + 1);
            List<String> after = new ArrayList<String>();
            if (!steps.isEmpty()) {
                String gap = "";
                try {
                    gap = lowText.substring(ends[i - 1], starts[i]);
                } catch (Exception ignored) {
                    gap = "";
                }
                if (gap.matches("(?s).*\\bthen\\b.*") || gap.matches("(?s).*\\bafter\\s+that\\b.*")) {
                    Object prev = steps.get(steps.size() - 1).get("id");
                    if (prev != null) {
                        after.add(String.valueOf(prev));
                    }
                }
            }
            Map<String, Object> step = new HashMap<String, Object>();
            step.put("id", sid);
            step.put("tool", tool.get("tool"));
            step.put("args", tool.get("args"));
            step.put("device", tool.get("device"));
            step.put("after", after);
            steps.add(step);
        }
        return steps;
    }

    public static Map<String, Object> planAsk(String text) {
        return planAsk(text, null, false);
    }

    public static Map<String, Object> planAsk(String text, List<Map<String, Object>> sparkTools, boolean longUtterance) {
        Map<String, Object> out = new HashMap<String, Object>();
        if ("refuse".equals(classifyVoice(text))) {
            out.put("steps", new ArrayList<Object>());
            out.put("model", SPARK_MODEL);
            out.put("kind", "refuse");
            return out;
        }
        if (skipMuse(text)) {
            List<Map<String, Object>> steps = splitUtterance(text);
            if (isPhoneRecipe(steps)) {
                out.put("steps", steps);
                out.put("model", SPARK_MODEL);
                out.put("kind", "spark");
                return out;
            }
            out.put("steps", steps);
            out.put("model", "local_fast");
            out.put("kind", "local_fast");
            return out;
        }
        List<Map<String, Object>> dag = splitUtterance(text);
        if (isPhoneRecipe(dag) && dag.size() == 1) {
            out.put("steps", dag);
            out.put("model", SPARK_MODEL);
            out.put("kind", "spark");
            return out;
        }
        if (dag.size() >= 2) {
            out.put("steps", dag);
            out.put("model", SPARK_MODEL);
            out.put("kind", "dag");
            return out;
        }
        if (sparkTools != null && !sparkTools.isEmpty()) {
            out.put("steps", sparkTools);
            out.put("model", SPARK_MODEL);
            out.put("kind", "spark");
            return out;
        }
        boolean isLong = longUtterance || (text != null && text.length() > 80);
        if (isLong) {
            out.put("steps", new ArrayList<Object>());
            out.put("model", WONDER_MODEL);
            out.put("kind", "wonder");
            return out;
        }
        out.put("steps", new ArrayList<Object>());
        out.put("model", SPARK_MODEL);
        out.put("kind", "spark");
        return out;
    }

    public interface StepRunner {
        Map<String, Object> run(Map<String, Object> step);
    }

    public static List<Map<String, Object>> dispatch(List<Map<String, Object>> steps,
                                                     StepRunner phone,
                                                     StepRunner laptop,
                                                     boolean laptopOk) {
        List<Map<String, Object>> results = new ArrayList<Map<String, Object>>();
        if (steps == null) {
            return results;
        }
        List<Map<String, Object>> seq = new ArrayList<Map<String, Object>>();
        for (Map<String, Object> step : steps) {
            seq.add(step);
        }
        for (int i = 0; i < seq.size(); i++) {
            Map<String, Object> step = seq.get(i);
            if (step == null || step.get("tool") == null) {
                continue;
            }
            Object deviceObj = step.get("device");
            String device = deviceObj == null ? "phone" : String.valueOf(deviceObj).toLowerCase(Locale.US);
            boolean isLaptop = "laptop".equals(device) || "server".equals(device);
            if (isLaptop) {
                if (laptopOk && laptop != null) {
                    results.add(laptop.run(step));
                } else {
                    Map<String, Object> miss = new HashMap<String, Object>();
                    miss.put("id", step.get("id"));
                    miss.put("ok", Boolean.FALSE);
                    miss.put("error", "laptop offline");
                    results.add(miss);
                }
            } else if (phone != null) {
                results.add(phone.run(step));
                String tool = String.valueOf(step.get("tool")).toLowerCase(Locale.US);
                if ("open_app".equals(tool) && i + 1 < seq.size()) {
                    Map<String, Object> next = seq.get(i + 1);
                    String nt = "";
                    if (next != null && next.get("tool") != null) {
                        nt = String.valueOf(next.get("tool")).toLowerCase(Locale.US);
                    }
                    if (isHandsTool(nt) && !"wait_ms".equals(nt)) {
                        try {
                            Thread.sleep(800);
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    }
                }
            }
        }
        return results;
    }

    static boolean isPhoneRecipe(List<Map<String, Object>> steps) {
        if (steps == null || steps.isEmpty()) {
            return false;
        }
        for (int i = 0; i < steps.size(); i++) {
            Map<String, Object> step = steps.get(i);
            if (step == null) {
                continue;
            }
            Object t = step.get("tool");
            String tool = t == null ? "" : String.valueOf(t);
            if ("whatsapp_send".equals(tool) || "play_music".equals(tool)
                    || "auto_scroll".equals(tool) || "youtube_play".equals(tool)
                    || "youtube_search".equals(tool)
                    || "notifications_list".equals(tool)
                    || "suggest_reply".equals(tool)
                    || "chat_touch".equals(tool)
                    || "phone_profile_snapshot".equals(tool)
                    || "sms_send".equals(tool)
                    || "mail_compose".equals(tool)
                    || "mail_send".equals(tool)
                    || "dial".equals(tool)) {
                return true;
            }
        }
        return false;
    }

    static boolean isHandsTool(String tool) {
        return "click_text".equals(tool)
                || "swipe".equals(tool)
                || "scroll".equals(tool)
                || "auto_scroll".equals(tool)
                || "closed_loop".equals(tool)
                || "type_into".equals(tool)
                || "press_back".equals(tool)
                || "wait_ms".equals(tool);
    }

    static Map<String, Object> clauseToTool(String clause) {
        if (clause == null) {
            clause = "";
        }
        String low = clause.toLowerCase(Locale.US);
        String device = (low.contains("on my laptop") || low.contains("on the server")) ? "laptop" : "phone";
        String cleaned = clause.replaceAll("(?i)\\bon\\s+my\\s+laptop\\b", " ").replaceAll("(?i)\\bon\\s+the\\s+server\\b", " ").trim();
        Map<String, Object> row = new HashMap<String, Object>();
        row.put("device", device);
        Matcher m;
        m = Pattern.compile("(?i)^\\s*(?:auto\\s*scroll|scroll|swipe)\\b(.*)$").matcher(cleaned);
        if (m.find()) {
            String rest = nz(m.group(1)).toLowerCase(Locale.US);
            if (low.contains("reel") || low.contains("auto")) {
                row.put("tool", "auto_scroll");
                Map<String, String> args = new HashMap<String, String>();
                args.put("direction", "up");
                row.put("args", args);
                return row;
            }
            String dir = "up";
            if (rest.contains("down")) {
                dir = "down";
            } else if (rest.contains("left")) {
                dir = "left";
            } else if (rest.contains("right")) {
                dir = "right";
            }
            row.put("tool", "swipe");
            Map<String, String> args = new HashMap<String, String>();
            args.put("direction", dir);
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*(?:tap|click)\\b\\s*(.*)$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "click_text");
            Map<String, String> args = new HashMap<String, String>();
            args.put("text", nz(m.group(1)));
            row.put("args", args);
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:touch|tell|ping|message)\\s+(.+?)\\s+(?:about|re|regarding)\\s+(.+)$")
                .matcher(cleaned);
        if (m.find()) {
            row.put("tool", "chat_touch");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("topic", nz(m.group(2)));
            args.put("channel", "whatsapp");
            args.put("package", waPackageFor(low));
            row.put("args", args);
            return row;
        }
        if (low.contains("phone profile")
                || low.contains("snapshot phone")
                || low.contains("refresh my phone profile")
                || low.contains("phone settings snapshot")
                || (low.contains("about phone") && low.contains("snapshot"))) {
            row.put("tool", "phone_profile_snapshot");
            row.put("args", new HashMap<String, String>());
            return row;
        }
        if (low.matches("(?s).*\\b(?:new\\s+)?notifications?\\b.*")
                || low.contains("what are the new notification")) {
            row.put("tool", "notifications_list");
            row.put("args", new HashMap<String, String>());
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:what\\s+should\\s+i\\s+reply\\s+(?:to\\s+)?"
                        + "|suggest\\s+(?:a\\s+)?reply\\s+(?:to\\s+)?"
                        + "|reply\\s+to\\s+)(.+)$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "suggest_reply");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            row.put("args", args);
            return row;
        }
        if (low.contains("what should i reply") || low.contains("suggest reply")) {
            row.put("tool", "suggest_reply");
            Map<String, String> args = new HashMap<String, String>();
            Matcher m2 = Pattern.compile("(?i)(?:reply\\s+to|to)\\s+(.+)$").matcher(cleaned);
            args.put("to", m2.find() ? nz(m2.group(1)) : "");
            row.put("args", args);
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:show|list|open)?\\s*(?:my\\s+)?(?:last\\s+)?(\\d{1,2})?\\s*"
                        + "(?:whatsapp\\s+)?(?:business\\s+)?(?:b\\s+)?chats?\\s*$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "wa_list_chats");
            Map<String, String> args = new HashMap<String, String>();
            String lim = m.group(1);
            args.put("limit", lim == null || lim.isEmpty() ? "30" : lim);
            args.put("package", "com.whatsapp.w4b");
            row.put("args", args);
            return row;
        }
        if (low.contains("last") && (low.contains("chat") || low.contains("chats"))
                || low.contains("b chat") || low.contains("business whatsapp")
                || low.contains("list chats") || low.contains("show chats")) {
            row.put("tool", "wa_list_chats");
            Map<String, String> args = new HashMap<String, String>();
            args.put("limit", "30");
            args.put("package", "com.whatsapp.w4b");
            row.put("args", args);
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:script|draft|write)\\s+(?:an?\\s+)?(?:sms|text\\s+message)\\s+"
                        + "(?:to\\s+)?(.+?)\\s+(?:saying|that|about|regarding|re|:|—|-)\\s*(.+)$")
                .matcher(cleaned);
        if (m.find()) {
            row.put("tool", "chat_touch");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("topic", nz(m.group(2)));
            args.put("channel", "sms");
            row.put("args", args);
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:script|draft|write)\\s+(?:an?\\s+)?(?:email|mail)\\s+"
                        + "(?:to\\s+)?(.+?)\\s+(?:saying|that|about|regarding|re|:|—|-)\\s*(.+)$")
                .matcher(cleaned);
        if (m.find()) {
            row.put("tool", "chat_touch");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("topic", nz(m.group(2)));
            args.put("channel", "mail");
            row.put("args", args);
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:script|draft|write)\\s+(?:a\\s+)?(?:whatsapp\\s+|wa\\s+)?"
                        + "(?:message|msg|text)\\s+(?:to\\s+)?(.+?)\\s+"
                        + "(?:saying|that|about|regarding|re|:|—|-)\\s*(.+)$").matcher(cleaned);
        if (m.find()) {
            // Compose in user's tone — not send topic as literal text.
            row.put("tool", "chat_touch");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("topic", nz(m.group(2)));
            args.put("channel", channelForScript(low));
            if ("whatsapp".equals(args.get("channel"))) {
                args.put("package", waPackageFor(low));
            }
            row.put("args", args);
            return row;
        }
        m = Pattern.compile(
                "(?i)^\\s*(?:script|draft|write)\\s+(?:a\\s+)?(?:message|msg|text)\\s+"
                        + "(?:to\\s+)?(\\S+)(?:\\s+(.*))?$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "chat_touch");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("topic", m.group(2) == null ? "" : m.group(2).trim());
            args.put("channel", channelForScript(low));
            if ("whatsapp".equals(args.get("channel"))) {
                args.put("package", waPackageFor(low));
            }
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*(?:sms|text\\s+message)\\s+(\\S+)(?:\\s+(.*))?$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "sms_send");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("text", m.group(2) == null ? "" : m.group(2).trim());
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*(?:text|whatsapp)\\s+(.+?)\\s+(marc\\s+test)\\s*$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "whatsapp_send");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("text", nz(m.group(2)));
            args.put("package", waPackageFor(low));
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*(?:text|whatsapp)\\s+(\\S+)(?:\\s+(.*))?$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "whatsapp_send");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("text", m.group(2) == null ? "" : m.group(2).trim());
            args.put("package", waPackageFor(low));
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*play\\b\\s*(.*)$").matcher(cleaned);
        if (m.find()) {
            String q = nz(m.group(1));
            if (low.contains("youtube") || low.contains("youtu")) {
                row.put("tool", "youtube_play");
                Map<String, String> args = new HashMap<String, String>();
                if (q.toLowerCase(Locale.US).contains("first") || low.contains("first")) {
                    args.put("mode", "first");
                } else {
                    args.put("mode", "search");
                    args.put("query", q);
                }
                row.put("args", args);
                return row;
            }
            row.put("tool", "play_music");
            Map<String, String> args = new HashMap<String, String>();
            args.put("query", q);
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*(?:email|mail)\\s+(\\S+)(?:\\s+(.*))?$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "mail_compose");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("subject", m.group(2) == null ? "" : m.group(2).trim());
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*(?:call|dial)\\b\\s*(.*)$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "dial");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*open\\b\\s*(.*)$").matcher(cleaned);
        if (m.find()) {
            String app = nz(m.group(1));
            String appLow = app.toLowerCase(Locale.US);
            Matcher play = Pattern.compile("(?i)^spotify\\s+(?:and\\s+)?play\\s+(.+)$").matcher(app);
            if (play.find()) {
                row.put("tool", "play_music");
                Map<String, String> args = new HashMap<String, String>();
                args.put("query", nz(play.group(1)));
                row.put("args", args);
                return row;
            }
            if (appLow.contains("spotify") && appLow.contains("play")) {
                Matcher mp = Pattern.compile("(?i)play\\s+(.+)$").matcher(app);
                row.put("tool", "play_music");
                Map<String, String> args = new HashMap<String, String>();
                args.put("query", mp.find() ? nz(mp.group(1)) : app);
                row.put("args", args);
                return row;
            }
            if ((appLow.contains("instagram") || appLow.contains("insta"))
                    && (appLow.contains("scroll") || appLow.contains("reel"))) {
                row.put("tool", "auto_scroll");
                Map<String, String> args = new HashMap<String, String>();
                args.put("direction", "up");
                row.put("args", args);
                return row;
            }
            if ((appLow.contains("youtube") || appLow.contains("youtu"))
                    && (appLow.contains("play") || appLow.contains("search") || appLow.contains("first"))) {
                row.put("tool", "youtube_play");
                Map<String, String> args = new HashMap<String, String>();
                if (appLow.contains("first")) {
                    args.put("mode", "first");
                } else {
                    args.put("mode", "search");
                    Matcher yq = Pattern.compile("(?i)(?:search(?:\\s+for)?|play)\\s+(.+)$").matcher(app);
                    args.put("query", yq.find() ? nz(yq.group(1)) : app);
                }
                row.put("args", args);
                return row;
            }
            row.put("tool", "open_app");
            Map<String, String> args = new HashMap<String, String>();
            args.put("app", app);
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*type\\b\\s*(.*)$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "type_into");
            Map<String, String> args = new HashMap<String, String>();
            args.put("text", nz(m.group(1)));
            row.put("args", args);
            return row;
        }
        return null;
    }

    /** Default Business sandbox; personal only when the utterance asks for it. */
    static String waPackageFor(String low) {
        if (low != null && (low.contains("personal whatsapp") || low.contains("my whatsapp"))) {
            return "com.whatsapp";
        }
        return "com.whatsapp.w4b";
    }

    /** Channel for script/draft when not explicitly sms/mail/whatsapp. */
    static String channelForScript(String low) {
        if (low == null) {
            return "whatsapp";
        }
        if (low.contains("sms") || low.contains("text message")) {
            return "sms";
        }
        if (low.contains("email") || low.contains("mail ") || low.startsWith("mail")
                || low.contains("gmail")) {
            return "mail";
        }
        return "whatsapp";
    }

    private static String nz(String s) {
        return s == null ? "" : s.trim();
    }

    private static String argString(Map<?, ?> args, String key) {
        if (args == null) {
            return "";
        }
        Object v;
        try {
            v = args.get(key);
        } catch (Exception e) {
            return "";
        }
        if (v == null) {
            return "";
        }
        try {
            return String.valueOf(v).trim();
        } catch (Exception e) {
            return "";
        }
    }

    private static String normSpace(String s) {
        if (s == null) {
            return "";
        }
        return s.trim().replaceAll("\\s+", " ");
    }
}
