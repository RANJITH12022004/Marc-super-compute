package com.marc.island;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

/**
 * MuseStore key-vault mask store (no Android imports; java.lang/java.util only).
 *
 * <p>On device, the real API key lives in EncryptedSharedPreferences and only
 * the masked view is ever shown. This class models the same contract over a
 * plain {@link Map} so it stays unit-testable with no secrets checked in.
 *
 * <p>No real secrets are stored here. The mask never contains the plaintext.
 *
 * <p>Mirrors apps/bee-android/muse_store.py.
 */
public final class MuseStore {

    /** Ellipsis used in masked views. */
    public static final String ELLIPSIS = "\u2026";

    /** Default model for spark. */
    public static final String SPARK_MODEL = "muse-spark-1.3";

    /** Default model for wonder. */
    public static final String WONDER_MODEL = "muse-wonder-1.0";

    /** Default model for voice. */
    public static final String VOICE_MODEL = "muse-voice-transcribe-1.0";

    /** Store field holding the real key (EncryptedSharedPreferences on device). */
    public static final String KEY_API_KEY = "api_key";

    /** Store field holding the masked view of the key. */
    public static final String KEY_MASK = "key_mask";

    private MuseStore() {
    }

    /**
     * Return a masked view of {@code key} showing only the last 4 chars.
     *
     * <p>Examples: {@code maskKey("LLM_abcdefghijk")} returns
     * {@code "LLM_\u2026hijk"}; {@code maskKey("")} and
     * {@code maskKey(null)} return {@code ""}. The mask never equals the
     * plaintext and never contains the full plaintext for long keys.
     *
     * @param key raw key, may be null
     * @return masked view, or "" for null/empty input
     */
    public static String maskKey(String key) {
        if (key == null || key.isEmpty()) {
            return "";
        }
        int n = key.length();
        if (n <= 4) {
            StringBuilder sb = new StringBuilder(n);
            for (int i = 0; i < n; i++) {
                sb.append(ELLIPSIS);
            }
            return sb.toString();
        }
        if (n <= 8) {
            return ELLIPSIS + key.substring(n - 4);
        }
        return key.substring(0, 4) + ELLIPSIS + key.substring(n - 4);
    }

    /**
     * Store {@code key} in {@code store} and record its masked view.
     *
     * <p>Rejects null/empty/blank keys with IllegalArgumentException. Stores
     * the real key under {@code "api_key"} (alias {@code "key"}) and the
     * masked view under {@code "key_mask"} (aliases {@code "mask"} /
     * {@code "masked_key"}).
     *
     * @param store mutable map acting as EncryptedSharedPreferences stand-in
     * @param key raw key, must be non-blank
     * @return the mask
     */
    public static String saveKey(Map<String, String> store, String key) {
        if (store == null) {
            throw new IllegalArgumentException("store must not be null");
        }
        if (key == null || key.trim().isEmpty()) {
            throw new IllegalArgumentException("key must be a non-empty string");
        }
        String mask = maskKey(key);
        store.put(KEY_API_KEY, key);
        store.put("key", key);
        store.put(KEY_MASK, mask);
        store.put("mask", mask);
        store.put("masked_key", mask);
        return mask;
    }

    /**
     * Return true when {@code store} holds a non-blank key.
     *
     * @param store map to inspect, may be null
     * @return true if a key is present
     */
    public static boolean hasKey(Map<String, String> store) {
        if (store == null) {
            return false;
        }
        String v = store.get(KEY_API_KEY);
        if (v != null && !v.trim().isEmpty()) {
            return true;
        }
        v = store.get("key");
        return v != null && !v.trim().isEmpty();
    }

    /**
     * Return the stored mask, or "" when absent.
     *
     * @param store map to inspect, may be null
     * @return masked view or ""
     */
    public static String getMask(Map<String, String> store) {
        if (store == null) {
            return "";
        }
        for (String field : new String[]{KEY_MASK, "mask", "masked_key"}) {
            String v = store.get(field);
            if (v != null && !v.isEmpty()) {
                return v;
            }
        }
        for (String field : new String[]{KEY_API_KEY, "key"}) {
            String v = store.get(field);
            if (v != null && !v.isEmpty()) {
                return maskKey(v);
            }
        }
        return "";
    }

    /**
     * Remove any stored key and mask from {@code store}.
     *
     * @param store mutable map, must not be null
     */
    public static void clearKey(Map<String, String> store) {
        if (store == null) {
            throw new IllegalArgumentException("store must not be null");
        }
        store.remove(KEY_API_KEY);
        store.remove("key");
        store.remove(KEY_MASK);
        store.remove("mask");
        store.remove("masked_key");
    }

    /**
     * Return default model names for spark/wonder/voice.
     *
     * @return unmodifiable map with spark/wonder/voice entries
     */
    public static Map<String, String> defaultModels() {
        Map<String, String> m = new HashMap<String, String>();
        m.put("spark", SPARK_MODEL);
        m.put("wonder", WONDER_MODEL);
        m.put("voice", VOICE_MODEL);
        return Collections.unmodifiableMap(m);
    }

    /**
     * Needle is never enabled in this vault.
     *
     * @return always false
     */
    public static boolean needleEnabled() {
        return false;
    }
}
