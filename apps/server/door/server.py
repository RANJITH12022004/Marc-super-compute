"""Door HTTP server — stdlib http.server. No model, no audio, no history.

Routes:
  POST /v1/utterance  JSON {text, session_id} -> waits, returns result
  GET  /v1/pull       long-poll, returns next job or {"ok":true,"job":null}
  POST /v1/result     JSON {id, ok, spoken, phone_steps, reply}
  GET  /v1/health     {ok, bridge_seen, bridge_seen_s}
  GET  /v1/whoami     proxied muse whoami (also /whoami for RoxClient)
  GET  /v1/mind?q=    proxied muse recall (also /mind?q= for RoxClient)
  POST /v1/note       proxied muse note   (also /note for RoxClient)
  GET/POST /v1/webhooks/meta  Meta IG/WA webhook proxy -> muse /webhooks/meta

Mind proxy: direct HTTP to MARC_MUSE_URL (loopback) first, else bridge
mailbox fallback (put_utterance with session whoami/mind/note + wait).

Auth: Authorization: Bearer MARC_TOKEN. Open when MARC_TOKEN empty
(mirrors marc-muse). Wrong/missing token -> 401.

Bind: PORT env (default 8787), 0.0.0.0. Never binds marc-muse (:8096).
"""

import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mailbox as mbox

PORT_DEFAULT = 8787
BODY_LIMIT = 256 * 1024

MUSE_TIMEOUT_S = 8.0
MIND_WAIT_DEFAULT_S = 30.0
MIND_WAIT_MAX_S = 60.0

# Marker text for whoami jobs travelling through the utterance mailbox.
# Bridge detects session_id in ("whoami","mind","note") and forwards to
# muse /whoami, /mind, /note instead of /utterance.
WHOAMI_MARKER = "__door_whoami__"
MIND_SESSIONS = ("whoami", "mind", "note")


def _port():
    try:
        return int((os.environ.get("PORT") or str(PORT_DEFAULT)).strip()
                   or PORT_DEFAULT)
    except ValueError:
        return PORT_DEFAULT


def _box():
    return mbox.get_default()


def _muse_base():
    raw = (os.environ.get("MARC_MUSE_URL")
           or "http://127.0.0.1:8096").strip()
    if not raw:
        return ""
    base = raw.rstrip("/")
    try:
        from urllib.parse import urlparse as _up
        parts = _up(base)
        host = (parts.hostname or "").lower()
        scheme = (parts.scheme or "").lower()
    except Exception:
        return ""
    if scheme not in ("http", "https"):
        return ""
    # Loopback only — never proxy to a non-loopback muse.
    if host not in ("127.0.0.1", "localhost", "::1"):
        return ""
    return base


def _muse_token():
    try:
        return (os.environ.get("MARC_TOKEN") or "").strip()
    except Exception:
        return ""


def _muse_fetch(method, muse_path, payload=None, timeout=MUSE_TIMEOUT_S):
    """Direct HTTP proxy to loopback muse. Returns dict or None on failure."""
    base = _muse_base()
    if not base:
        return None
    url = base + muse_path
    headers = {"Accept": "application/json"}
    tok = _muse_token()
    if tok:
        headers["Authorization"] = "Bearer " + tok
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        try:
            body = json.dumps(payload).encode("utf-8")
        except Exception:
            return None
    try:
        req = urllib.request.Request(url, data=body, method=method,
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {"ok": True, "text": raw}
        if isinstance(data, dict):
            return data
        return {"ok": True, "text": str(data)}
    except Exception:
        return None


def _mind_wait_s(qs=None, data=None, default=MIND_WAIT_DEFAULT_S):
    try:
        if isinstance(qs, dict):
            for key in ("timeout_s", "timeout", "wait_s"):
                vals = qs.get(key)
                if vals:
                    v = float(vals[0])
                    return max(0.0, min(v, MIND_WAIT_MAX_S))
        if isinstance(data, dict):
            for key in ("timeout_s", "timeout", "wait_s"):
                if key in data:
                    v = float(data[key])
                    return max(0.0, min(v, MIND_WAIT_MAX_S))
    except Exception:
        pass
    return default


def _mailbox_proxy(kind, text, wait_s):
    """Enqueue a mind-proxy job through the utterance mailbox and wait.

    kind in ("whoami","mind","note"). Returns result dict or None (timeout).
    """
    try:
        wait = float(wait_s)
    except Exception:
        wait = MIND_WAIT_DEFAULT_S
    wait = max(0.0, min(wait, MIND_WAIT_MAX_S))
    box = _box()
    try:
        job_id = box.put_utterance(text, kind)
    except Exception:
        return None
    try:
        res = box.wait_result(job_id, timeout_s=wait)
    except Exception:
        return None
    if res is None:
        return None
    if isinstance(res, dict):
        out = dict(res)
        out.setdefault("id", job_id)
        out.setdefault("ok", True)
        return out
    return {"ok": True, "id": job_id, "text": str(res)}


class Handler(BaseHTTPRequestHandler):
    server_version = "door/1.0"

    def log_message(self, fmt, *args):
        # Never log tokens / bodies.
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    # -- helpers --------------------------------------------------------
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > BODY_LIMIT:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8", "replace")
            data = json.loads(raw) if raw.strip() else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _need_auth(self):
        if not mbox.is_authorized(self.headers):
            self._send(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def _serve_whoami(self, qs):
        wait_s = _mind_wait_s(qs)
        direct = _muse_fetch("GET", "/whoami")
        if isinstance(direct, dict):
            out = dict(direct)
            out.setdefault("ok", True)
            self._send(200, out)
            return
        res = _mailbox_proxy("whoami", WHOAMI_MARKER, wait_s)
        if res is None:
            self._send(504, {"ok": False, "error": "timeout"})
            return
        self._send(200, res)

    def _serve_mind(self, qs):
        try:
            q = (qs.get("q") or qs.get("query") or qs.get("text")
                 or [""])[0]
        except Exception:
            q = ""
        if q is None:
            q = ""
        q = str(q)
        wait_s = _mind_wait_s(qs)
        direct = _muse_fetch("GET", "/mind?q=" + quote(q, safe=""))
        if isinstance(direct, dict):
            out = dict(direct)
            out.setdefault("ok", True)
            out.setdefault("text", "")
            self._send(200, out)
            return
        res = _mailbox_proxy("mind", q, wait_s)
        if res is None:
            self._send(504, {"ok": False, "error": "timeout"})
            return
        self._send(200, res)

    def _serve_note(self, data):
        title = data.get("title") or ""
        body = data.get("body") if "body" in data else data.get("text", "")
        if title is None:
            title = ""
        if body is None:
            body = ""
        title = str(title)
        body = str(body)
        wait_s = _mind_wait_s(None, data)
        direct = _muse_fetch("POST", "/note",
                             {"title": title, "body": body})
        if isinstance(direct, dict):
            out = dict(direct)
            out.setdefault("ok", True)
            self._send(200, out)
            return
        try:
            text = json.dumps({"title": title, "body": body})
        except Exception:
            text = body
        res = _mailbox_proxy("note", text, wait_s)
        if res is None:
            self._send(504, {"ok": False, "error": "timeout"})
            return
        self._send(200, res)

    # -- routes ---------------------------------------------------------
    def _proxy_meta_webhook(self, method, qs_raw=""):
        """Forward Meta webhook verify/POST to loopback muse (no door auth)."""
        base = _muse_base()
        if not base:
            self._send(503, {"ok": False, "error": "muse offline"})
            return
        url = base + "/webhooks/meta" + (("?" + qs_raw) if qs_raw else "")
        headers = {"Accept": "*/*"}
        tok = _muse_token()
        if tok:
            headers["Authorization"] = "Bearer " + tok
        body = None
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length > 0 else b""
            body = raw
            headers["Content-Type"] = self.headers.get("Content-Type") or "application/json"
            sig = self.headers.get("X-Hub-Signature-256") or self.headers.get("X-Hub-Signature")
            if sig:
                headers["X-Hub-Signature-256"] = sig
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=MUSE_TIMEOUT_S) as resp:
                raw_out = resp.read()
                code = resp.getcode()
                ctype = resp.headers.get("Content-Type") or "application/json"
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw_out)))
            self.end_headers()
            self.wfile.write(raw_out)
        except Exception:
            self._send(502, {"ok": False, "error": "muse unreachable"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = (parsed.path or "/").rstrip("/") or "/"
        if path in ("/v1/webhooks/meta", "/webhooks/meta"):
            self._proxy_meta_webhook("GET", parsed.query or "")
            return
        if path in ("/v1/health", "/health"):
            if not self._need_auth():
                return
            self._send(200, _box().health())
            return
        if path in ("/v1/whoami", "/whoami"):
            if not self._need_auth():
                return
            try:
                qs = parse_qs(parsed.query or "")
            except Exception:
                qs = {}
            self._serve_whoami(qs)
            return
        if path in ("/v1/mind", "/mind"):
            if not self._need_auth():
                return
            try:
                qs = parse_qs(parsed.query or "")
            except Exception:
                qs = {}
            self._serve_mind(qs)
            return
        if path in ("/v1/pull", "/pull"):
            if not self._need_auth():
                return
            try:
                qs = parse_qs(parsed.query or "")
            except Exception:
                qs = {}
            try:
                timeout_s = float((qs.get("timeout_s") or qs.get("timeout")
                                   or ["25"])[0])
            except Exception:
                timeout_s = 25.0
            # Clamp so a local dev server never hangs forever.
            timeout_s = max(0.0, min(timeout_s, 28.0))
            job = _box().pull(timeout_s=timeout_s)
            if job is None:
                self._send(200, {"ok": True, "job": None})
            else:
                self._send(200, {"ok": True, "id": job.get("id"),
                                 "text": job.get("text", ""),
                                 "session_id": job.get("session_id",
                                                       "phone")})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        raw_path = self.path.split("?")[0].rstrip("/") or "/"
        path = raw_path
        if path in ("/v1/webhooks/meta", "/webhooks/meta"):
            self._proxy_meta_webhook("POST", "")
            return
        if path in ("/v1/note", "/note"):
            if not self._need_auth():
                return
            data = self._read_json()
            self._serve_note(data if isinstance(data, dict) else {})
            return
        if path in ("/v1/utterance", "/utterance"):
            if not self._need_auth():
                return
            data = self._read_json()
            text = data.get("text") or ""
            if not str(text).strip():
                self._send(400, {"ok": False, "error": "empty text"})
                return
            session_id = str(data.get("session_id")
                             or data.get("session") or "phone")
            try:
                wait_s = float(data.get("timeout_s", 90))
            except Exception:
                wait_s = 90.0
            wait_s = max(0.0, min(wait_s, 95.0))
            box = _box()
            job_id = box.put_utterance(str(text), session_id)
            result = box.wait_result(job_id, timeout_s=wait_s)
            if result is None:
                self._send(504, {"ok": False, "error": "timeout",
                                 "id": job_id})
                return
            out = {"ok": bool(result.get("ok", True))}
            for key in ("spoken", "phone_steps", "reply"):
                if key in result:
                    out[key] = result[key]
            # Pass through any extra keys (harmless, no history stored).
            for key, val in result.items():
                if key not in out:
                    out[key] = val
            out.setdefault("id", job_id)
            self._send(200, out)
            return
        if path in ("/v1/result", "/result"):
            if not self._need_auth():
                return
            data = self._read_json()
            job_id = str(data.get("id") or data.get("job_id") or "")
            if not job_id:
                self._send(400, {"ok": False, "error": "missing id"})
                return
            payload = {"ok": bool(data.get("ok", True))}
            for key in ("spoken", "phone_steps", "reply"):
                if key in data:
                    payload[key] = data[key]
            for key, val in data.items():
                if key not in payload and key not in ("id", "job_id"):
                    payload[key] = val
            _box().put_result(job_id, payload)
            self._send(200, {"ok": True, "id": job_id})
            return
        self._send(404, {"ok": False, "error": "not found"})


def _bind():
    host = (os.environ.get("DOOR_BIND") or "127.0.0.1").strip() or "127.0.0.1"
    return host, _port()


def main():
    host, port = _bind()
    srv = ThreadingHTTPServer((host, port), Handler)
    sys.stderr.write("door listening on %s:%d\n" % (host, port))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
