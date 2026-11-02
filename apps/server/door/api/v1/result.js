import { isAuthorized, unauthorized, send, readJson, storePutResult } from "./_store.js";

// POST /v1/result  {id, ok, spoken, phone_steps, reply, ...}
export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 404, { ok: false, error: "not found" });
  if (!isAuthorized(req)) return unauthorized(res);
  const data = await readJson(req);
  const id = String((data && (data.id || data.job_id)) || "");
  if (!id) return send(res, 400, { ok: false, error: "missing id" });
  const payload = { ok: !!(data && data.ok !== false) };
  for (const k of ["spoken", "phone_steps", "reply"]) {
    if (data && k in data) payload[k] = data[k];
  }
  for (const k of Object.keys(data || {})) {
    if (!(k in payload) && k !== "id" && k !== "job_id") payload[k] = data[k];
  }
  try {
    await storePutResult(id, payload);
  } catch {
    return send(res, 500, { ok: false, error: "store failed" });
  }
  return send(res, 200, { ok: true, id });
}
