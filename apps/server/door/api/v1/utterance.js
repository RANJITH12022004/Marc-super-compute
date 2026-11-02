import { isAuthorized, unauthorized, send, readJson, newId, storePutJob, storeGetResult, sleep } from "./_store.js";

// POST /v1/utterance  {text, session_id, timeout_s?}
// Stores a job, then polls for the bridge result.
// NOTE: serverless functions cannot block 90s (Vercel hobby ~10-30s),
// so timeout_s is capped at 25s here. The stdlib python server.py
// (local dev) waits up to 90s. Same JSON protocol either way.
export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 404, { ok: false, error: "not found" });
  if (!isAuthorized(req)) return unauthorized(res);
  const data = await readJson(req);
  const text = String((data && data.text) || "");
  if (!text.trim()) return send(res, 400, { ok: false, error: "empty text" });
  const sessionId = String((data && (data.session_id || data.session)) || "phone");
  let waitS = Number((data && data.timeout_s) || 55);
  if (!isFinite(waitS)) waitS = 55;
  waitS = Math.max(0, Math.min(waitS, 55));

  const id = newId();
  try {
    await storePutJob(id, text, sessionId);
  } catch (e) {
    return send(res, 500, { ok: false, error: "store failed" });
  }
  const deadline = Date.now() + waitS * 1000;
  while (Date.now() < deadline) {
    let result = null;
    try {
      result = await storeGetResult(id);
    } catch {}
    if (result) {
      const out = { ok: !!result.ok, id };
      for (const k of ["spoken", "phone_steps", "reply"]) {
        if (k in result) out[k] = result[k];
      }
      for (const k of Object.keys(result)) {
        if (!(k in out)) out[k] = result[k];
      }
      if (!("ok" in result)) out.ok = true;
      return send(res, 200, out);
    }
    await sleep(500);
  }
  return send(res, 504, { ok: false, error: "timeout", id });
}
