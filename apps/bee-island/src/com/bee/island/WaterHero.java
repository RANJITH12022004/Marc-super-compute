package com.bee.island;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Jointed water-hero contract (no Android). Mirrors water_hero.py. */
public final class WaterHero {

    public static final float CAMERA_X = 540f;
    public static final float CAMERA_Y = 68.6f;
    public static final String HERO_VIEW = "WaterHeroView";
    public static final long HOUR_MS = 3600000L;
    public static final boolean PLAY_ON_OPEN = false;
    public static final String FALLBACK = "water_courier";

    private WaterHero() {
    }

    public static String overlayType(boolean hostBound) {
        return hostBound ? "accessibility" : "application";
    }

    public static String hitOverlayType(boolean hostBound) {
        return overlayType(hostBound);
    }

    public static float clampJoint(String name, float angle) {
        float lo;
        float hi;
        if ("shoulder".equals(name)) {
            lo = -50f;
            hi = 50f;
        } else if ("elbow".equals(name)) {
            lo = 15f;
            hi = 145f;
        } else if ("hip".equals(name)) {
            lo = -25f;
            hi = 35f;
        } else if ("knee".equals(name)) {
            lo = 5f;
            hi = 140f;
        } else {
            return angle;
        }
        if (angle < lo) {
            return lo;
        }
        if (angle > hi) {
            return hi;
        }
        return angle;
    }

    public static Map<String, Object> showHeroStage(Object host, Object wm) {
        String overlay = overlayType(host != null);
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("created", Boolean.TRUE);
        out.put("overlay", overlay);
        return Collections.unmodifiableMap(out);
    }

    public static long nextDelayMs(boolean seen, long lastMs, long nowMs) {
        if (!seen) {
            return HOUR_MS;
        }
        long remaining = (lastMs + HOUR_MS) - nowMs;
        return remaining <= 0 ? 0L : remaining;
    }
}
