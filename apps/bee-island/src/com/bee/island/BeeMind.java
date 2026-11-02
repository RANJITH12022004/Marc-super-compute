package com.bee.island;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
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
        if (low.contains("whoami") || low.contains("who am i")) {
            return true;
        }
        if (low.contains("where am i")) {
            return true;
        }
        if (low.contains("what do you know about me") || low.contains("know about me")) {
            return true;
        }
        if (low.contains("what will you do") || low.contains("what are you doing")) {
            return true;
        }
        if (low.contains("what was i doing") || low.contains("what am i doing")) {
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

    /** Prefer short spoken lines from markdown soul text. */
    static String speakable(String raw) {
        if (raw == null) {
            return "";
        }
        String s = raw.trim();
        if (s.isEmpty()) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        String[] lines = s.split("\n");
        for (int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            if (line.isEmpty() || line.startsWith("#") || line.startsWith("---")) {
                continue;
            }
            if (line.startsWith("- ")) {
                line = line.substring(2).trim();
            }
            line = line.replaceAll("\\[\\[([^\\]]+)\\]\\]", "$1");
            line = line.replaceAll("</?b>", "");
            if (line.isEmpty()) {
                continue;
            }
            if (out.length() > 0) {
                out.append(" ");
            }
            out.append(line);
            if (out.length() > 280) {
                break;
            }
        }
        String spoken = out.toString().trim();
        if (spoken.isEmpty()) {
            spoken = s.replaceAll("#+", " ").replaceAll("\\s+", " ").trim();
        }
        if (spoken.length() > CONTEXT_MAX) {
            spoken = spoken.substring(0, CONTEXT_MAX);
        }
        return spoken;
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

    /** Record a failure: POST to Rox as note title 'failed', else append FAILED.md. */
    public static String recordFail(Context context, String body) {
        String b = body == null ? "" : body.trim();
        if (b.isEmpty()) {
            return "";
        }
        boolean sent = false;
        try {
            if (context != null && RoxClient.reachable(context)) {
                sent = RoxClient.postNote(context, "failed", b);
            }
        } catch (Exception ignored) {
            sent = false;
        }
        if (!sent) {
            try {
                appendCache(context, "FAILED.md", b + "\n");
            } catch (Exception ignored) {
            }
        }
        return "Noted.";
    }

    /** Record success: refresh NOW.md via /mind when online, else cache given text. */
    public static String recordOk(Context context, String body) {
        String b = body == null ? "" : body.trim();
        try {
            if (context != null && RoxClient.reachable(context)) {
                String fresh = RoxClient.getMind(context, "now");
                if (fresh != null && !fresh.trim().isEmpty()) {
                    String clean = fresh.trim();
                    writeCache(context, "NOW.md", clean);
                    return clean;
                }
            }
        } catch (Exception ignored) {
        }
        if (!b.isEmpty()) {
            try {
                writeCache(context, "NOW.md", b);
            } catch (Exception ignored) {
            }
            return b;
        }
        return readCache(context, "NOW.md");
    }

    public static String recordOk(Context context) {
        return recordOk(context, "");
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
        String failed = readCache(context, "FAILED.md");
        if (me == null) {
            me = "";
        }
        if (now == null) {
            now = "";
        }
        if (failed == null) {
            failed = "";
        }
        me = stripSecretLines(me).trim().replaceAll("\\s+", " ");
        now = stripSecretLines(now).trim().replaceAll("\\s+", " ");
        String failedTail = lastFiveLines(stripSecretLines(failed).trim());
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
        if (!failedTail.isEmpty()) {
            if (sb.length() > 0) {
                sb.append("\n");
            }
            sb.append(failedTail);
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
        boolean identity = low.contains("whoami") || low.contains("who am i")
                || low.contains("where am i")
                || low.contains("what do you know about me")
                || low.contains("know about me");
        boolean doing = low.contains("what will you do")
                || low.contains("what are you doing")
                || low.contains("what was i doing")
                || low.contains("what am i doing")
                || low.matches("(?s).*\\bwhat\\b.*\\bdoing\\b.*");
        if (identity) {
            String me = whoAmI(context);
            if (me == null) {
                me = "";
            }
            me = speakable(me);
            if (me.isEmpty() && RoxClient.reachable(context)) {
                try {
                    String mind = RoxClient.getMind(context, text);
                    me = speakable(mind);
                } catch (Exception ignored) {
                    me = "";
                }
            }
            if (me.isEmpty()) {
                // Let AskRouter leftover hit Muse /utterance (RAG-first).
                return false;
            }
            AskRouter.speak(context, me);
            return true;
        }
        if (doing) {
            String now = whatWasIDoing(context);
            if (now == null) {
                now = "";
            }
            now = speakable(now);
            if (now.isEmpty() && RoxClient.reachable(context)) {
                try {
                    String mind = RoxClient.getMind(context, text);
                    now = speakable(mind);
                } catch (Exception ignored) {
                    now = "";
                }
            }
            if (now.isEmpty()) {
                return false;
            }
            AskRouter.speak(context, now);
            return true;
        }
        if (!low.matches("(?s).*\\bremember\\b.*") && !low.matches("(?s).*\\bnote\\b.*")) {
            return false;
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

    private static String stripSecretLines(String text) {
        if (text == null || text.isEmpty()) {
            return "";
        }
        String[] lines = text.split("\n", -1);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < lines.length; i++) {
            String line = lines[i];
            String low = line.toLowerCase(Locale.US);
            if (low.contains("authorization")) {
                continue;
            }
            if (low.matches("(?s).*api[\\s_\\-]*keys?.*")) {
                continue;
            }
            if (sb.length() > 0) {
                sb.append("\n");
            }
            sb.append(line);
        }
        return sb.toString();
    }

    public static int failedCount(Context context) {
        String failed = stripSecretLines(readCache(context, "FAILED.md"));
        if (failed == null || failed.trim().isEmpty()) {
            return 0;
        }
        int n = 0;
        String[] lines = failed.split("\n");
        for (int i = 0; i < lines.length; i++) {
            if (lines[i] != null && !lines[i].trim().isEmpty()) {
                n++;
            }
        }
        return n;
    }

    private static String lastFiveLines(String text) {
        if (text == null) {
            return "";
        }
        String trimmed = text.trim();
        if (trimmed.isEmpty()) {
            return "";
        }
        String[] lines = trimmed.split("\n");
        List<String> kept = new ArrayList<String>();
        for (int i = 0; i < lines.length; i++) {
            String l = lines[i] == null ? "" : lines[i].trim();
            if (l.isEmpty()) {
                continue;
            }
            kept.add(lines[i].trim());
        }
        if (kept.isEmpty()) {
            return "";
        }
        int from = kept.size() > 5 ? kept.size() - 5 : 0;
        StringBuilder sb = new StringBuilder();
        for (int i = from; i < kept.size(); i++) {
            if (sb.length() > 0) {
                sb.append("\n");
            }
            sb.append(kept.get(i));
        }
        String out = sb.toString().replaceAll("\\s+", " ");
        return out.trim();
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
