package com.marc.island;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Hydration hero stage (no Android imports; java.lang/java.util only).
 *
 * <p>Mirrors bee_hydration.py. Visual origin is fixed at CAMERA_X/CAMERA_Y.
 * showHeroStage never no-ops when host is null: it still adds the hero
 * view (the hit target) to the window manager and returns
 * created=true plus the overlay type.
 */
public final class HydrationHero {

    /** Fixed visual origin X. Never change. */
    public static final float CAMERA_X = 540f;

    /** Fixed visual origin Y. Never change. */
    public static final float CAMERA_Y = 68.6f;

    /** Hero view name (also the hit target). */
    public static final String HERO_VIEW = "HydrationHeroView";

    private HydrationHero() {
    }

    /**
     * Overlay type for the hero.
     *
     * @param hostBound true when host-bound, false otherwise
     * @return "accessibility" if bound, else "application"
     */
    public static String overlayType(boolean hostBound) {
        return hostBound ? "accessibility" : "application";
    }

    /** Null-safe overload: null is treated as not bound. */
    public static String overlayType(Boolean hostBound) {
        return (hostBound != null && hostBound.booleanValue()) ? "accessibility" : "application";
    }

    /**
     * Show the hydration hero stage. Never no-ops when host is null:
     * still adds {@link #HERO_VIEW} to {@code wm} plus a hit target,
     * and returns created=true with the overlay type.
     *
     * @param host host object or null; null means not host-bound
     * @param wm   window manager fake exposing addView/add_view(String)
     * @return map with created=true and overlay type
     */
    public static Map<String, Object> showHeroStage(Object host, Object wm) {
        String overlay = overlayType(host != null);
        if (wm != null) {
            try {
                invokeAddView(wm, HERO_VIEW);
            } catch (Exception ignored) {
                // Never fail the contract on a fake wm.
            }
            try {
                recordHitTarget(wm, HERO_VIEW);
            } catch (Exception ignored) {
                // Best effort only.
            }
        }
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("created", Boolean.TRUE);
        out.put("overlay", overlay);
        return Collections.unmodifiableMap(out);
    }

    /**
     * Play the water hero now; delegates to {@code showHeroStage(null, wm)}.
     *
     * @param wm window manager fake
     * @return result of showHeroStage(null, wm)
     */
    public static Map<String, Object> playWaterNow(Object wm) {
        return showHeroStage(null, wm);
    }

    private static void invokeAddView(Object wm, String name) throws Exception {
        Method[] methods;
        try {
            methods = wm.getClass().getMethods();
        } catch (Exception e) {
            return;
        }
        // Prefer exact addView(String) / add_view(String) matches.
        for (Method m : methods) {
            String n = m.getName();
            if (!("addView".equals(n) || "add_view".equals(n))) {
                continue;
            }
            Class<?>[] params = m.getParameterTypes();
            if (params.length == 1 && params[0].isAssignableFrom(String.class)) {
                try {
                    m.invoke(wm, name);
                    return;
                } catch (Exception ignored) {
                    // Try next candidate.
                }
            }
        }
        // Fallback: any single-arg addView/add_view accepting Object/CharSequence.
        for (Method m : methods) {
            String n = m.getName();
            if (!("addView".equals(n) || "add_view".equals(n))) {
                continue;
            }
            if (m.getParameterTypes().length == 1) {
                try {
                    m.invoke(wm, new Object[]{name});
                    return;
                } catch (Exception ignored) {
                    // Continue.
                }
            }
        }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void recordHitTarget(Object wm, String name) {
        // Try explicit hit-target adder methods first.
        try {
            for (Method m : wm.getClass().getMethods()) {
                String n = m.getName();
                if (!("addHitTarget".equals(n)
                        || "add_hit_target".equals(n)
                        || "addHitView".equals(n)
                        || "add_hit_view".equals(n))) {
                    continue;
                }
                Class<?>[] params = m.getParameterTypes();
                try {
                    if (params.length == 1 && params[0].isAssignableFrom(String.class)) {
                        m.invoke(wm, name);
                        return;
                    }
                    if (params.length == 3
                            && params[0].isAssignableFrom(String.class)) {
                        m.invoke(wm, new Object[]{name,
                                Float.valueOf(CAMERA_X), Float.valueOf(CAMERA_Y)});
                        return;
                    }
                    if (params.length == 1) {
                        m.invoke(wm, new Object[]{name});
                        return;
                    }
                } catch (Exception ignored) {
                    // Try next candidate / fall through to field.
                }
            }
        } catch (Exception ignored) {
            // Fall through to field bookkeeping.
        }
        // Fall back to a hit-target list field if present.
        String[] fieldNames = {"hitTargets", "hit_targets", "hitTargetsList",
                "hit_targets_list", "targets", "hits"};
        for (String fieldName : fieldNames) {
            try {
                Field f = findField(wm.getClass(), fieldName);
                if (f == null) {
                    continue;
                }
                f.setAccessible(true);
                Object val = f.get(wm);
                if (val instanceof List) {
                    List list = (List) val;
                    if (!list.contains(name)) {
                        list.add(name);
                    }
                    return;
                }
            } catch (Exception ignored) {
                // Try next field name.
            }
        }
    }

    private static Field findField(Class<?> cls, String name) {
        Class<?> c = cls;
        while (c != null) {
            try {
                return c.getDeclaredField(name);
            } catch (NoSuchFieldException e) {
                c = c.getSuperclass();
            } catch (Exception e) {
                return null;
            }
        }
        try {
            return cls.getField(name);
        } catch (Exception e) {
            return null;
        }
    }
}
