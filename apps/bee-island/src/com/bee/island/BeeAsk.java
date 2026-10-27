package com.bee.island;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
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

    private static final Pattern CLAUSE_SPLIT = Pattern.compile(
            "\\s*;\\s*"
                    + "|\\s*,?\\s*\\bafter\\s+that\\b\\s*,?\\s*"
                    + "|\\s*,?\\s*\\band\\s+then\\b\\s*,?\\s*"
                    + "|\\s*,?\\s*\\bthen\\b\\s*,?\\s*"
                    + "|\\s*(?:,\\s*(?:and\\s+)?|\\band\\b\\s+)"
                    + "(?=(?:text|whatsapp|play|email|mail|call|dial|open)\\b)",
            Pattern.CASE_INSENSITIVE);

    private BeeAsk() {
    }

    public static boolean needleEnabled() {
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
            return "Planning…";
        }
        if ("confirm".equals(state)) {
            return "Say yes or cancel.";
        }
        if ("done".equals(state)) {
            return "Done.";
        }
        if ("fail".equals(state)) {
            return "Failed.";
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
        if (low.matches("(?s).*\\bdemo\\b.*")) {
            return false;
        }
        if (low.contains("email") || low.contains("whatsapp")) {
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
        String stripped = low.trim();
        if (stripped.startsWith("type ")) {
            return true;
        }
        if (stripped.matches("open\\s+spotify\\b.*")) {
            return true;
        }
        return low.contains("youtube");
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

    public static String classifyVoice(String text) {
        String low = text == null ? "" : text.toLowerCase(Locale.US);
        if (low.contains("reboot")
                || low.contains("shutdown")
                || low.contains("sudo")
                || low.contains("poweroff")
                || low.contains("rm -rf")) {
            return "refuse";
        }
        if (low.matches("(?s).*\\bsend\\s+it\\b.*")) {
            return "confirm";
        }
        if (low.matches("(?s).*\\b(yes|yeah|yep|okay)\\b.*")) {
            return "confirm";
        }
        if (low.matches("(?s).*\\bok\\b.*")) {
            return "confirm";
        }
        if (low.matches("(?s).*\\bdo\\s+it\\b.*")) {
            return "confirm";
        }
        if (low.matches("(?s).*\\bgo\\s+ahead\\b.*")) {
            return "confirm";
        }
        String strippedThat = low.trim().replaceAll("^[?.!\\s]+|[?.!\\s]+$", "").trim();
        if ("that".equals(strippedThat)) {
            return "confirm";
        }
        if (low.matches("(?s).*\\b(nope|cancel|stop|no)\\b.*")) {
            return "cancel";
        }
        return "ask";
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
                label = to.isEmpty() ? "send text" : ("text " + to).trim();
            } else if ("mail_compose".equals(t)) {
                String to = normSpace(argString(args, "to"));
                label = to.isEmpty() ? "send email" : ("email " + to).trim();
            } else if ("dial".equals(t)) {
                String to = normSpace(argString(args, "to"));
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
            action = hasPending ? "ask" : "ack";
        } else {
            action = hasPending ? "ask" : "ack";
        }
        Map<String, Object> out = new HashMap<String, Object>();
        out.put("action", action);
        return out;
    }

    public static List<Map<String, Object>> splitUtterance(String text) {
        List<Map<String, Object>> steps = new ArrayList<Map<String, Object>>();
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
            out.put("steps", steps);
            out.put("model", "local_fast");
            out.put("kind", "local_fast");
            return out;
        }
        List<Map<String, Object>> dag = splitUtterance(text);
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
        for (Map<String, Object> step : steps) {
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
            }
        }
        return results;
    }

    static Map<String, Object> clauseToTool(String clause) {
        if (clause == null) {
            clause = "";
        }
        String low = clause.toLowerCase(Locale.US);
        String device = low.contains("on my laptop") ? "laptop" : "phone";
        String cleaned = clause.replaceAll("(?i)\\bon\\s+my\\s+laptop\\b", " ").trim();
        Map<String, Object> row = new HashMap<String, Object>();
        row.put("device", device);
        Matcher m;
        m = Pattern.compile("(?i)^\\s*(?:text|whatsapp)\\s+(\\S+)(?:\\s+(.*))?$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "whatsapp_send");
            Map<String, String> args = new HashMap<String, String>();
            args.put("to", nz(m.group(1)));
            args.put("text", m.group(2) == null ? "" : m.group(2).trim());
            row.put("args", args);
            return row;
        }
        m = Pattern.compile("(?i)^\\s*play\\b\\s*(.*)$").matcher(cleaned);
        if (m.find()) {
            row.put("tool", "play_music");
            Map<String, String> args = new HashMap<String, String>();
            args.put("query", nz(m.group(1)));
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
            row.put("tool", "open_app");
            Map<String, String> args = new HashMap<String, String>();
            args.put("app", nz(m.group(1)));
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
