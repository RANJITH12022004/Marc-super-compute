"""marc-muse HTTP service — live Muse planner on Rox loopback :8096.

Entry:  python apps/marc-muse/server.py
Bind:   MARC_MUSE_BIND : MARC_MUSE_PORT  (default 127.0.0.1:8096)
"""

import json
import os
import sys
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import planner


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
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/health":
            if not self._need_auth():
                return
            self._send(200, {
                "ok": True,
                "planner": "muse",
                "mode": planner.get_mode(),
                "paused": planner.is_paused(),
                "stopped": planner.is_stopped(),
            })
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
