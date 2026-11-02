package com.bee.island;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Water-hero contract (no Android). Mirrors water_hero.py. */
public final class WaterHero {

    public static final float CAMERA_X = 540f;
    public static final float CAMERA_Y = 68.6f;
    public static final String HERO_VIEW = "HydrationHeroView";
    public static final String LEGACY_HERO_VIEW = "WaterHeroView";
    public static final long HOUR_MS = 3600000L;
    public static final long OFFER_MS = 12000L;
    public static final boolean PLAY_ON_OPEN = false;
    public static final String FALLBACK = "water_courier";

    public static final int BEAT_IDLE = 0;
    public static final int BEAT_PEEK = 1;
    public static final int BEAT_CLIMB = 2;
    public static final int BEAT_SWING = 3;
    public static final int BEAT_POINT = 4;
    public static final int BEAT_OFFER = 5;
    public static final int BEAT_CELEBRATE = 6;
    public static final int BEAT_SHOOT = 7;
    public static final int BEAT_RETURN = 8;

    private WaterHero() {
    }

    public static boolean isOffering(int beat) {
        return beat == BEAT_OFFER;
    }

    public static boolean isPlaying(int beat) {
        return beat != BEAT_IDLE;
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
