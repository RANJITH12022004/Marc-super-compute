"""Door mailbox — Vercel-ready HTTPS mailbox. Stdlib only.

No model, no audio, no chat history. Just a job queue:

  phone/laptop --POST /v1/utterance--> door --GET /v1/pull--> bridge
  bridge --POST /v1/result--> door --(waiter wakes)--> phone/laptop

Auth: ``Authorization: Bearer MARC_TOKEN``. When ``MARC_TOKEN`` env is
empty, auth is open (mirrors marc-muse, keeps unit tests simple).

Expiry: jobs/results older than ~120s are swept lazily.
Bridge is "seen" when last pull was within 30s.
"""

import hmac
import os
import threading
import time
import uuid

EXPIRY_S = 120.0
BRIDGE_SEEN_S = 30.0
DEFAULT_WAIT_S = 90.0
DEFAULT_PULL_S = 25.0


def expected_token():
    """Current MARC_TOKEN (read live so tests can patch env)."""
    try:
        return (os.environ.get("MARC_TOKEN") or "").strip()
    except Exception:
        return ""


def _headers_get(headers, name):
    """Case-insensitive header lookup for dicts and HTTPMessage."""
    if headers is None:
        return ""
    want = (name or "").lower()
    try:
        get = getattr(headers, "get", None)
        if callable(get):
            for key in (name, name.lower(), name.upper(), "-".join(
                    p.capitalize() for p in want.split("-"))):
                try:
                    val = headers.get(key)
                except Exception:
                    val = None
                if val:
                    return str(val)
    except Exception:
        pass
    try:
        items = headers.items() if hasattr(headers, "items") else []
        for k, v in items:
            try:
                if str(k).lower() == want and v:
                    return str(v)
            except Exception:
                continue
    except Exception:
        pass
    if isinstance(headers, dict):
        for k, v in headers.items():
            try:
                if str(k).lower() == want and v:
                    return str(v)
            except Exception:
                continue
    return ""


def extract_bearer(headers):
    auth = _headers_get(headers, "authorization")
    if auth and auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    # Compat alias mirrored from marc-muse (never required).
    xtok = _headers_get(headers, "x-marc-token")
    if xtok:
        return xtok.strip()
    return ""


def is_authorized(headers):
    """True when request headers carry the right bearer token.

    Open (True) when MARC_TOKEN env is empty — mirrors marc-muse.
    """
    expected = expected_token()
    if not expected:
        return True
    got = extract_bearer(headers)
    if not got:
        return False
    try:
        return hmac.compare_digest(got, expected)
    except Exception:
        return got == expected


class Mailbox(object):
    """Thread-safe in-memory job mailbox.

    ``backend`` is an optional dict used as the job table (for tests).
    Events/queues stay in memory; only job payloads live in ``backend``.
    """

    def __init__(self, backend=None):
        self._cond = threading.Condition()
        self._pending = []  # FIFO of {"id","text","session_id","_created"}
        self._jobs = backend if backend is not None else {}
        self._last_pull = None  # wall-clock time.time()

    def _sweep_locked(self, now):
        cutoff = now - EXPIRY_S
        try:
            self._pending = [j for j in self._pending
                             if j.get("_created", now) > cutoff
                             and j.get("id") in self._jobs]
        except Exception:
            self._pending = []
        try:
            for jid in [k for k, e in list(self._jobs.items())
                        if not isinstance(e, dict)
                        or e.get("_created", now) <= cutoff]:
                self._jobs.pop(jid, None)
        except Exception:
            pass

    # -- health ---------------------------------------------------------
    def health(self):
        with self._cond:
            now = time.time()
            if self._last_pull is None:
                return {"ok": True, "bridge_seen": False,
                        "bridge_seen_s": None}
            seen_s = now - self._last_pull
            return {"ok": True, "bridge_seen": seen_s <= BRIDGE_SEEN_S,
                    "bridge_seen_s": seen_s}

    # -- utterance side ---------------------------------------------------
    def put_utterance(self, text, session_id="phone"):
        now = time.time()
        job_id = uuid.uuid4().hex[:12]
        entry = {"id": job_id, "text": text,
                 "session_id": session_id or "phone",
                 "_created": now, "result": None}
        with self._cond:
            self._sweep_locked(now)
            self._jobs[job_id] = entry
            self._pending.append({"id": job_id, "text": text,
                                  "session_id": session_id or "phone",
                                  "_created": now})
            self._cond.notify_all()
        return job_id

    def wait_result(self, job_id, timeout_s=DEFAULT_WAIT_S):
        try:
            timeout = float(timeout_s)
        except Exception:
            timeout = DEFAULT_WAIT_S
        if timeout < 0:
            timeout = 0
        deadline = time.time() + timeout
        with self._cond:
            while True:
                entry = self._jobs.get(job_id)
                if isinstance(entry, dict) and entry.get("result") is not None:
                    res = entry.get("result")
                    return dict(res) if isinstance(res, dict) else res
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                try:
                    self._cond.wait(timeout=min(1.0, remaining))
                except Exception:
                    time.sleep(min(0.05, remaining))
                try:
                    self._sweep_locked(time.time())
                except Exception:
                    pass
                if job_id not in self._jobs and time.time() >= deadline:
                    return None

    # -- bridge side ------------------------------------------------------
    def pull(self, timeout_s=DEFAULT_PULL_S):
        try:
            timeout = float(timeout_s)
        except Exception:
            timeout = DEFAULT_PULL_S
        if timeout < 0:
            timeout = 0
        with self._cond:
            now = time.time()
            self._last_pull = now
            self._sweep_locked(now)
            self._cond.notify_all()
            deadline = now + timeout
            while True:
                while self._pending:
                    cand = self._pending.pop(0)
                    jid = cand.get("id")
                    entry = self._jobs.get(jid)
                    if entry is None:
                        continue  # expired
                    return {"id": jid, "text": entry.get("text", ""),
                            "session_id": entry.get("session_id", "phone")}
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                try:
                    self._cond.wait(timeout=min(1.0, remaining))
                except Exception:
                    time.sleep(min(0.05, remaining))

    def put_result(self, job_id, payload):
        if not isinstance(payload, dict):
            payload = {"ok": True, "reply": str(payload)}
        now = time.time()
        with self._cond:
            self._sweep_locked(now)
            entry = self._jobs.get(job_id)
            if isinstance(entry, dict):
                entry["result"] = dict(payload)
            else:
                # Orphan result (waiter may arrive late); keep for EXPIRY_S.
                self._jobs[job_id] = {"id": job_id, "text": "",
                                      "session_id": "",
                                      "_created": now,
                                      "result": dict(payload)}
            self._cond.notify_all()
        return True


# Module-level default instance (used by server.py).
_default = Mailbox()


def get_default():
    return _default


def health():
    return _default.health()


def put_utterance(text, session_id="phone"):
    return _default.put_utterance(text, session_id)


def wait_result(job_id, timeout_s=DEFAULT_WAIT_S):
    return _default.wait_result(job_id, timeout_s)


def pull(timeout_s=DEFAULT_PULL_S):
    return _default.pull(timeout_s)


def put_result(job_id, payload):
    return _default.put_result(job_id, payload)
