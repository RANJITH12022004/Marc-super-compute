package com.bee.island;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * MODEL_API_KEY lives in Android Keystore AES-GCM + SharedPreferences.
 * Never logs the Bearer token. Needle stays off.
 */
final class KeyVault {
    private static final String PREFS = "bee_vault";
    private static final String ALIAS = "bee_muse_key";
    private static final String CIPHER_PREF = "api_key_blob";
    private static final String IV_PREF = "api_key_iv";
    private static final String MASK_PREF = "api_key_mask";
    private static final String SPARK_PREF = "spark";
    private static final String WONDER_PREF = "wonder";
    private static final String VOICE_PREF = "voice";
    private static final String MODE_PREF = "mode";

    private KeyVault() {
    }

    static String mask(String key) {
        return MuseStore.maskKey(key);
    }

    static boolean hasKey(Context context) {
        String k = loadKey(context);
        return k != null && !k.trim().isEmpty();
    }

    static String maskOrEmpty(Context context) {
        SharedPreferences p = prefs(context);
        String mask = p.getString(MASK_PREF, "");
        return mask == null ? "" : mask;
    }

    static void saveKey(Context context, String key) {
        if (key == null || key.trim().isEmpty()) {
            throw new IllegalArgumentException("key");
        }
        byte[] iv;
        byte[] sealed;
        try {
            SecretKey secret = getOrCreateKey();
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, secret);
            iv = cipher.getIV();
            sealed = cipher.doFinal(key.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("keystore");
        }
        prefs(context).edit()
                .putString(CIPHER_PREF, Base64.encodeToString(sealed, Base64.NO_WRAP))
                .putString(IV_PREF, Base64.encodeToString(iv, Base64.NO_WRAP))
                .putString(MASK_PREF, MuseStore.maskKey(key))
                .apply();
    }

    static String loadKey(Context context) {
        SharedPreferences p = prefs(context);
        String blob = p.getString(CIPHER_PREF, "");
        String ivB64 = p.getString(IV_PREF, "");
        if (blob == null || blob.isEmpty() || ivB64 == null || ivB64.isEmpty()) {
            return "";
        }
        try {
            SecretKey secret = getOrCreateKey();
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            byte[] iv = Base64.decode(ivB64, Base64.NO_WRAP);
            cipher.init(Cipher.DECRYPT_MODE, secret, new GCMParameterSpec(128, iv));
            byte[] plain = cipher.doFinal(Base64.decode(blob, Base64.NO_WRAP));
            return new String(plain, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        }
    }

    static String spark(Context context) {
        return prefs(context).getString(SPARK_PREF, MuseStore.SPARK_MODEL);
    }

    static String wonder(Context context) {
        return prefs(context).getString(WONDER_PREF, MuseStore.WONDER_MODEL);
    }

    static String voice(Context context) {
        return prefs(context).getString(VOICE_PREF, MuseStore.VOICE_MODEL);
    }

    static boolean sandbox(Context context) {
        return !"live".equals(prefs(context).getString(MODE_PREF, "sandbox"));
    }

    static void saveModels(Context context, String spark, String wonder, String voice, String mode) {
        prefs(context).edit()
                .putString(SPARK_PREF, spark == null || spark.isEmpty() ? MuseStore.SPARK_MODEL : spark)
                .putString(WONDER_PREF, wonder == null || wonder.isEmpty() ? MuseStore.WONDER_MODEL : wonder)
                .putString(VOICE_PREF, voice == null || voice.isEmpty() ? MuseStore.VOICE_MODEL : voice)
                .putString(MODE_PREF, mode == null || mode.isEmpty() ? "sandbox" : mode)
                .apply();
    }

    static boolean needleEnabled() {
        return false;
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static SecretKey getOrCreateKey() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(ALIAS)) {
            return ((KeyStore.SecretKeyEntry) ks.getEntry(ALIAS, null)).getSecretKey();
        }
        KeyGenerator gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        gen.init(new KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build());
        return gen.generateKey();
    }
}
