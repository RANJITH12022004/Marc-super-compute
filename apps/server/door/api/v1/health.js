import { isAuthorized, unauthorized, send, storeHealth } from "./_store.js";

// GET /v1/health -> {ok, bridge_seen, bridge_seen_s}
export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, 404, { ok: false, error: "not found" });
  if (!isAuthorized(req)) return unauthorized(res);
  try {
    const h = await storeHealth();
    return send(res, 200, h);
  } catch {
    return send(res, 200, { ok: true, bridge_seen: false, bridge_seen_s: null });
  }
}
