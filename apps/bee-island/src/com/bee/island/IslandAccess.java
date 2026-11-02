package com.bee.island;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Context;
import android.content.Intent;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Accessibility host that lets the pill use TYPE_ACCESSIBILITY_OVERLAY. */
public class IslandAccess extends AccessibilityService {

    private static WeakReference<IslandAccess> self;

    private View pill;

    static boolean typeFocused(String text) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null || text == null) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        AccessibilityNodeInfo focused = findEditable(root);
        if (focused == null) {
            try {
                root.recycle();
            } catch (Exception ignored) {
            }
            return false;
        }
        boolean wasFocused = false;
        try {
            wasFocused = focused.isFocused() || focused.isAccessibilityFocused();
        } catch (Exception ignored) {
            wasFocused = false;
        }
        if (!wasFocused) {
            try {
                focused.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            } catch (Exception ignored) {
            }
            try {
                Thread.sleep(200);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            } catch (Exception ignored) {
            }
        }
        Bundle extras = new Bundle();
        extras.putCharSequence(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        boolean ok = false;
        try {
            ok = focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, extras);
        } catch (Exception ignored) {
            ok = false;
        }
        try {
            focused.recycle();
        } catch (Exception ignored) {
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    static boolean clickText(String text) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null || text == null) {
            return false;
        }
        String want = text.trim().toLowerCase(Locale.US);
        if (want.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        AccessibilityNodeInfo hit = null;
        try {
            hit = findNodeForText(root, want);
        } catch (Exception ignored) {
            hit = null;
        }
        if (hit == null) {
            try {
                root.recycle();
            } catch (Exception ignored) {
            }
            return false;
        }
        boolean ok = clickClickableAncestor(hit);
        try {
            hit.recycle();
        } catch (Exception ignored) {
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    static boolean clickLabel(String text) {
        return clickText(text);
    }

    static boolean typeViewId(String id, String text) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null || id == null || text == null) {
            return false;
        }
        String want = id.trim();
        if (want.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        List<AccessibilityNodeInfo> nodes = null;
        try {
            nodes = root.findAccessibilityNodeInfosByViewId(want);
        } catch (Exception ignored) {
            nodes = null;
        }
        if (nodes == null || nodes.isEmpty()) {
            try {
                root.recycle();
            } catch (Exception ignored) {
            }
            return false;
        }
        boolean ok = false;
        for (int i = 0; i < nodes.size(); i++) {
            AccessibilityNodeInfo n = null;
            try {
                n = nodes.get(i);
            } catch (Exception ignored) {
                n = null;
            }
            if (n == null) {
                continue;
            }
            if (!ok) {
                Bundle extras = new Bundle();
                extras.putCharSequence(
                        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
                try {
                    ok = n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, extras);
                } catch (Exception ignored) {
                    ok = false;
                }
            }
            try {
                n.recycle();
            } catch (Exception ignored) {
            }
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    static boolean clickViewId(String id) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null || id == null) {
            return false;
        }
        String want = id.trim();
        if (want.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        List<AccessibilityNodeInfo> nodes = null;
        try {
            nodes = root.findAccessibilityNodeInfosByViewId(want);
        } catch (Exception ignored) {
            nodes = null;
        }
        if (nodes == null || nodes.isEmpty()) {
            if (nodes != null) {
                for (int i = 0; i < nodes.size(); i++) {
                    AccessibilityNodeInfo n = null;
                    try {
                        n = nodes.get(i);
                    } catch (Exception ignored) {
                        n = null;
                    }
                    if (n != null) {
                        try {
                            n.recycle();
                        } catch (Exception ignored) {
                        }
                    }
                }
            }
            try {
                root.recycle();
            } catch (Exception ignored) {
            }
            return false;
        }
        boolean ok = false;
        for (int i = 0; i < nodes.size(); i++) {
            AccessibilityNodeInfo n = null;
            try {
                n = nodes.get(i);
            } catch (Exception ignored) {
                n = null;
            }
            if (n == null) {
                continue;
            }
            boolean clicked = false;
            try {
                boolean clickable = false;
                try {
                    clickable = n.isClickable();
                } catch (Exception ignored) {
                    clickable = false;
                }
                if (clickable) {
                    try {
                        clicked = n.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    } catch (Exception ignored) {
                        clicked = false;
                    }
                } else {
                    clicked = clickClickableAncestor(n);
                }
                if (!clicked) {
                    clicked = tapNodeCenter(n);
                }
            } catch (Exception ignored) {
                clicked = false;
            }
            try {
                n.recycle();
            } catch (Exception ignored) {
            }
            if (clicked) {
                ok = true;
                for (int j = i + 1; j < nodes.size(); j++) {
                    try {
                        AccessibilityNodeInfo rest = nodes.get(j);
                        if (rest != null) {
                            try {
                                rest.recycle();
                            } catch (Exception ignored) {
                            }
                        }
                    } catch (Exception ignored) {
                    }
                }
                break;
            }
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    static String focusedEditText() {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return "";
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return "";
        }
        if (root == null) {
            return "";
        }
        AccessibilityNodeInfo focused = null;
        try {
            focused = findEditable(root);
        } catch (Exception ignored) {
            focused = null;
        }
        if (focused == null) {
            try {
                root.recycle();
            } catch (Exception ignored) {
            }
            return "";
        }
        String out = "";
        try {
            CharSequence t = focused.getText();
            out = t == null ? "" : String.valueOf(t);
        } catch (Exception ignored) {
            out = "";
        }
        try {
            focused.recycle();
        } catch (Exception ignored) {
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return out == null ? "" : out;
    }

    static boolean clickSendControl() {
        if (clickViewId("com.whatsapp:id/send")) {
            return true;
        }
        if (clickViewId("com.whatsapp.w4b:id/send")) {
            return true;
        }
        return clickTextExactPrefer("Send");
    }

    static boolean clickTextExactPrefer(String text) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null || text == null) {
            return false;
        }
        String want = text.trim().toLowerCase(Locale.US);
        if (want.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        AccessibilityNodeInfo hit = null;
        try {
            hit = findNodeExact(root, want);
            if (hit == null) {
                hit = findNodeForText(root, want);
            }
        } catch (Exception ignored) {
            hit = null;
        }
        if (hit == null) {
            try {
                root.recycle();
            } catch (Exception ignored) {
            }
            return false;
        }
        String shown = nodeLabel(hit).toLowerCase(Locale.US);
        boolean ok = false;
        if (shown.contains(want)) {
            ok = clickClickableAncestor(hit);
        }
        try {
            hit.recycle();
        } catch (Exception ignored) {
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    static String foregroundPackage() {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return "";
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return "";
        }
        if (root == null) {
            return "";
        }
        String pkg = "";
        try {
            CharSequence p = root.getPackageName();
            pkg = p == null ? "" : String.valueOf(p);
        } catch (Exception ignored) {
            pkg = "";
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return pkg;
    }

    private static boolean isSearchOrEdit(AccessibilityNodeInfo node) {
        if (node == null) {
            return true;
        }
        try {
            if (node.isEditable()) {
                return true;
            }
        } catch (Exception ignored) {
        }
        try {
            CharSequence cn = node.getClassName();
            String c = cn == null ? "" : String.valueOf(cn).toLowerCase(Locale.US);
            if (c.contains("edittext") || c.contains("searchview")
                    || c.contains("autocompletetextview")) {
                return true;
            }
        } catch (Exception ignored) {
        }
        String lab = nodeLabel(node).toLowerCase(Locale.US);
        if (lab.equals("search") || lab.startsWith("search ")) {
            return true;
        }
        return false;
    }

    static boolean clickChatRow(String name) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null || name == null) {
            return false;
        }
        String want = name.trim().toLowerCase(Locale.US);
        if (want.isEmpty()) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        AccessibilityNodeInfo hit = findChatRow(root, want, true);
        if (hit == null) {
            hit = findChatRow(root, want, false);
        }
        boolean ok = false;
        if (hit != null) {
            ok = clickClickableAncestor(hit);
            try {
                hit.recycle();
            } catch (Exception ignored) {
            }
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    private static AccessibilityNodeInfo findChatRow(AccessibilityNodeInfo node, String want) {
        return findChatRow(node, want, false);
    }

    private static AccessibilityNodeInfo findChatRow(AccessibilityNodeInfo node, String want,
                                                     boolean skipYou) {
        if (node == null || want == null) {
            return null;
        }
        try {
            String label = nodeLabel(node).toLowerCase(Locale.US);
            if (label.contains(want) && !isSearchOrEdit(node)
                    && !label.contains("from ~") && !label.startsWith("from ")
                    && (!skipYou || !label.contains("(you)"))) {
                return AccessibilityNodeInfo.obtain(node);
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo hit = findChatRow(child, want, skipYou);
            if (hit != null) {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
                return hit;
            }
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    static boolean clickFirstResultRow() {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        AccessibilityNodeInfo hit = findFirstResultRow(root, 0);
        boolean ok = false;
        if (hit != null) {
            try {
                ok = hit.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            } catch (Exception ignored) {
                ok = false;
            }
            if (!ok) {
                ok = clickClickableAncestor(hit);
            }
            try {
                hit.recycle();
            } catch (Exception ignored) {
            }
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return ok;
    }

    private static AccessibilityNodeInfo findFirstResultRow(AccessibilityNodeInfo node, int depth) {
        if (node == null || depth > 24) {
            return null;
        }
        try {
            boolean clickable = false;
            try {
                clickable = node.isClickable();
            } catch (Exception ignored) {
            }
            String lab = nodeLabel(node).toLowerCase(Locale.US);
            if (clickable && !isSearchOrEdit(node) && !isResultChrome(lab)
                    && isVideoSized(node)) {
                return AccessibilityNodeInfo.obtain(node);
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo hit = findFirstResultRow(child, depth + 1);
            if (hit != null) {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
                return hit;
            }
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    private static boolean isResultChrome(String lab) {
        if (lab == null) {
            return true;
        }
        String s = lab.trim().toLowerCase(Locale.US);
        if (s.isEmpty()) {
            return false;
        }
        if (s.equals("search") || s.equals("shuffle") || s.equals("home")
                || s.equals("cancel") || s.equals("back") || s.equals("shorts")
                || s.equals("subscriptions") || s.equals("library")
                || s.equals("you") || s.equals("create") || s.equals("cast")
                || s.equals("notifications") || s.equals("notification")
                || s.equals("account") || s.equals("all") || s.equals("premium")
                || s.equals("explore") || s.equals("menu") || s.equals("more")
                || s.equals("unwatched") || s.equals("videos")
                || s.equals("recently uploaded") || s.equals("filters")) {
            return true;
        }
        if (s.contains("notification") || s.contains("google account")
                || s.contains("voice search") || s.contains("continue watching")
                || s.contains("cast to") || s.contains("play all")) {
            return true;
        }
        return false;
    }

    private static boolean isVideoSized(AccessibilityNodeInfo node) {
        if (node == null) {
            return false;
        }
        try {
            Rect r = new Rect();
            node.getBoundsInScreen(r);
            int h = r.height();
            int w = r.width();
            if (w > 2 * h && h < 200) {
                return false;
            }
            return r.top > 160 && r.top < 1400 && h > 120 && w > 200;
        } catch (Exception ignored) {
            return false;
        }
    }

    static boolean hasText(String text) {
        if (text == null || text.trim().isEmpty()) {
            return false;
        }
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        boolean found = false;
        try {
            found = findNodeForText(root, text.trim().toLowerCase(Locale.US)) != null;
        } catch (Exception ignored) {
            found = false;
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return found;
    }

    static boolean waitFor(String pkgNeedle, String label, long timeoutMs) {
        long cap = timeoutMs <= 0L ? 8000L : timeoutMs;
        long start = System.currentTimeMillis();
        String pkgWant = pkgNeedle == null ? "" : pkgNeedle.trim().toLowerCase(Locale.US);
        String labWant = label == null ? "" : label.trim();
        while (System.currentTimeMillis() - start < cap) {
            boolean pkgOk = true;
            if (!pkgWant.isEmpty()) {
                String fg = foregroundPackage();
                pkgOk = fg != null && fg.toLowerCase(Locale.US).contains(pkgWant);
            }
            boolean labOk = true;
            if (!labWant.isEmpty()) {
                labOk = hasText(labWant);
                if (!labOk) {
                    List<String> labs = clickableLabels();
                    String want = labWant.toLowerCase(Locale.US);
                    for (int i = 0; i < labs.size(); i++) {
                        String row = labs.get(i);
                        if (row != null && row.toLowerCase(Locale.US).contains(want)) {
                            labOk = true;
                            break;
                        }
                    }
                }
            }
            if (pkgOk && labOk) {
                return true;
            }
            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }

    static boolean isSelectedLabel(String text) {
        if (text == null || text.trim().isEmpty()) {
            return false;
        }
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return false;
        }
        if (root == null) {
            return false;
        }
        boolean selected = false;
        try {
            selected = findSelectedLabel(root, text.trim().toLowerCase(Locale.US));
        } catch (Exception ignored) {
            selected = false;
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return selected;
    }

    static String nodeDump() {
        List<String> labs = clickableLabels();
        StringBuilder b = new StringBuilder();
        int n = labs.size();
        if (n > 30) {
            n = 30;
        }
        for (int i = 0; i < n; i++) {
            if (i > 0) {
                b.append("|");
            }
            String row = labs.get(i);
            b.append(row == null ? "" : row);
        }
        String dump = b.toString();
        Log.i("bee", dump);
        return dump;
    }

    /** Visible text dump for one-shot Settings/profile snapshot (not continuous scrape). */
    static String visibleTextDump() {
        List<String> labs = new ArrayList<String>();
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return "";
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return "";
        }
        if (root == null) {
            return "";
        }
        try {
            collectVisibleText(root, labs);
        } catch (Exception ignored) {
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        StringBuilder b = new StringBuilder();
        int n = labs.size();
        if (n > 120) {
            n = 120;
        }
        for (int i = 0; i < n; i++) {
            if (i > 0) {
                b.append("\n");
            }
            b.append(labs.get(i));
        }
        return b.toString();
    }

    private static void collectVisibleText(AccessibilityNodeInfo node, List<String> out) {
        if (node == null || out == null || out.size() >= 120) {
            return;
        }
        try {
            boolean visible = false;
            try {
                visible = node.isVisibleToUser();
            } catch (Exception ignored) {
                visible = false;
            }
            if (visible) {
                String label = null;
                try {
                    CharSequence t = node.getText();
                    if (t != null) {
                        label = t.toString().trim();
                    }
                } catch (Exception ignored) {
                }
                if (label == null || label.isEmpty()) {
                    try {
                        CharSequence d = node.getContentDescription();
                        if (d != null) {
                            label = d.toString().trim();
                        }
                    } catch (Exception ignored) {
                    }
                }
                if (label != null && !label.isEmpty() && label.length() < 200) {
                    if (!out.contains(label)) {
                        out.add(label);
                    }
                }
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n && out.size() < 120; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            try {
                collectVisibleText(child, out);
            } finally {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
            }
        }
    }

    private static boolean clickClickableAncestor(AccessibilityNodeInfo hit) {
        if (hit == null) {
            return false;
        }
        AccessibilityNodeInfo cur = hit;
        boolean own = false;
        try {
            for (int depth = 0; depth < 16; depth++) {
                boolean clickable = false;
                try {
                    clickable = cur.isClickable();
                } catch (Exception ignored) {
                }
                if (clickable) {
                    try {
                        return cur.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    } catch (Exception ignored) {
                        return false;
                    }
                }
                AccessibilityNodeInfo parent = null;
                try {
                    parent = cur.getParent();
                } catch (Exception ignored) {
                }
                if (own) {
                    try {
                        cur.recycle();
                    } catch (Exception ignored) {
                    }
                }
                cur = parent;
                own = true;
                if (cur == null) {
                    break;
                }
            }
            try {
                return hit.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            } catch (Exception ignored) {
                return false;
            }
        } finally {
            if (own && cur != null) {
                try {
                    cur.recycle();
                } catch (Exception ignored) {
                }
            }
        }
    }

    private static boolean findSelectedLabel(AccessibilityNodeInfo node, String want) {
        if (node == null || want == null) {
            return false;
        }
        try {
            String lab = nodeLabel(node).toLowerCase(Locale.US);
            if (lab.contains(want)) {
                boolean sel = false;
                try {
                    sel = node.isSelected() || node.isChecked();
                } catch (Exception ignored) {
                }
                if (sel) {
                    return true;
                }
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            boolean hit = findSelectedLabel(child, want);
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
            if (hit) {
                return true;
            }
        }
        return false;
    }

    static float reelProgress() {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return -1f;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return -1f;
        }
        if (root == null) {
            return -1f;
        }
        float p = scanProgress(root);
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return p;
    }

    private static float scanProgress(AccessibilityNodeInfo node) {
        if (node == null) {
            return -1f;
        }
        try {
            AccessibilityNodeInfo.RangeInfo ri = node.getRangeInfo();
            if (ri != null) {
                float max = ri.getMax();
                float cur = ri.getCurrent();
                if (max > 0f) {
                    return cur / max;
                }
            }
        } catch (Exception ignored) {
        } catch (NoSuchMethodError ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            float p = scanProgress(child);
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
            if (p >= 0f) {
                return p;
            }
        }
        return -1f;
    }

    private static AccessibilityNodeInfo findNodeForText(AccessibilityNodeInfo node, String want) {
        if (node == null || want == null) {
            return null;
        }
        try {
            CharSequence t = null;
            CharSequence d = null;
            CharSequence h = null;
            try {
                t = node.getText();
            } catch (Exception ignored) {
            }
            try {
                d = node.getContentDescription();
            } catch (Exception ignored) {
            }
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    h = node.getHintText();
                }
            } catch (Exception ignored) {
            } catch (NoSuchMethodError ignored) {
            }
            if (containsIgnoreCase(t, want)
                    || containsIgnoreCase(d, want)
                    || containsIgnoreCase(h, want)) {
                try {
                    return AccessibilityNodeInfo.obtain(node);
                } catch (Exception ignored) {
                    return null;
                }
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo hit = findNodeForText(child, want);
            if (hit != null) {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
                return hit;
            }
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    private static boolean containsIgnoreCase(CharSequence cs, String want) {
        if (cs == null || want == null || want.isEmpty()) {
            return false;
        }
        try {
            String s = cs.toString().toLowerCase(Locale.US);
            return s.contains(want);
        } catch (Exception ignored) {
            return false;
        }
    }

    private static String nodeLabel(AccessibilityNodeInfo node) {
        if (node == null) {
            return "";
        }
        try {
            CharSequence t = node.getText();
            if (t != null && t.length() > 0) {
                return String.valueOf(t);
            }
        } catch (Exception ignored) {
        }
        try {
            CharSequence d = node.getContentDescription();
            if (d != null && d.length() > 0) {
                return String.valueOf(d);
            }
        } catch (Exception ignored) {
        }
        return "";
    }

    private static AccessibilityNodeInfo findNodeExact(AccessibilityNodeInfo node, String want) {
        if (node == null || want == null) {
            return null;
        }
        try {
            String label = nodeLabel(node).trim().toLowerCase(Locale.US);
            if (label.equals(want) || label.startsWith(want + " ")) {
                return AccessibilityNodeInfo.obtain(node);
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo hit = findNodeExact(child, want);
            if (hit != null) {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
                return hit;
            }
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    private static boolean tapNodeCenter(AccessibilityNodeInfo node) {
        if (node == null) {
            return false;
        }
        try {
            Rect r = new Rect();
            node.getBoundsInScreen(r);
            if (r.width() <= 0 || r.height() <= 0) {
                return false;
            }
            IslandAccess svc = self == null ? null : self.get();
            if (svc == null) {
                return false;
            }
            int screenW = 0;
            int screenH = 0;
            try {
                WindowManager wm = (WindowManager) svc.getSystemService(WINDOW_SERVICE);
                if (wm != null) {
                    DisplayMetrics dm = new DisplayMetrics();
                    wm.getDefaultDisplay().getMetrics(dm);
                    screenW = dm.widthPixels;
                    screenH = dm.heightPixels;
                }
            } catch (Exception ignored) {
                return false;
            }
            if (screenW <= 0 || screenH <= 0) {
                return false;
            }
            return tapRatio((r.centerX() * 1f) / screenW, (r.centerY() * 1f) / screenH);
        } catch (Exception ignored) {
            return false;
        }
    }

    static boolean tapRatio(float fx, float fy) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
            return false;
        }
        int screenW = 0;
        int screenH = 0;
        try {
            WindowManager wm = (WindowManager) svc.getSystemService(WINDOW_SERVICE);
            if (wm != null) {
                DisplayMetrics dm = new DisplayMetrics();
                wm.getDefaultDisplay().getMetrics(dm);
                screenW = dm.widthPixels;
                screenH = dm.heightPixels;
            }
        } catch (Exception ignored) {
            return false;
        }
        if (screenW <= 0 || screenH <= 0) {
            return false;
        }
        float x = screenW * fx;
        float y = screenH * fy;
        try {
            Path path = new Path();
            path.moveTo(x, y);
            GestureDescription.StrokeDescription stroke =
                    new GestureDescription.StrokeDescription(path, 0, 80);
            GestureDescription gesture =
                    new GestureDescription.Builder().addStroke(stroke).build();
            return svc.dispatchGesture(gesture, null, null);
        } catch (Exception ignored) {
            return false;
        } catch (NoSuchMethodError ignored) {
            return false;
        }
    }

    static boolean swipe(String direction) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
            return false;
        }
        String dir = direction == null ? "up" : direction.trim().toLowerCase(Locale.US);
        if (dir.isEmpty()) {
            dir = "up";
        }
        int screenW = 0;
        int screenH = 0;
        try {
            WindowManager wm = (WindowManager) svc.getSystemService(WINDOW_SERVICE);
            if (wm != null) {
                DisplayMetrics dm = new DisplayMetrics();
                wm.getDefaultDisplay().getMetrics(dm);
                screenW = dm.widthPixels;
                screenH = dm.heightPixels;
            }
        } catch (Exception ignored) {
            return false;
        }
        if (screenW <= 0 || screenH <= 0) {
            return false;
        }
        float cx = screenW / 2f;
        float cy = screenH / 2f;
        float distance = Math.min(screenW, screenH) * 0.4f;
        float x1 = cx;
        float y1 = cy;
        float x2 = cx;
        float y2 = cy;
        if (dir.contains("down")) {
            y1 = cy - distance / 2f;
            y2 = cy + distance / 2f;
        } else if (dir.contains("left")) {
            x1 = cx + distance / 2f;
            x2 = cx - distance / 2f;
        } else if (dir.contains("right")) {
            x1 = cx - distance / 2f;
            x2 = cx + distance / 2f;
        } else {
            // Default direction up.
            y1 = cy + distance / 2f;
            y2 = cy - distance / 2f;
        }
        try {
            Path path = new Path();
            path.moveTo(x1, y1);
            path.lineTo(x2, y2);
            GestureDescription.StrokeDescription stroke =
                    new GestureDescription.StrokeDescription(path, 0, 250);
            GestureDescription gesture =
                    new GestureDescription.Builder().addStroke(stroke).build();
            return svc.dispatchGesture(gesture, null, null);
        } catch (Exception ignored) {
            return false;
        } catch (NoSuchMethodError ignored) {
            return false;
        }
    }

    static boolean scroll(String direction) {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        String dir = direction == null ? "" : direction.trim().toLowerCase(Locale.US);
        boolean forward = true;
        if (dir.contains("back")) {
            forward = false;
        } else if (dir.contains("up") && !dir.contains("down")) {
            // Scrolling up means going backward.
            forward = false;
        } else {
            // forward, down, empty, default all mean forward.
            forward = true;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            root = null;
        }
        if (root != null) {
            AccessibilityNodeInfo target = null;
            try {
                target = findScrollable(root);
            } catch (Exception ignored) {
                target = null;
            }
            if (target != null) {
                boolean ok = false;
                try {
                    if (forward) {
                        ok = target.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
                    } else {
                        ok = target.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);
                    }
                } catch (Exception ignored) {
                    ok = false;
                }
                try {
                    target.recycle();
                } catch (Exception ignored) {
                }
                try {
                    root.recycle();
                } catch (Exception ignored) {
                }
                if (ok) {
                    return true;
                }
                // Action failed: fall through to swipe fallback.
            } else {
                try {
                    root.recycle();
                } catch (Exception ignored) {
                }
            }
        }
        if (forward) {
            return swipe("up");
        } else {
            return swipe("down");
        }
    }

    private static AccessibilityNodeInfo findScrollable(AccessibilityNodeInfo node) {
        if (node == null) {
            return null;
        }
        try {
            boolean scrollable = false;
            try {
                scrollable = node.isScrollable();
            } catch (Exception ignored) {
                scrollable = false;
            }
            if (scrollable) {
                try {
                    return AccessibilityNodeInfo.obtain(node);
                } catch (Exception ignored) {
                    return null;
                }
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo hit = findScrollable(child);
            if (hit != null) {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
                return hit;
            }
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
        return null;
    }

    static boolean pressBack() {
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return false;
        }
        try {
            return svc.performGlobalAction(GLOBAL_ACTION_BACK);
        } catch (Exception ignored) {
            return false;
        }
    }

    static List<String> clickableLabels() {
        List<String> out = new ArrayList<String>();
        IslandAccess svc = self == null ? null : self.get();
        if (svc == null) {
            return out;
        }
        AccessibilityNodeInfo root = null;
        try {
            root = svc.getRootInActiveWindow();
        } catch (Exception ignored) {
            return out;
        }
        if (root == null) {
            return out;
        }
        try {
            collectClickable(root, out);
        } catch (Exception ignored) {
        }
        try {
            root.recycle();
        } catch (Exception ignored) {
        }
        return out;
    }

    private static void collectClickable(AccessibilityNodeInfo node, List<String> out) {
        if (node == null || out == null || out.size() >= 30) {
            return;
        }
        try {
            boolean clickable = false;
            boolean visible = false;
            try {
                clickable = node.isClickable();
            } catch (Exception ignored) {
                clickable = false;
            }
            try {
                visible = node.isVisibleToUser();
            } catch (Exception ignored) {
                visible = false;
            }
            if (clickable && visible) {
                String label = null;
                try {
                    CharSequence t = node.getText();
                    if (t != null) {
                        label = t.toString().trim();
                    }
                } catch (Exception ignored) {
                }
                if (label == null || label.isEmpty()) {
                    try {
                        CharSequence d = node.getContentDescription();
                        if (d != null) {
                            label = d.toString().trim();
                        }
                    } catch (Exception ignored) {
                    }
                }
                if (label != null && !label.isEmpty() && out.size() < 30) {
                    if (!out.contains(label)) {
                        out.add(label);
                    }
                }
                if (out.size() >= 20) {
                    return;
                }
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            if (out.size() >= 20) {
                return;
            }
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            collectClickable(child, out);
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
    }

    private static AccessibilityNodeInfo findEditable(AccessibilityNodeInfo node) {
        if (node == null) {
            return null;
        }
        try {
            if (node.isEditable() && (node.isFocused() || node.isAccessibilityFocused())) {
                return AccessibilityNodeInfo.obtain(node);
            }
        } catch (Exception ignored) {
        }
        int n = 0;
        try {
            n = node.getChildCount();
        } catch (Exception ignored) {
            n = 0;
        }
        for (int i = 0; i < n; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
            } catch (Exception ignored) {
                child = null;
            }
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo hit = findEditable(child);
            if (hit != null) {
                try {
                    child.recycle();
                } catch (Exception ignored) {
                }
                return hit;
            }
            try {
                child.recycle();
            } catch (Exception ignored) {
            }
        }
        try {
            if (node.isEditable()) {
                return AccessibilityNodeInfo.obtain(node);
            }
        } catch (Exception ignored) {
        }
        return null;
    }

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

    void showPill(View view) {
        if (view == null) {
            return;
        }
        try {
            WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            if (wm == null) {
                return;
            }
            if (pill != null && pill != view) {
                try {
                    wm.removeView(pill);
                } catch (Exception ignored) {
                }
            }
            int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                    | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                    | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                    | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED;
            int w = WindowManager.LayoutParams.WRAP_CONTENT;
            int h = WindowManager.LayoutParams.WRAP_CONTENT;
            int x = 0;
            int y = 0;
            if (view.getTag() instanceof int[]) {
                int[] box = (int[]) view.getTag();
                if (box.length >= 4) {
                    x = box[0];
                    y = box[1];
                    w = box[2];
                    h = box[3];
                }
            }
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                    w,
                    h,
                    WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                    flags,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.TOP | Gravity.START;
            lp.x = x;
            lp.y = y;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                lp.layoutInDisplayCutoutMode =
                        WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
            }
            try {
                wm.removeView(view);
            } catch (Exception ignored) {
            }
            wm.addView(view, lp);
            pill = view;
        } catch (Exception ignored) {
        }
    }

    void hidePill() {
        try {
            if (pill == null) {
                return;
            }
            try {
                WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
                if (wm != null) {
                    wm.removeView(pill);
                }
            } catch (Exception ignored) {
            }
        } finally {
            pill = null;
        }
    }

    @Override
    public void onServiceConnected() {
        self = new WeakReference<IslandAccess>(this);
        try {
            Intent i = new Intent(this, IslandService.class);
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(i);
            } else {
                startService(i);
            }
        } catch (Exception ignored) {
        }
        IslandService.bindHost(this);
        IslandService.requestPill(this);
    }

    @Override
    public boolean onUnbind(Intent intent) {
        hidePill();
        IslandService.bindHost(null);
        self = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) {
            return;
        }
        try {
            if (event.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                    && event.getEventType() != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) {
                return;
            }
        } catch (Exception ignored) {
            return;
        }
        CharSequence pkgCs = null;
        try {
            pkgCs = event.getPackageName();
        } catch (Exception ignored) {
            pkgCs = null;
        }
        String pkg = pkgCs == null ? "" : String.valueOf(pkgCs);
        if (pkg.isEmpty()) {
            try {
                pkg = foregroundPackage();
            } catch (Exception ignored) {
                pkg = "";
            }
        }
        boolean pay = PaymentGate.isPayment(pkg);
        boolean was = PaymentGate.isHidden();
        if (pay && !was) {
            PaymentGate.setHidden(true);
            hidePill();
            IslandService.onPaymentHidden(true);
        } else if (!pay && was) {
            if (pkg != null && pkg.contains("bee.island")) {
                return;
            }
            PaymentGate.setHidden(false);
            IslandService.onPaymentHidden(false);
            IslandService.requestPill(this);
        }
    }

    @Override
    public void onInterrupt() {
    }
}
