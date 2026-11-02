import { send } from "./_store.js";

// GET/POST /v1/webhooks/meta — public Meta Instagram/WhatsApp webhook proxy.
// Forwards to MARC_MUSE_URL /webhooks/meta (loopback on Rox). No MARC_TOKEN
// auth on the inbound Meta challenge; muse verifies hub.verify_token / HMAC.

const DIRECT_TIMEOUT_MS = 8000;

function museBase() {
  try {
    const raw = (process.env.MARC_MUSE_URL || "").trim();
    if (!raw) return "";
    return raw.replace(/\/$/, "");
  } catch {
    return "";
  }
}

function museHeaders(extra) {
  const h = Object.assign({ Accept: "application/json" }, extra || {});
  try {
    const tok = (process.env.MARC_TOKEN || "").trim();
    if (tok) h.Authorization = "Bearer " + tok;
  } catch {}
  return h;
}

async function readRaw(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  const base = museBase();
  if (!base) {
    return send(res, 503, { ok: false, error: "muse offline" });
  }

  if (req.method === "GET") {
    try {
      const u = new URL(req.url, "http://x");
      const qs = u.search || "";
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), DIRECT_TIMEOUT_MS);
      try {
        const r = await fetch(base + "/webhooks/meta" + qs, {
          method: "GET",
          headers: museHeaders(),
          signal: ctrl.signal,
        });
        const text = await r.text();
        res.statusCode = r.status;
        res.setHeader("Content-Type", r.headers.get("content-type") || "text/plain");
        res.end(text);
        return;
      } finally {
        clearTimeout(t);
      }
    } catch (e) {
      return send(res, 502, { ok: false, error: "muse unreachable" });
    }
  }

  if (req.method === "POST") {
    try {
      const raw = await readRaw(req);
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), DIRECT_TIMEOUT_MS);
      try {
        const headers = museHeaders({
          "Content-Type": req.headers["content-type"] || "application/json",
        });
        const sig =
          req.headers["x-hub-signature-256"] || req.headers["x-hub-signature"];
        if (sig) headers["X-Hub-Signature-256"] = sig;
        const r = await fetch(base + "/webhooks/meta", {
          method: "POST",
          headers,
          body: raw,
          signal: ctrl.signal,
        });
        const text = await r.text();
        let data = {};
        try {
          data = JSON.parse(text);
        } catch {
          data = { ok: r.ok, raw: text };
        }
        return send(res, r.status, data && typeof data === "object" ? data : { ok: r.ok });
      } finally {
        clearTimeout(t);
      }
    } catch (e) {
      return send(res, 502, { ok: false, error: "muse unreachable" });
    }
  }

  return send(res, 404, { ok: false, error: "not found" });
}
