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
import java.util.HashMap;
import java.util.Map;

/** Laptop/server steps go to Rox marc-muse :8096 /utterance. */
final class RoxClient {
    private RoxClient() {
    }

    static String baseUrl(Context context) {
        SharedPreferences p = prefs(context);
        String url = p.getString("rox_url", "").trim();
        if (url.isEmpty()) {
            url = p.getString("host", "").trim();
        }
        if (url.isEmpty()) {
            return "";
        }
        if (!url.startsWith("http")) {
            url = "http://" + url;
        }
        if (!url.contains(":")) {
            url = url + ":8096";
        }
        return url.replaceAll("/+$", "");
    }

    static boolean reachable(Context context) {
        String base = baseUrl(context);
        if (base.isEmpty()) {
            return false;
        }
        HttpURLConnection conn = null;
        try {
            URL url = new URL(base + "/island");
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(1500);
            conn.setReadTimeout(1500);
            conn.setRequestMethod("GET");
            int code = conn.getResponseCode();
            return code >= 200 && code < 500;
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    static String getWhoami(Context context) {
        try {
            String base = baseUrl(context);
            if (base == null || base.isEmpty()) {
                return "";
            }
            HttpURLConnection conn = null;
            try {
                URL url = new URL(base + "/whoami");
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3500);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Accept", "application/json");
                int code = conn.getResponseCode();
                if (code < 200 || code >= 300) {
                    return "";
                }
                InputStream in = null;
                try {
                    in = conn.getInputStream();
                } catch (Exception e) {
                    return "";
                }
                if (in == null) {
                    return "";
                }
                String body;
                try {
                    body = readAll(in);
                } finally {
                    try {
                        in.close();
                    } catch (Exception ignored) {
                    }
                }
                return extractText(body);
            } catch (Exception e) {
                return "";
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        } catch (Exception e) {
            return "";
        }
    }

    static String getMind(Context context, String q) {
        try {
            String base = baseUrl(context);
            if (base == null || base.isEmpty()) {
                return "";
            }
            String query = q == null ? "" : q;
            String encoded;
            try {
                encoded = URLEncoder.encode(query, "UTF-8");
            } catch (Exception e) {
                encoded = "";
            }
            HttpURLConnection conn = null;
            try {
                URL url = new URL(base + "/mind?q=" + encoded);
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3500);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Accept", "application/json");
                int code = conn.getResponseCode();
                if (code < 200 || code >= 300) {
                    return "";
                }
                InputStream in = null;
                try {
                    in = conn.getInputStream();
                } catch (Exception e) {
                    return "";
                }
                if (in == null) {
                    return "";
                }
                String body;
                try {
                    body = readAll(in);
                } finally {
                    try {
                        in.close();
                    } catch (Exception ignored) {
                    }
                }
                return extractText(body);
            } catch (Exception e) {
                return "";
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        } catch (Exception e) {
            return "";
        }
    }

    static boolean postNote(Context context, String title, String body) {
        try {
            String base = baseUrl(context);
            if (base == null || base.isEmpty()) {
                return false;
            }
            String t = title == null ? "" : title;
            String b = body == null ? "" : body;
            HttpURLConnection conn = null;
            try {
                URL url = new URL(base + "/note");
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3500);
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Accept", "application/json");
                Map<String, Object> payload = new HashMap<String, Object>();
                payload.put("title", t);
                payload.put("body", b);
                String json = MuseClient.toJson(payload);
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
                return code >= 200 && code < 300;
            } catch (Exception e) {
                return false;
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
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
        HttpURLConnection conn = null;
        try {
            URL url = new URL(base + "/utterance");
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(20000);
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            String body = "{\"text\":" + MuseClient.toJson(text)
                    + ",\"source\":\"bee\",\"target\":\"laptop\"}";
            OutputStream out = conn.getOutputStream();
            out.write(body.getBytes(StandardCharsets.UTF_8));
            out.close();
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
            if (conn != null) {
                conn.disconnect();
            }
        }
        return result;
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

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("bee_setup", Context.MODE_PRIVATE);
    }
}
