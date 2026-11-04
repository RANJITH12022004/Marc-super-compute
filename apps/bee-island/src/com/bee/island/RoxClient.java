package com.bee.island;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Phone talks to the public HTTPS door, never Tailscale :8096. */
final class RoxClient {
    static final String DEFAULT_DOOR = "https://marc-door.vercel.app";

    private RoxClient() {
    }

    static String baseUrl(Context context) {
        SharedPreferences p = prefs(context);
        String url = p.getString("rox_url", "").trim();
        if (url.isEmpty()) {
            url = p.getString("host", "").trim();
        }
        if (url.isEmpty()) {
            url = DEFAULT_DOOR;
        }
        if (!url.startsWith("http")) {
            url = "http://" + url;
        }
        url = url.replaceAll("/+$", "");
        if (url.startsWith("https://")) {
            return url;
        }
        String rest = url.startsWith("http://") ? url.substring("http://".length()) : url;
        int slash = rest.indexOf('/');
        String hostport = slash < 0 ? rest : rest.substring(0, slash);
        String path = slash < 0 ? "" : rest.substring(slash);
        if (!hostport.contains(":")) {
            url = "http://" + hostport + ":8096" + path;
        }
        return url;
    }

    static String authToken(Context context) {
        try {
            return prefs(context).getString("marc_token", "").trim();
        } catch (Exception e) {
            return "";
        }
    }

    static void applyAuth(HttpURLConnection conn, Context context) {
        if (conn == null) {
            return;
        }
        String t = authToken(context);
        if (t != null && !t.isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + t);
        }
    }

    static boolean reachable(Context context) {
        String base = baseUrl(context);
        if (base.isEmpty()) {
            return false;
        }
        HttpURLConnection conn = null;
        try {
            URL url = new URL(base + "/v1/health");
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(2500);
            conn.setReadTimeout(2500);
            conn.setRequestMethod("GET");
            applyAuth(conn, context);
            int code = conn.getResponseCode();
            // 5xx (e.g. door 502) must not look reachable — leftover needs on-device Muse.
            return code >= 200 && code < 400;
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    /** GET with /v1 first then bare path; always applies auth. */
    private static String getDoorText(Context context, String[] paths) {
        String base = baseUrl(context);
        if (base == null || base.isEmpty() || paths == null) {
            return "";
        }
        for (int i = 0; i < paths.length; i++) {
            String path = paths[i];
            if (path == null || path.isEmpty()) {
                continue;
            }
            HttpURLConnection conn = null;
            try {
                URL url = new URL(base + path);
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(4000);
                conn.setReadTimeout(8000);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Accept", "application/json");
                applyAuth(conn, context);
                int code = conn.getResponseCode();
                if (code < 200 || code >= 300) {
                    continue;
                }
                InputStream in = null;
                try {
                    in = conn.getInputStream();
                    if (in == null) {
                        continue;
                    }
                    String body = readAll(in);
                    String text = extractText(body);
                    if (text != null && !text.trim().isEmpty()) {
                        return text.trim();
                    }
                    if (body != null && !body.trim().isEmpty() && !body.trim().startsWith("{")) {
                        return body.trim();
                    }
                } finally {
                    if (in != null) {
                        try {
                            in.close();
                        } catch (Exception ignored) {
                        }
                    }
                }
            } catch (Exception ignored) {
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        return "";
    }

    static String getWhoami(Context context) {
        return getDoorText(context, new String[] {"/v1/whoami", "/api/v1/whoami", "/whoami"});
    }

    static String getMind(Context context, String q) {
        String query = q == null ? "" : q;
        String encoded;
        try {
            encoded = URLEncoder.encode(query, "UTF-8");
        } catch (Exception e) {
            encoded = "";
        }
        String qs = encoded.isEmpty() ? "" : ("?q=" + encoded);
        return getDoorText(context, new String[] {
                "/v1/mind" + qs,
                "/api/v1/mind" + qs,
                "/mind" + qs
        });
    }

    static boolean postNote(Context context, String title, String body) {
        try {
            String base = baseUrl(context);
            if (base == null || base.isEmpty()) {
                return false;
            }
            String t = title == null ? "" : title;
            String b = body == null ? "" : body;
            Map<String, Object> payload = new HashMap<String, Object>();
            payload.put("title", t);
            payload.put("body", b);
            String json = MuseClient.toJson(payload);
            String[] paths = new String[] {"/v1/note", "/api/v1/note", "/note"};
            for (int i = 0; i < paths.length; i++) {
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(base + paths[i]);
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setConnectTimeout(3000);
                    conn.setReadTimeout(3500);
                    conn.setRequestMethod("POST");
                    conn.setDoOutput(true);
                    conn.setRequestProperty("Content-Type", "application/json");
                    conn.setRequestProperty("Accept", "application/json");
                    applyAuth(conn, context);
                    byte[] data = json.getBytes(StandardCharsets.UTF_8);
                    OutputStream out = null;
                    try {
                        out = conn.getOutputStream();
                        out.write(data);
                        out.flush();
                    } finally {
                        if (out != null) {
                            try {
                                out.close();
                            } catch (Exception ignored) {
                            }
                        }
                    }
                    int code = conn.getResponseCode();
                    InputStream in = null;
                    try {
                        if (code >= 200 && code < 300) {
                            in = conn.getInputStream();
                        } else {
                            in = conn.getErrorStream();
                        }
                        if (in != null) {
                            byte[] buf = new byte[1024];
                            while (in.read(buf) != -1) {
                            }
                        }
                    } catch (Exception ignored) {
                    } finally {
                        if (in != null) {
                            try {
                                in.close();
                            } catch (Exception ignored) {
                            }
                        }
                    }
                    if (code >= 200 && code < 300) {
                        return true;
                    }
                } catch (Exception ignored) {
                } finally {
                    if (conn != null) {
                        conn.disconnect();
                    }
                }
            }
            return false;
        } catch (Exception e) {
            return false;
        }
    }

    static Map<String, Object> postUtterance(Context context, Map<String, Object> step) {
        Map<String, Object> result = new HashMap<String, Object>();
        result.put("id", step == null ? null : step.get("id"));
        String base = baseUrl(context);
        if (base.isEmpty()) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "laptop offline");
            return result;
        }
        String text = "";
        if (step != null) {
            Object args = step.get("args");
            if (args instanceof Map) {
                Object t = ((Map<?, ?>) args).get("text");
                if (t == null) {
                    t = ((Map<?, ?>) args).get("query");
                }
                if (t == null) {
                    t = ((Map<?, ?>) args).get("app");
                }
                text = t == null ? "" : String.valueOf(t);
            }
            if (text.isEmpty()) {
                text = String.valueOf(step.get("tool"));
            }
        }
        String body = "{\"text\":" + MuseClient.toJson(text)
                + ",\"source\":\"bee\",\"target\":\"laptop\"}";
        HttpURLConnection conn = postDoor(context, base, body, 4000, 100000);
        if (conn == null) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "laptop offline");
            return result;
        }
        try {
            int code = conn.getResponseCode();
            InputStream in = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
            if (in != null) {
                in.close();
            }
            boolean ok = code >= 200 && code < 300;
            result.put("ok", Boolean.valueOf(ok));
            if (!ok) {
                result.put("error", "laptop offline");
            }
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "laptop offline");
        } finally {
            conn.disconnect();
        }
        return result;
    }

    static Map<String, Object> postUtterance(Context context, String text) {
        Map<String, Object> result = new HashMap<String, Object>();
        result.put("ok", Boolean.FALSE);
        result.put("spoken", "");
        result.put("phone_steps", new ArrayList<Map<String, Object>>());
        String base;
        try {
            base = baseUrl(context);
        } catch (Exception e) {
            base = "";
        }
        if (base == null || base.isEmpty()) {
            result.put("error", "laptop offline");
            return result;
        }
        String t = text == null ? "" : text;
        Map<String, Object> payload = new HashMap<String, Object>();
        payload.put("text", t);
        payload.put("session_id", "phone");
        payload.put("source", "bee");
        payload.put("target", "auto");
        String json = MuseClient.toJson(payload);
        HttpURLConnection conn = postDoor(context, base, json, 8000, 100000);
        if (conn == null) {
            result.put("error", "laptop offline");
            return result;
        }
        try {
            int code = conn.getResponseCode();
            boolean ok = code >= 200 && code < 300;
            result.put("ok", Boolean.valueOf(ok));
            InputStream in = null;
            try {
                if (ok) {
                    try {
                        in = conn.getInputStream();
                    } catch (Exception ignored) {
                        in = null;
                    }
                } else {
                    try {
                        in = conn.getErrorStream();
                    } catch (Exception ignored) {
                        in = null;
                    }
                }
                String body = "";
                if (in != null) {
                    try {
                        body = readAll(in);
                    } catch (Exception ignored) {
                        body = "";
                    }
                }
                if (ok) {
                    String spoken = "";
                    List<Map<String, Object>> phoneSteps =
                            new ArrayList<Map<String, Object>>();
                    if (body != null && !body.trim().isEmpty()) {
                        try {
                            Object parsed = MuseClient.parseJson(body.trim());
                            if (parsed instanceof Map) {
                                Map<?, ?> m = (Map<?, ?>) parsed;
                                spoken = extractSpoken(m);
                                phoneSteps = extractPhoneSteps(m);
                            }
                        } catch (Exception ignored) {
                        }
                    }
                    result.put("spoken", spoken);
                    result.put("phone_steps", phoneSteps);
                } else {
                    result.put("error", "laptop offline");
                }
            } finally {
                if (in != null) {
                    try {
                        in.close();
                    } catch (Exception ignored) {
                    }
                }
            }
        } catch (Exception e) {
            result.put("ok", Boolean.FALSE);
            result.put("error", "laptop offline");
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
        return result;
    }

    private static String extractSpoken(Map<?, ?> m) {
        String[] keys = {"spoken", "reply", "text"};
        for (int i = 0; i < keys.length; i++) {
            Object v = m.get(keys[i]);
            if (v instanceof String) {
                String s = (String) v;
                if (!s.isEmpty()) {
                    return s;
                }
            }
        }
        for (int i = 0; i < keys.length; i++) {
            Object v = m.get(keys[i]);
            if (v != null && !(v instanceof String)) {
                String s = String.valueOf(v);
                if (s != null && !s.isEmpty()) {
                    return s;
                }
            }
        }
        return "";
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> extractPhoneSteps(Map<?, ?> m) {
        List<Map<String, Object>> out = new ArrayList<Map<String, Object>>();
        if (m == null) {
            return out;
        }
        Object direct = m.get("phone_steps");
        if (direct instanceof List) {
            for (Object o : (List<?>) direct) {
                if (o instanceof Map) {
                    out.add((Map<String, Object>) o);
                }
            }
            return out;
        }
        List<?> candidates = null;
        Object plan = m.get("plan");
        if (plan instanceof List) {
            candidates = (List<?>) plan;
        } else if (plan instanceof Map) {
            Object s = ((Map<?, ?>) plan).get("steps");
            if (s instanceof List) {
                candidates = (List<?>) s;
            }
        }
        if (candidates == null) {
            Object s = m.get("steps");
            if (s instanceof List) {
                candidates = (List<?>) s;
            }
        }
        if (candidates != null) {
            for (Object o : candidates) {
                if (o instanceof Map) {
                    Map<String, Object> step = (Map<String, Object>) o;
                    Object dev = step.get("device");
                    String ds = dev == null ? "" : String.valueOf(dev);
                    if ("phone".equals(ds)) {
                        out.add(step);
                    }
                }
            }
        }
        return out;
    }

    private static String readAll(InputStream in) throws java.io.IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[2048];
        int n;
        while ((n = in.read(buf)) != -1) {
            bos.write(buf, 0, n);
        }
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }

    private static String extractText(String body) {
        if (body == null) {
            return "";
        }
        String trimmed = body.trim();
        if (trimmed.isEmpty()) {
            return "";
        }
        try {
            Object parsed = MuseClient.parseJson(trimmed);
            if (parsed instanceof Map) {
                Object text = ((Map<?, ?>) parsed).get("text");
                if (text instanceof String) {
                    return (String) text;
                }
            }
            return "";
        } catch (Exception e) {
            return "";
        }
    }

    private static HttpURLConnection postDoor(Context context, String base, String json,
                                              int connectMs, int readMs) {
        if (base == null || base.isEmpty() || json == null) {
            return null;
        }
        String[] paths = new String[] {"/v1/utterance", "/utterance"};
        HttpURLConnection last = null;
        for (int i = 0; i < paths.length; i++) {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(base + paths[i]);
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(connectMs);
                conn.setReadTimeout(readMs);
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Accept", "application/json");
                applyAuth(conn, context);
                byte[] data = json.getBytes(StandardCharsets.UTF_8);
                OutputStream out = null;
                try {
                    out = conn.getOutputStream();
                    out.write(data);
                    out.flush();
                } finally {
                    if (out != null) {
                        try {
                            out.close();
                        } catch (Exception ignored) {
                        }
                    }
                }
                int code = conn.getResponseCode();
                if (code == 404 && i == 0) {
                    conn.disconnect();
                    continue;
                }
                return conn;
            } catch (Exception e) {
                if (conn != null) {
                    conn.disconnect();
                }
                last = null;
            }
        }
        return last;
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("bee_setup", Context.MODE_PRIVATE);
    }
}
