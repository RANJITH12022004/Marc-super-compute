import { isAuthorized, unauthorized, send, readJson, newId, storePutJob, storeGetResult, sleep } from "./_store.js";

// POST /v1/note  {title, body} -> proxied muse note.
// Direct HTTP to MARC_MUSE_URL first, else bridge mailbox fallback
// (enqueue session "note" job, poll for bridge result).
// Vercel auto-maps this file to /api/v1/note. Utterance mailbox untouched.

const DIRECT_TIMEOUT_MS = 6000;
const WAIT_CAP_S = 25;

function museBase() {
  try {
    const raw = (process.env.MARC_MUSE_URL || "").trim();
    if (!raw) return "";
    const base = raw.replace(/\/$/, "");
    const u = new URL(base);
    if (u.protocol !== "http:" && u.protocol !== "https:") return "";
    return base;
  } catch {
    return "";
  }
}

function museHeaders() {
  const h = { Accept: "application/json", "Content-Type": "application/json" };
  try {
    const tok = (process.env.MARC_TOKEN || "").trim();
    if (tok) h.Authorization = "Bearer " + tok;
  } catch {}
  return h;
}

async function museDirect(title, body) {
  const base = museBase();
  if (!base) return null;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), DIRECT_TIMEOUT_MS);
  try {
    const r = await fetch(base + "/note", {
      method: "POST",
      headers: museHeaders(),
      body: JSON.stringify({ title, body }),
      signal: ctrl.signal,
    });
    if (!r.ok) return null;
    const text = await r.text();
    if (!text || !text.trim()) return { ok: true };
    try {
      const data = JSON.parse(text);
      return data && typeof data === "object" ? data : { ok: true, text: String(data) };
    } catch {
      return { ok: true, text };
    }
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 404, { ok: false, error: "not found" });
  if (!isAuthorized(req)) return unauthorized(res);
  const data = await readJson(req);
  const title = String((data && data.title) || "");
  const body = String((data && (data.body !== undefined ? data.body : data.text)) || "");

  try {
    const direct = await museDirect(title, body);
    if (direct) {
      const out = { ok: true, ...direct };
      if (!("ok" in direct)) out.ok = true;
      return send(res, 200, out);
    }
  } catch {}

  let waitS = WAIT_CAP_S;
  try {
    const w = data && (data.timeout_s !== undefined ? data.timeout_s : (data.timeout !== undefined ? data.timeout : data.wait_s));
    if (w !== undefined && w !== null) waitS = parseFloat(w);
  } catch {}
  if (!isFinite(waitS)) waitS = WAIT_CAP_S;
  waitS = Math.max(0, Math.min(waitS, WAIT_CAP_S));

  const id = newId();
  let text = body;
  try {
    text = JSON.stringify({ title, body });
  } catch {}
  try {
    await storePutJob(id, text, "note");
  } catch {
    return send(res, 500, { ok: false, error: "store failed" });
  }
  const deadline = Date.now() + waitS * 1000;
  while (Date.now() < deadline) {
    let result = null;
    try {
      result = await storeGetResult(id);
    } catch {}
    if (result) {
      const out = { ok: true, id, ...result };
      if (!("ok" in result)) out.ok = true;
      return send(res, 200, out);
    }
    await sleep(500);
  }
  return send(res, 504, { ok: false, error: "timeout", id });
}
