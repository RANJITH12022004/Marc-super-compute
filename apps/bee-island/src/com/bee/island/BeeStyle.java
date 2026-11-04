package com.bee.island;

import android.content.Context;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * On-device personal-tone drafts from bee_mind/style cards (seeded assets).
 */
final class BeeStyle {
    private BeeStyle() {
    }

    static String slug(String name) {
        if (name == null) {
            return "untitled";
        }
        String s = name.trim().toLowerCase(Locale.US);
        s = s.replaceAll("[^a-z0-9]+", "_").replaceAll("^_+|_+$", "");
        if (s.isEmpty()) {
            return "untitled";
        }
        if (s.length() > 40) {
            s = s.substring(0, 40);
        }
        return s;
    }

    static String loadCard(Context context, String person, String channel) {
        BeeMind.ensureSeeded(context);
        String ch = channel == null || channel.isEmpty() ? "whatsapp" : channel.trim().toLowerCase(Locale.US);
        String sl = slug(person);
        String[] paths = new String[]{
                "style/" + ch + "/" + sl + ".md",
                "style/whatsapp/" + sl + ".md",
                "style/general/" + sl + ".md"
        };
        for (int i = 0; i < paths.length; i++) {
            String body = readMindFile(context, paths[i]);
            if (body != null && !body.trim().isEmpty()) {
                return body.trim();
            }
        }
        return "";
    }

    /**
     * Draft a short body in the user's voice to *person* about *topic*.
     */
    static String draftLikeMe(Context context, String person, String topic) {
        return draftLikeMe(context, person, topic, "whatsapp");
    }

    static String draftLikeMe(Context context, String person, String topic, String channel) {
        String intent = topic == null ? "" : topic.trim();
        if (intent.isEmpty()) {
            intent = "checking in";
        }
        String ch = channel == null || channel.isEmpty() ? "whatsapp" : channel.trim().toLowerCase(Locale.US);
        if ("email".equals(ch) || "gmail".equals(ch)) {
            ch = "mail";
        }
        String card = loadCard(context, person, ch);
        if (card.isEmpty() && !"whatsapp".equals(ch)) {
            card = loadCard(context, person, "whatsapp");
        }
        String greet = hint(card, "Greetings");
        String examples = hint(card, "Examples");
        if (examples.isEmpty()) {
            examples = hint(card, "Example");
        }
        String formality = hint(card, "Formality");
        String lang = hint(card, "Language");
        if (greet.isEmpty() || greet.equalsIgnoreCase("none observed")
                || greet.equalsIgnoreCase("none")) {
            greet = "mail".equals(ch) ? "Hello" : "Hi";
        } else {
            // Take first greeting token.
            int cut = greet.indexOf(',');
            if (cut > 0) {
                greet = greet.substring(0, cut);
            }
            greet = greet.replaceAll("\\s*\\(\\d+\\)\\s*$", "").trim();
            if (greet.isEmpty()) {
                greet = "mail".equals(ch) ? "Hello" : "Hi";
            }
        }
        String core = rewriteTopic(intent, formality, lang, examples);
        String body;
        if ("mail".equals(ch)) {
            body = greet + ",\n\n" + core + "\n\nBest regards,\nRanjith";
        } else {
            body = greet + "! " + core;
        }
        int cap = "mail".equals(ch) ? 400 : 220;
        if (body.length() > cap) {
            body = body.substring(0, cap - 1).replaceAll("\\s+$", "") + "…";
        }
        return body;
    }

    private static String rewriteTopic(String intent, String formality, String lang,
                                       String examples) {
        String low = intent.toLowerCase(Locale.US);
        // Strip planner wrappers.
        low = low.replaceFirst("^(regarding|about|re|saying|that)\\s+", "");
        String core = intent.trim();
        if (core.toLowerCase(Locale.US).startsWith("regarding ")
                || core.toLowerCase(Locale.US).startsWith("about ")) {
            int sp = core.indexOf(' ');
            if (sp > 0) {
                core = core.substring(sp + 1).trim();
            }
        }
        // Casual WA voice for friends / Tamil mix cards.
        boolean casual = formality.toLowerCase(Locale.US).contains("casual")
                || formality.toLowerCase(Locale.US).contains("informal")
                || lang.toLowerCase(Locale.US).contains("tamil")
                || lang.toLowerCase(Locale.US).contains("telugu")
                || lang.toLowerCase(Locale.US).contains("mixed");
        if (casual) {
            if (low.contains("late") || low.contains("running late")
                    || low.contains("i'll be late") || low.contains("i will be late")) {
                return "I'll be late, on the way.";
            }
            if (low.contains("coming") || low.contains("on the way")) {
                return "On the way!";
            }
            if (low.contains("call") && low.contains("later")) {
                return "Can I call you later?";
            }
        }
        // Prefer a short example line shape if present.
        if (examples != null && !examples.isEmpty() && examples.length() < 120
                && !examples.equalsIgnoreCase("none observed")) {
            // Keep intent content; examples only influence tone via greet/casual.
        }
        // Default: capitalize first letter, drop trailing period spam.
        if (core.isEmpty()) {
            return "Just checking in.";
        }
        char c0 = core.charAt(0);
        if (Character.isLowerCase(c0)) {
            core = Character.toUpperCase(c0) + core.substring(1);
        }
        return core;
    }

    private static String hint(String card, String heading) {
        if (card == null || card.isEmpty() || heading == null) {
            return "";
        }
        String[] lines = card.split("\n");
        String want = heading.toLowerCase(Locale.US);
        for (int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            String low = line.toLowerCase(Locale.US);
            if (low.startsWith("- " + want + ":") || low.startsWith(want + ":")
                    || low.startsWith("**" + want.toLowerCase(Locale.US))) {
                int colon = line.indexOf(':');
                if (colon >= 0 && colon + 1 < line.length()) {
                    return line.substring(colon + 1).trim();
                }
            }
            if (low.equals("## " + want) || low.equals("# " + want)
                    || low.startsWith("## " + want)) {
                if (i + 1 < lines.length) {
                    return lines[i + 1].trim().replaceFirst("^[-*]\\s*", "");
                }
            }
        }
        return "";
    }

    private static String readMindFile(Context context, String rel) {
        if (context == null || rel == null) {
            return "";
        }
        try {
            File f = new File(new File(context.getFilesDir(), "bee_mind"), rel);
            if (f.isFile()) {
                FileInputStream in = new FileInputStream(f);
                try {
                    return readAll(in);
                } finally {
                    try {
                        in.close();
                    } catch (Exception ignored) {
                    }
                }
            }
        } catch (Exception ignored) {
        }
        try {
            InputStream in = context.getAssets().open("mind/" + rel);
            try {
                return readAll(in);
            } finally {
                try {
                    in.close();
                } catch (Exception ignored) {
                }
            }
        } catch (Exception ignored) {
        }
        return "";
    }

    private static String readAll(InputStream in) throws java.io.IOException {
        java.io.ByteArrayOutputStream bos = new java.io.ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) != -1) {
            bos.write(buf, 0, n);
        }
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }
}
