package com.bee.island;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.util.Log;

/**
 * Thin diagnose path via Termux when installed. Never arbitrary shell;
 * never reboot/shutdown. Primary phone control remains Accessibility.
 */
final class TermuxBridge {
    private static final String TAG = "BeeIsland";
    private static final String TERMUX = "com.termux";
    private static final String RUN = "com.termux.RUN_COMMAND";
    private static final String SERVICE = "com.termux.app.RunCommandService";

    private TermuxBridge() {
    }

    static boolean installed(Context context) {
        if (context == null) {
            return false;
        }
        try {
            context.getPackageManager().getPackageInfo(TERMUX, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Fire allowlisted diagnose commands. Returns a short note for replan context
     * (best-effort; Termux may not echo stdout back to Bee).
     */
    static String diagnose(Context context, String hint) {
        if (!installed(context)) {
            return "";
        }
        String h = hint == null ? "" : hint.toLowerCase(java.util.Locale.US);
        if (h.contains("reboot") || h.contains("shutdown") || h.contains("rm ")
                || h.contains("format") || h.contains("dd ")) {
            return "";
        }
        // Allowlist only — logcat slice + accessibility dump.
        fire(context, new String[]{"/data/data/com.termux/files/usr/bin/logcat", "-d", "-t", "80"});
        fire(context, new String[]{"/system/bin/dumpsys", "accessibility"});
        return "termux:diagnosed";
    }

    private static void fire(Context context, String[] cmd) {
        if (context == null || cmd == null || cmd.length == 0) {
            return;
        }
        try {
            Intent i = new Intent();
            i.setClassName(TERMUX, SERVICE);
            i.setAction(RUN);
            i.putExtra("com.termux.RUN_COMMAND_PATH", cmd[0]);
            if (cmd.length > 1) {
                String[] args = new String[cmd.length - 1];
                System.arraycopy(cmd, 1, args, 0, args.length);
                i.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", args);
            }
            i.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
            i.putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0");
            context.startService(i);
        } catch (Exception e) {
            Log.w(TAG, "Termux diagnose skipped", e);
        }
    }
}
