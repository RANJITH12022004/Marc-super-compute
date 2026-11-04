package com.bee.island;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Fuzzy contact / chat-row matching (edit distance + token score).
 * No Android imports — pure scoring.
 */
public final class ContactMatch {

    public static final double DEFAULT_THRESHOLD = 0.55;

    private ContactMatch() {
    }

    public static final class Hit {
        public final String label;
        public final double score;

        public Hit(String label, double score) {
            this.label = label == null ? "" : label;
            this.score = score;
        }
    }

    public static int editDistance(String a, String b) {
        String x = a == null ? "" : a.toLowerCase(Locale.US);
        String y = b == null ? "" : b.toLowerCase(Locale.US);
        int n = x.length();
        int m = y.length();
        if (n == 0) {
            return m;
        }
        if (m == 0) {
            return n;
        }
        int[] prev = new int[m + 1];
        int[] cur = new int[m + 1];
        for (int j = 0; j <= m; j++) {
            prev[j] = j;
        }
        for (int i = 1; i <= n; i++) {
            cur[0] = i;
            char cx = x.charAt(i - 1);
            for (int j = 1; j <= m; j++) {
                int cost = cx == y.charAt(j - 1) ? 0 : 1;
                int del = prev[j] + 1;
                int ins = cur[j - 1] + 1;
                int sub = prev[j - 1] + cost;
                cur[j] = Math.min(del, Math.min(ins, sub));
            }
            int[] tmp = prev;
            prev = cur;
            cur = tmp;
        }
        return prev[m];
    }

    /** Score in 0..1 (1 = perfect). */
    public static double score(String want, String candidate) {
        if (want == null || candidate == null) {
            return 0;
        }
        String w = want.trim().toLowerCase(Locale.US);
        String c = candidate.trim().toLowerCase(Locale.US);
        if (w.isEmpty() || c.isEmpty()) {
            return 0;
        }
        if (w.equals(c)) {
            return 1.0;
        }
        // Prefer first token of chat rows like "Rahul · hello"
        String cFirst = c.split("[·\\-|,]")[0].trim();
        if (cFirst.isEmpty()) {
            cFirst = c;
        }
        if (w.equals(cFirst)) {
            return 0.98;
        }
        if (cFirst.startsWith(w) || w.startsWith(cFirst)) {
            return 0.9;
        }
        if (c.contains(w) || w.contains(cFirst)) {
            return 0.75;
        }
        int maxLen = Math.max(w.length(), cFirst.length());
        if (maxLen <= 0) {
            return 0;
        }
        double dist = editDistance(w, cFirst);
        double sim = 1.0 - (dist / (double) maxLen);
        // Token overlap bonus
        String[] wt = w.split("\\s+");
        String[] ct = cFirst.split("\\s+");
        int hits = 0;
        for (int i = 0; i < wt.length; i++) {
            for (int j = 0; j < ct.length; j++) {
                if (wt[i].equals(ct[j]) || editDistance(wt[i], ct[j]) <= 1) {
                    hits++;
                    break;
                }
            }
        }
        if (wt.length > 0 && hits > 0) {
            sim = Math.max(sim, 0.5 + 0.4 * ((double) hits / (double) wt.length));
        }
        if (sim < 0) {
            return 0;
        }
        if (sim > 1) {
            return 1;
        }
        return sim;
    }

    public static Hit bestMatch(String want, List<String> candidates, double threshold) {
        if (candidates == null || candidates.isEmpty()) {
            return null;
        }
        double th = threshold <= 0 ? DEFAULT_THRESHOLD : threshold;
        Hit best = null;
        for (int i = 0; i < candidates.size(); i++) {
            String label = candidates.get(i);
            if (label == null || label.trim().isEmpty()) {
                continue;
            }
            double s = score(want, label);
            if (s < th) {
                continue;
            }
            if (best == null || s > best.score) {
                best = new Hit(label.trim(), s);
            }
        }
        return best;
    }

    public static List<String> uniqueLabels(List<String> raw) {
        List<String> out = new ArrayList<String>();
        if (raw == null) {
            return out;
        }
        for (int i = 0; i < raw.size(); i++) {
            String s = raw.get(i);
            if (s == null) {
                continue;
            }
            s = s.trim();
            if (s.isEmpty()) {
                continue;
            }
            boolean seen = false;
            for (int j = 0; j < out.size(); j++) {
                if (out.get(j).equalsIgnoreCase(s)) {
                    seen = true;
                    break;
                }
            }
            if (!seen) {
                out.add(s);
            }
        }
        return out;
    }
}
