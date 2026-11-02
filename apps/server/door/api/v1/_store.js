// Shared door mailbox backend for Vercel serverless functions.
// SAME protocol as apps/server/door/mailbox.py (stdlib python).
//
// Production MUST set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN.
// Without them this falls back to a per-instance in-memory Map, which
// does NOT share state between Vercel serverless instances (dev only).
//
// Keys (all prefixed door:):
//   door:queue        list of pending job ids (RPUSH/LPOP)
//   door:job:<id>     JSON {id,text,session_id} EX 120
//   door:result:<id>  JSON {ok,spoken,phone_steps,reply,...} EX 120
//   door:last_pull    unix timestamp (no expiry)

const EXPIRY_S = 120;
const BRIDGE_SEEN_S = 30;

function env(name) {
  try {
    return (process.env[name] || "").trim();
  } catch {
    return "";
  }
}

export function expectedToken() {
  return env("MARC_TOKEN");
}

export function extractBearer(req) {
  try {
    const h = (req && req.headers) || {};
    const auth = h.authorization || h.Authorization || "";
    if (typeof auth === "string" && auth.startsWith("Bearer ")) {
      return auth.slice(7).trim();
    }
    const xtok = h["x-marc-token"] || h["X-Marc-Token"] || "";
    if (typeof xtok === "string" && xtok.trim()) return xtok.trim();
  } catch {}
  return "";
}

export function isAuthorized(req) {
  const expected = expectedToken();
  if (!expected) return true; // open mode, mirrors marc-muse
  const got = extractBearer(req);
  if (!got || got.length !== expected.length) return false;
  // constant-time compare
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ got.charCodeAt(i);
  }
  return diff === 0;
}

export function unauthorized(res) {
  return send(res, 401, { ok: false, error: "unauthorized" });
}

export function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Content-Length", Buffer.byteLength(body));
  res.end(body);
}

export async function readJson(req) {
  const chunks = [];
  const limit = 256 * 1024;
  let size = 0;
  await new Promise((resolve) => {
    req.on("data", (c) => {
      size += c.length;
      if (size <= limit) chunks.push(c);
    });
    req.on("end", resolve);
    req.on("error", resolve);
  });
  if (!chunks.length) return {};
  try {
    const data = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

export function newId() {
  try {
    const c = require("crypto");
    return c.randomBytes(6).toString("hex");
  } catch {}
  return (
    Math.random().toString(16).slice(2) + Date.now().toString(16)
  ).slice(0, 12);
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---- Upstash REST client (fetch, no deps) ----
function upstashCfg() {
  const url = env("UPSTASH_REDIS_REST_URL").replace(/\/$/, "");
  const token = env("UPSTASH_REDIS_REST_TOKEN");
  if (!url || !token) return null;
  return { url, token };
}

export function useRedis() {
  return !!upstashCfg();
}

async function up(cmd) {
  // cmd: array of path segments, e.g. ["get","door:last_pull"]
  const cfg = upstashCfg();
  if (!cfg) throw new Error("no redis");
  const path = cmd.map((s) => encodeURIComponent(String(s))).join("/");
  const r = await fetch(cfg.url + "/" + path, {
    headers: { Authorization: "Bearer " + cfg.token },
  });
  if (!r.ok) throw new Error("upstash " + r.status);
  return r.json(); // {result: ...}
}

const mem = globalThis.__doorMem || (globalThis.__doorMem = {
  queue: [],
  jobs: new Map(), // id -> {id,text,session_id,created}
  results: new Map(), // id -> payload
  lastPull: 0,
});

function memSweep(now) {
  const cutoff = now - EXPIRY_S * 1000;
  for (const [k, v] of mem.jobs) {
    if (!v || v.created <= cutoff) mem.jobs.delete(k);
  }
  for (const [k, v] of mem.results) {
    if (!v || v.at <= cutoff) mem.results.delete(k);
  }
  mem.queue = mem.queue.filter((id) => mem.jobs.has(id));
}

// ---- unified ops used by the route handlers ----
export async function storePutJob(id, text, sessionId) {
  if (useRedis()) {
    const job = JSON.stringify({ id, text, session_id: sessionId });
    await up(["set", "door:job:" + id, job, "EX", String(EXPIRY_S)]);
    await up(["rpush", "door:queue", id]);
    return;
  }
  const now = Date.now();
  memSweep(now);
  mem.jobs.set(id, { id, text, session_id: sessionId, created: now });
  mem.queue.push(id);
}

export async function storeTakeJob() {
  if (useRedis()) {
    const popped = await up(["lpop", "door:queue"]);
    const id = popped && popped.result;
    if (!id) return null;
    const got = await up(["get", "door:job:" + id]);
    if (!got || !got.result) return null;
    try {
      const j = JSON.parse(got.result);
      return { id: j.id || id, text: j.text || "", session_id: j.session_id || "phone" };
    } catch {
      return null;
    }
  }
  memSweep(Date.now());
  while (mem.queue.length) {
    const id = mem.queue.shift();
    const j = mem.jobs.get(id);
    if (!j) continue;
    return { id: j.id, text: j.text, session_id: j.session_id };
  }
  return null;
}

export async function storePutResult(id, payload) {
  if (useRedis()) {
    await up(["set", "door:result:" + id, JSON.stringify(payload), "EX", String(EXPIRY_S)]);
    return;
  }
  memSweep(Date.now());
  mem.results.set(id, { at: Date.now(), payload });
}

export async function storeGetResult(id) {
  if (useRedis()) {
    try {
      const got = await up(["get", "door:result:" + id]);
      if (!got || !got.result) return null;
      return JSON.parse(got.result);
    } catch {
      return null;
    }
  }
  const e = mem.results.get(id);
  return e ? e.payload : null;
}

export async function storeTouchPull() {
  const now = Date.now() / 1000;
  if (useRedis()) {
    try {
      await up(["set", "door:last_pull", String(now)]);
    } catch {}
    return;
  }
  mem.lastPull = now;
}

export async function storeHealth() {
  let seen = null;
  if (useRedis()) {
    try {
      const got = await up(["get", "door:last_pull"]);
      if (got && got.result) seen = parseFloat(got.result);
    } catch {
      seen = null;
    }
  } else {
    seen = mem.lastPull || null;
  }
  if (!seen) return { ok: true, bridge_seen: false, bridge_seen_s: null };
  const age = Date.now() / 1000 - seen;
  return { ok: true, bridge_seen: age <= BRIDGE_SEEN_S, bridge_seen_s: age };
}
