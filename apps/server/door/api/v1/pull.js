import { isAuthorized, unauthorized, send, storeTakeJob, storeTouchPull, sleep } from "./_store.js";

// GET /v1/pull?timeout_s=25 — bridge long-poll. Updates last_pull.
export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, 404, { ok: false, error: "not found" });
  if (!isAuthorized(req)) return unauthorized(res);
  let timeoutS = 25;
  try {
    const u = new URL(req.url, "http://x");
    const q = u.searchParams.get("timeout_s") || u.searchParams.get("timeout");
    if (q !== null) timeoutS = parseFloat(q);
  } catch {}
  if (!isFinite(timeoutS)) timeoutS = 25;
  timeoutS = Math.max(0, Math.min(timeoutS, 25));

  try {
    await storeTouchPull();
  } catch {}
  const deadline = Date.now() + timeoutS * 1000;
  while (true) {
    let job = null;
    try {
      job = await storeTakeJob();
    } catch {}
    if (job) return send(res, 200, { ok: true, id: job.id, text: job.text || "", session_id: job.session_id || "phone" });
    if (Date.now() >= deadline) return send(res, 200, { ok: true, job: null });
    await sleep(500);
  }
}
