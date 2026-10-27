package com.bee.island;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Static pending tool-step queue (no Android imports).
 *
 * <p>Confirm-before-act staging: tools NEVER auto-run from here.
 * This class only stores copies and never dispatches anything.
 */
public final class PendingPlan {

    /** Frozen visual origin X. Unused by queue logic; do not use. */
    public static final float CAMERA_X = 540f;

    /** Frozen visual origin Y. Unused by queue logic; do not use. */
    public static final float CAMERA_Y = 68.6f;

    private static final int MAX_PROMPT = 40;

    private static final Object LOCK = new Object();
    private static final List<Map<String, Object>> PENDING =
            new ArrayList<Map<String, Object>>();
    private static String currentPrompt = "";

    private PendingPlan() {
    }

    /**
     * Stage a copy of {@code steps} with {@code prompt} clamped to 40 chars.
     *
     * @param steps tool steps, may be null (treated as empty)
     * @param prompt this-or-that line, may be null (treated as "")
     */
    public static void set(List<Map<String, Object>> steps, String prompt) {
        synchronized (LOCK) {
            PENDING.clear();
            if (steps != null) {
                for (Map<String, Object> step : steps) {
                    if (step == null) {
                        continue;
                    }
                    PENDING.add(copyStep(step));
                }
            }
            currentPrompt = clampPrompt(prompt);
        }
    }

    /**
     * Return a copy of the staged steps (empty list if none).
     *
     * @return defensive copy, never null
     */
    public static List<Map<String, Object>> get() {
        synchronized (LOCK) {
            List<Map<String, Object>> out =
                    new ArrayList<Map<String, Object>>(PENDING.size());
            for (Map<String, Object> step : PENDING) {
                if (step == null) {
                    continue;
                }
                out.add(copyStep(step));
            }
            return out;
        }
    }

    /**
     * Return the current this-or-that line, or "" when none.
     *
     * @return clamped prompt, never null
     */
    public static String prompt() {
        synchronized (LOCK) {
            return currentPrompt;
        }
    }

    /**
     * Return true when no steps are staged.
     *
     * @return true if empty
     */
    public static boolean isEmpty() {
        synchronized (LOCK) {
            return PENDING.isEmpty();
        }
    }

    /**
     * Return true when at least one step is staged.
     *
     * @return true if pending
     */
    public static boolean hasPending() {
        synchronized (LOCK) {
            return !PENDING.isEmpty();
        }
    }

    /** Drop the staged queue and prompt. */
    public static void clear() {
        synchronized (LOCK) {
            PENDING.clear();
            currentPrompt = "";
        }
    }

    private static String clampPrompt(String value) {
        if (value == null) {
            return "";
        }
        String s = value.trim().replaceAll("\\s+", " ");
        if (s.length() > MAX_PROMPT) {
            return s.substring(0, MAX_PROMPT);
        }
        return s;
    }

    private static Map<String, Object> copyStep(Map<String, Object> src) {
        Map<String, Object> dst = new HashMap<String, Object>(src.size());
        for (Map.Entry<String, Object> e : src.entrySet()) {
            Object v = e.getValue();
            if (v instanceof Map) {
                Map<?, ?> m = (Map<?, ?>) v;
                Map<Object, Object> c = new HashMap<Object, Object>(m.size());
                c.putAll(m);
                dst.put(e.getKey(), c);
            } else if (v instanceof List) {
                List<?> l = (List<?>) v;
                dst.put(e.getKey(), new ArrayList<Object>(l));
            } else {
                dst.put(e.getKey(), v);
            }
        }
        return dst;
    }
}
