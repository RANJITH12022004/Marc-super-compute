package com.bee.island;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Device recall against Rox plus local cache in filesDir/bee_mind. */
public class BeeMind {

    private static final int CONTEXT_MAX = 800;

    private BeeMind() {
    }

    public static boolean isMind(String text) {
        if (text == null) {
            return false;
        }
        String low = text.toLowerCase(Locale.US);
        if (low.contains("whoami")) {
            return true;
        }
        if (low.contains("who am i")) {
            return true;
        }
        if (low.contains("what was i doing")) {
            return true;
        }
        if (low.contains("what am i doing")) {
            return true;
        }
        if (low.matches("(?s).*\\bwhat\\b.*\\bdoing\\b.*")) {
            return true;
        }
        if (low.matches("(?s).*\\bremember\\b.*")) {
            return true;
        }
        if (low.matches("(?s).*\\bnote\\b.*")) {
            return true;
        }
        return false;
    }

    public static String whoAmI(Context context) {
        String cached = readCache(context, "ME.md");
        try {
            if (context != null && RoxClient.reachable(context)) {
                String body = RoxClient.getWhoami(context);
                if (body != null && !body.trim().isEmpty()) {
                    String clean = body.trim();
                    writeCache(context, "ME.md", clean);
                    return clean;
                }
            }
        } catch (Exception ignored) {
        }
        return cached == null ? "" : cached;
    }

    public static String whatWasIDoing(Context context) {
        String cached = readCache(context, "NOW.md");
        try {
            if (context != null && RoxClient.reachable(context)) {
                String body = RoxClient.getMind(context, "now");
                if (body != null && !body.trim().isEmpty()) {
                    String clean = body.trim();
                    writeCache(context, "NOW.md", clean);
                    return clean;
                }
            }
        } catch (Exception ignored) {
        }
        return cached == null ? "" : cached;
    }

    public static String note(Context context, String title, String body) {
        String t = title == null ? "" : title;
        String b = body == null ? "" : body;
        String entry = ("# " + t + "\n" + b + "\n").trim() + "\n";
        boolean sent = false;
        try {
            if (context != null && RoxClient.reachable(context)) {
                sent = RoxClient.postNote(context, t, b);
            }
        } catch (Exception ignored) {
            sent = false;
        }
        if (!sent) {
            try {
                appendCache(context, "NOTES.md", entry);
            } catch (Exception ignored) {
            }
        }
        return "Noted.";
    }

    public static String note(Context context, String body) {
        String b = body == null ? "" : body;
        String t = "note";
        String low = b.toLowerCase(Locale.US).trim();
        String[] prefixes = new String[]{
                "remember that ", "remember to ", "remember ",
                "note that ", "note to ", "note "
        };
        for (String p : prefixes) {
            if (low.startsWith(p)) {
                b = b.trim().substring(p.length()).trim();
                break;
            }
        }
        if (b.isEmpty()) {
            b = body == null ? "" : body;
        }
        return note(context, t, b);
    }

    public static String injectContext(Context context) {
        try {
            whoAmI(context);
        } catch (Exception ignored) {
        }
        try {
            whatWasIDoing(context);
        } catch (Exception ignored) {
        }
        String me = readCache(context, "ME.md");
        String now = readCache(context, "NOW.md");
        if (me == null) {
            me = "";
        }
        if (now == null) {
            now = "";
        }
        me = me.trim().replaceAll("\\s+", " ");
        now = now.trim().replaceAll("\\s+", " ");
        StringBuilder sb = new StringBuilder();
        if (!me.isEmpty()) {
            sb.append(me);
        }
        if (!now.isEmpty()) {
            if (sb.length() > 0) {
                sb.append("\n");
            }
            sb.append(now);
        }
        String out = sb.toString().trim();
        if (out.length() > CONTEXT_MAX) {
            out = out.substring(0, CONTEXT_MAX);
        }
        return out;
    }

    public static boolean handle(Context context, String text) {
        if (text == null || !isMind(text)) {
            return false;
        }
        String low = text.toLowerCase(Locale.US);
        if (low.contains("whoami") || low.contains("who am i")) {
            String me = whoAmI(context);
            if (me == null) {
                me = "";
            }
            me = me.trim();
            if (me.isEmpty()) {
                me = "Unknown.";
            }
            if (me.length() > CONTEXT_MAX) {
                me = me.substring(0, CONTEXT_MAX);
            }
            AskRouter.speak(context, me);
            return true;
        }
        if (low.matches("(?s).*\\bwhat\\b.*\\bdoing\\b.*")) {
            String now = whatWasIDoing(context);
            if (now == null) {
                now = "";
            }
            now = now.trim();
            if (now.isEmpty()) {
                now = "Unknown.";
            }
            if (now.length() > CONTEXT_MAX) {
                now = now.substring(0, CONTEXT_MAX);
            }
            AskRouter.speak(context, now);
            return true;
        }
        String body = text.trim();
        String lowBody = body.toLowerCase(Locale.US);
        String[] prefixes = new String[]{
                "remember that ", "remember to ", "remember ",
                "note that ", "note to ", "note "
        };
        for (String p : prefixes) {
            if (lowBody.startsWith(p)) {
                body = body.substring(p.length()).trim();
                break;
            }
        }
        if (body.isEmpty()) {
            body = text.trim();
        }
        note(context, "note", body);
        AskRouter.speak(context, "Noted.");
        return true;
    }

    private static File mindDir(Context context) {
        File base = null;
        try {
            base = context.getFilesDir();
        } catch (Exception ignored) {
            base = null;
        }
        if (base == null) {
            return null;
        }
        return new File(base, "bee_mind");
    }

    private static String readCache(Context context, String name) {
        if (context == null || name == null) {
            return "";
        }
        try {
            File dir = mindDir(context);
            if (dir == null) {
                return "";
            }
            File f = new File(dir, name);
            if (!f.isFile()) {
                return "";
            }
            FileInputStream in = null;
            try {
                in = new FileInputStream(f);
                return readAll(in).trim();
            } finally {
                if (in != null) {
                    try {
                        in.close();
                    } catch (Exception ignored) {
                    }
                }
            }
        } catch (Exception ignored) {
            return "";
        }
    }

    private static void writeCache(Context context, String name, String content) {
        if (context == null || name == null) {
            return;
        }
        if (content == null) {
            content = "";
        }
        try {
            File dir = mindDir(context);
            if (dir == null) {
                return;
            }
            if (!dir.isDirectory() && !dir.mkdirs()) {
                if (!dir.isDirectory()) {
                    return;
                }
            }
            File f = new File(dir, name);
            FileOutputStream out = null;
            try {
                out = new FileOutputStream(f, false);
                out.write(content.getBytes(StandardCharsets.UTF_8));
                out.flush();
            } finally {
                if (out != null) {
                    try {
                        out.close();
                    } catch (Exception ignored) {
                    }
                }
            }
        } catch (Exception ignored) {
        }
    }

    private static void appendCache(Context context, String name, String content) {
        if (context == null || name == null) {
            return;
        }
        if (content == null) {
            content = "";
        }
        try {
            File dir = mindDir(context);
            if (dir == null) {
                return;
            }
            if (!dir.isDirectory() && !dir.mkdirs()) {
                if (!dir.isDirectory()) {
                    return;
                }
            }
            File f = new File(dir, name);
            FileOutputStream out = null;
            try {
                out = new FileOutputStream(f, true);
                out.write(content.getBytes(StandardCharsets.UTF_8));
                out.flush();
            } finally {
                if (out != null) {
                    try {
                        out.close();
                    } catch (Exception ignored) {
                    }
                }
            }
        } catch (Exception ignored) {
        }
    }

    private static String readAll(InputStream in) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) != -1) {
            bos.write(buf, 0, n);
        }
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }
}
