package com.bee.island;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.Intent;
import android.provider.Settings;
import android.text.TextUtils;
import android.view.accessibility.AccessibilityEvent;

/** Accessibility host that lets the pill use TYPE_ACCESSIBILITY_OVERLAY. */
public class IslandAccess extends AccessibilityService {

    static boolean isEnabled(Context context) {
        if (context == null) {
            return false;
        }
        String enabled = Settings.Secure.getString(
                context.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (TextUtils.isEmpty(enabled)) {
            return false;
        }
        String needle = context.getPackageName() + "/" + IslandAccess.class.getName();
        String shortNeedle = context.getPackageName() + "/.IslandAccess";
        for (String piece : enabled.split(":")) {
            if (needle.equalsIgnoreCase(piece) || shortNeedle.equalsIgnoreCase(piece)) {
                return true;
            }
            if (piece != null && piece.contains(context.getPackageName())) {
                return true;
            }
        }
        return false;
    }
    @Override
    public void onServiceConnected() {
        IslandService.bindHost(this);
    }

    @Override
    public boolean onUnbind(Intent intent) {
        IslandService.bindHost(null);
        return super.onUnbind(intent);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
    }

    @Override
    public void onInterrupt() {
    }
}
