"""marc-muse HTTP service — live Muse planner on Rox loopback :8096.

Entry:  python apps/marc-muse/server.py
Bind:   MARC_MUSE_BIND : MARC_MUSE_PORT  (default 127.0.0.1:8096)
"""

import importlib.util
import json
import os
import sys
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import planner

try:
    import executor
except Exception:
    executor = None


def _load_recall():
    try:
        from brain.recall import mind_recall, who_am_i  # type: ignore
        return mind_recall, who_am_i
    except Exception:
        pass
    try:
        here = Path(os.path.dirname(os.path.abspath(__file__)))
        rp = here / "brain" / "recall.py"
        if rp.is_file():
            spec = importlib.util.spec_from_file_location("brain_recall_fallback", str(rp))
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return getattr(mod, "mind_recall", None), getattr(mod, "who_am_i", None)
    except Exception:
        pass
    return None, None


_recall_fn, _whoami_fn = _load_recall()


def _do_recall(query):
    if callable(_recall_fn):
        try:
            res = _recall_fn(query or "")
            if isinstance(res, dict):
                res.setdefault("ok", True)
                res.setdefault("text", "")
                res.setdefault("hits", [])
                return res
            if isinstance(res, str):
                return {"ok": True, "text": res, "hits": []}
        except Exception as exc:
            return {"ok": False, "text": "recall error: %s" % exc, "hits": []}
    return {"ok": False, "text": "recall unavailable", "hits": []}


def _do_whoami():
    if callable(_whoami_fn):
        try:
            res = _whoami_fn()
            if isinstance(res, dict):
                res.setdefault("ok", True)
                res.setdefault("text", "")
                res.setdefault("hits", [])
                return res
            if isinstance(res, str):
                return {"ok": True, "text": res, "hits": []}
        except Exception as exc:
            return {"ok": False, "text": "whoami error: %s" % exc, "hits": []}
    return _do_recall("who am i")


def _bind():
    host = (os.environ.get("MARC_MUSE_BIND") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int((os.environ.get("MARC_MUSE_PORT") or "8096").strip() or "8096")
    except ValueError:
        port = 8096
    return host, port


def _authorized(handler):
    expected = os.environ.get("MARC_TOKEN") or ""
    if not expected:
        return True
    auth = handler.headers.get("Authorization") or ""
    xtok = handler.headers.get("X-Marc-Token") or ""
    got = ""
    if auth.startswith("Bearer "):
        got = auth[len("Bearer "):].strip()
    if not got:
        got = (xtok or "").strip()
    if not got:
        return False
    return hmac.compare_digest(got, expected)


def _hop_defaults():
    if executor is not None:
        try:
            h = executor.get_hops()
            mx = int(h.get("max_hops", 8))
            hd = int(h.get("hard_hops", 14))
            return mx, hd
        except Exception:
            pass
    return 8, 14


class Handler(BaseHTTPRequestHandler):
    server_version = "marc-muse/1.0"

    def log_message(self, fmt, *args):
        # Never log tokens / headers / bodies.
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

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
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8", "replace")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _need_auth(self):
        if not _authorized(self):
            self._send(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        path = (parsed.path or "/").rstrip("/") or "/"
        if path == "/health":
            if not self._need_auth():
                return
            mx, hd = _hop_defaults()
            self._send(200, {
                "ok": True,
                "planner": "muse",
                "mode": planner.get_mode(),
                "paused": planner.is_paused(),
                "stopped": planner.is_stopped(),
                "max_hops": mx,
                "hard_hops": hd,
                "hops": {"max_hops": mx, "hard_hops": hd},
            })
            return
        if path == "/mind":
            if not self._need_auth():
                return
            try:
                qs = parse_qs(parsed.query or "")
            except Exception:
                qs = {}
            q = qs.get("q", [""])[0]
            if not q:
                q = qs.get("query", [""])[0]
            if not q:
                q = qs.get("text", [""])[0]
            self._send(200, _do_recall(q or ""))
            return
        if path == "/whoami":
            if not self._need_auth():
                return
            self._send(200, _do_whoami())
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if not self._need_auth():
            return
        if path == "/plan":
            data = self._read_json()
            result = planner.plan(
                text=data.get("text", ""),
                session_id=data.get("session_id") or data.get("session") or "phone",
                target=data.get("target", "auto"),
                note=data.get("note", ""),
                context=data.get("context"),
            )
            self._send(200, result)
            return
        if path == "/run":
            data = self._read_json()
            session_id = data.get("session_id") or data.get("session") or "phone"
            plan_obj = data.get("plan")
            if plan_obj is None:
                plan_obj = planner.plan(
                    text=data.get("text", "") or "",
                    session_id=session_id,
                    target=data.get("target", "auto"),
                    note=data.get("note", ""),
                    context=data.get("context"),
                )
            if executor is None:
                self._send(200, {"ok": False, "error": "executor missing",
                                 "session_id": session_id})
                return
            try:
                result = executor.execute_plan(plan_obj, session_id)
            except Exception as exc:
                self._send(200, {"ok": False, "error": str(exc),
                                 "session_id": session_id})
                return
            self._send(200, result)
            return
        if path in ("/muse/stop", "/stop"):
            planner.set_stopped()
            self._send(200, {"ok": True, "stopped": True})
            return
        if path == "/muse/resume":
            planner.clear_stopped()
            self._send(200, {"ok": True, "stopped": False})
            return
        self._send(404, {"ok": False, "error": "not found"})


def serve():
    host, port = _bind()
    httpd = ThreadingHTTPServer((host, port), Handler)
    sys.stderr.write("marc-muse on %s:%d mode=%s\n" % (host, port, planner.get_mode()))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve()
