package com.bee.island;

import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * IslandTouch pure touch contract (no Android imports; java.lang/java.util only).
 *
 * <p>Visual pill origin is fixed at CAMERA_X/CAMERA_Y. Hit area expands by
 * HIT_SLOP_DP on every side without moving the visual origin constants.
 */
public final class IslandTouch {

    /** Fixed visual pill origin X (dp). Never change. */
    public static final float CAMERA_X = 540f;

    /** Fixed visual pill origin Y (dp). Never change. */
    public static final float CAMERA_Y = 68.6f;

    /** Compact idle pill width (dp). */
    public static final float IDLE_W_DP = 126f;

    /** Listening morph pill width (dp). */
    public static final float LISTEN_W_DP = 168f;

    /** Touch slop expansion applied on each side (dp). */
    public static final int HIT_SLOP_DP = 24;

    /** Listening tap debounce window (ms). */
    public static final int LISTEN_TIMEOUT_MS = 20000;

    /** Hold-to-open threshold (ms). */
    public static final int HOLD_MS = 2000;

    /** Tap ignore window after listen starts (ms). */
    public static final int TAP_IGNORE_MS = 300;

    private IslandTouch() {
    }

    /**
     * Overlay type for the pill.
     *
     * @param a11yBound true when bound via accessibility, false for application overlay
     * @return "accessibility" if bound, else "application"
     */
    public static String overlayType(boolean a11yBound) {
        return a11yBound ? "accessibility" : "application";
    }

    /** Null-safe overload: null is treated as not bound. */
    public static String overlayType(Boolean a11yBound) {
        return (a11yBound != null && a11yBound.booleanValue()) ? "accessibility" : "application";
    }

    /**
     * Window flags for the pill. The pill always receives taps, so the result
     * never includes "not_touchable" (any casing).
     *
     * @param screenOn true to keep screen on, false otherwise
     * @return unmodifiable set of flag tokens; always contains "touchable" and "show_when_locked"
     */
    public static Set<String> windowFlags(boolean screenOn) {
        Set<String> flags = new LinkedHashSet<String>();
        flags.add("touchable");
        flags.add("not_focusable");
        flags.add("layout_in_screen");
        flags.add("watch_outside_touch");
        flags.add("show_when_locked");
        if (screenOn) {
            flags.add("keep_screen_on");
        }
        return Collections.unmodifiableSet(flags);
    }

    /** No-arg overload defaults to screenOn=false. */
    public static Set<String> windowFlags() {
        return windowFlags(false);
    }

    /**
     * Convenience mirror of the Python {@code window_flags_touchable} contract:
     * the pill is always touchable.
     */
    public static boolean windowFlagsTouchable(boolean screenOn) {
        return true;
    }

    /** No-arg overload: always true. */
    public static boolean windowFlagsTouchable() {
        return true;
    }

    /** Gesture onDown: always consumes (returns true). */
    public static boolean onDown() {
        return true;
    }

    /** Gesture onDown with coordinates: always true. */
    public static boolean onDown(float x, float y) {
        return true;
    }

    /** Gesture onDown with state hints: always true. */
    public static boolean onDown(boolean listening, boolean confirming) {
        return true;
    }

    /**
     * Tap dispatch.
     *
     * <ul>
     *   <li>if confirming return "confirm" (tap = yes)</li>
     *   <li>else if listening and age &lt; TAP_IGNORE_MS return "ignore"</li>
     *   <li>else if listening and age &gt;= TAP_IGNORE_MS return "restart_listen"</li>
     *   <li>else return "start_listen"</li>
     * </ul>
     */
    public static String onTap(boolean listening, boolean confirming, long listeningAgeMs) {
        if (confirming) {
            return "confirm";
        }
        if (listening) {
            if (listeningAgeMs < (long) TAP_IGNORE_MS) {
                return "ignore";
            }
            return "restart_listen";
        }
        return "start_listen";
    }

    /** Int overload delegates to the long version. */
    public static String onTap(boolean listening, boolean confirming, int listeningAgeMs) {
        return onTap(listening, confirming, (long) listeningAgeMs);
    }

    /** No-age overload defaults age to 0. */
    public static String onTap(boolean listening, boolean confirming) {
        return onTap(listening, confirming, 0L);
    }

    /**
     * Hold dispatch.
     *
     * <ul>
     *   <li>if confirming return "cancel"</li>
     *   <li>else return "open_app"</li>
     * </ul>
     */
    public static String onHold(boolean listening, boolean confirming) {
        if (confirming) {
            return "cancel";
        }
        return "open_app";
    }

    /**
     * Expanded hit box for the pill.
     *
     * <p>Expands by HIT_SLOP_DP on every side:
     * left = cameraX - slop, top = cameraY - slop,
     * right = cameraX + pillW + slop, bottom = cameraY + pillH + slop.
     * The visual origin constants CAMERA_X/CAMERA_Y are never mutated.
     *
     * @return float array {left, top, right, bottom}
     */
    public static float[] hitBox(float cameraX, float cameraY, float pillW, float pillH) {
        float slop = (float) HIT_SLOP_DP;
        float left = cameraX - slop;
        float top = cameraY - slop;
        float right = cameraX + pillW + slop;
        float bottom = cameraY + pillH + slop;
        return new float[]{left, top, right, bottom};
    }

    /** Double overload delegates to the float version. */
    public static float[] hitBox(double cameraX, double cameraY, double pillW, double pillH) {
        return hitBox((float) cameraX, (float) cameraY, (float) pillW, (float) pillH);
    }

    /**
     * Named view of {@link #hitBox(float, float, float, float)}.
     *
     * @return map with left/top/right/bottom, visual x/y origin (== cameraX/cameraY),
     *         and expanded width/height (pill + 2*slop)
     */
    public static java.util.Map<String, Float> hitBoxMap(float cameraX, float cameraY, float pillW, float pillH) {
        float[] b = hitBox(cameraX, cameraY, pillW, pillH);
        float width = b[2] - b[0];
        float height = b[3] - b[1];
        java.util.Map<String, Float> m = new java.util.LinkedHashMap<String, Float>();
        m.put("left", Float.valueOf(b[0]));
        m.put("top", Float.valueOf(b[1]));
        m.put("right", Float.valueOf(b[2]));
        m.put("bottom", Float.valueOf(b[3]));
        m.put("x", Float.valueOf(cameraX));
        m.put("y", Float.valueOf(cameraY));
        m.put("originX", Float.valueOf(cameraX));
        m.put("originY", Float.valueOf(cameraY));
        m.put("width", Float.valueOf(width));
        m.put("height", Float.valueOf(height));
        return Collections.unmodifiableMap(m);
    }

    /**
     * Punch-hole window layout. Visual center stays on the camera even when
     * the window clamps to the screen top (never Gravity-center the visual).
     *
     * @return float array {winX, winY, winW, winH, visualLeft, visualTop, centerX, centerY}
     */
    public static float[] pillWindow(float cameraX, float cameraY, float visualW, float visualH, float slopPx) {
        float halfW = visualW / 2f;
        float halfH = visualH / 2f;
        float winX = Math.max(0f, cameraX - halfW - slopPx);
        float above = cameraY - halfH;
        float winY = (above >= slopPx) ? (cameraY - halfH - slopPx) : 0f;
        float visualLeft = cameraX - winX - halfW;
        float visualTop = cameraY - winY - halfH;
        float winW = visualLeft + visualW + slopPx;
        float winH = visualTop + visualH + slopPx;
        float centerX = cameraX;
        float centerY = cameraY;
        return new float[]{winX, winY, winW, winH, visualLeft, visualTop, centerX, centerY};
    }
}
