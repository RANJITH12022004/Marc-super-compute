package com.bee.island;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** Foreground packages that must hide the Dynamic Island (payments / banks). */
public final class PaymentGate {

    private static final Set<String> PACKAGES = new HashSet<String>(Arrays.asList(
            "com.dreamplug.androidapp",
            "com.google.android.apps.nbu.paisa.user",
            "net.one97.paytm",
            "com.phonepe.app",
            "com.sbi.lotusintouch",
            "com.snapwork.hdfc",
            "com.csam.icici.bank.imobile",
            "com.axis.mobile",
            "com.bankofbaroda.neobanking",
            "com.upi.axispay",
            "com.fss.pnbpsp",
            "com.enstage.wibmo.hdfc"
    ));

    private static volatile boolean hidden;

    private PaymentGate() {
    }

    public static boolean isPayment(String pkg) {
        if (pkg == null || pkg.trim().isEmpty()) {
            return false;
        }
        String p = pkg.trim().toLowerCase(Locale.US);
        if (PACKAGES.contains(p)) {
            return true;
        }
        if (p.contains("paytm") || p.contains("phonepe") || p.contains("paisa")
                || p.contains("bhim") || p.contains("upi") && p.contains("bank")) {
            return true;
        }
        return false;
    }

    public static void setHidden(boolean value) {
        hidden = value;
    }

    public static boolean isHidden() {
        return hidden;
    }
}
