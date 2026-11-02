"""MARC laptop worker (Windows, no model).

Small stdlib-only HTTP worker. No ML, no bee-island imports.

Endpoints:
  GET  /health -> {"ok": true, "device": "laptop"}
  POST /run    JSON {"tool": ..., "args": {...}} -> allowlist-dispatched result.

Env:
  MARC_LAPTOP_PORT  port to bind (default 8765), bind is always 0.0.0.0
  MARC_TOKEN        optional shared secret; when set, client must send it
                    via `X-MARC-Token` header, `X-Token` header,
                    `Authorization: Bearer <token>`, or JSON body `token` field.
  MARC_MODE=sandbox simulate side effects (no startfile/pyautogui calls).

Allowlist:
  open_app  -> Windows os.startfile(label). Simulated when sandbox.
  type_into -> NOT implemented live (pyautogui later); simulated ok in sandbox,
               ok:false live.
Everything else (including reboot/shutdown/sudo/rm) is refused with ok:false.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

DEVICE = "laptop"
DEFAULT_PORT = 8765

ALLOWED_TOOLS = {"open_app", "type_into"}

# Explicitly refused even if someone adds them to the allowlist later.
DENIED_TOOLS = {
    "reboot",
    "shutdown",
    "sudo",
    "rm",
    "reboot_system",
    "poweroff",
    "halt",
    "format",
}


def is_sandbox() -> bool:
    return os.environ.get("MARC_MODE", "").strip().lower() == "sandbox"


def get_port() -> int:
    try:
        return int(os.environ.get("MARC_LAPTOP_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


def get_expected_token() -> str:
    return os.environ.get("MARC_TOKEN", "")


def check_auth(headers, body_token: str = "") -> bool:
    """Return True if request is authorized.

    When MARC_TOKEN is unset/empty, auth is disabled (open).
    When set, one of the token carriers must match exactly.
    """
    expected = get_expected_token()
    if not expected:
        return True

    candidates = []
    if headers is not None:
        # headers may be http.client.HTTPMessage (case-insensitive get)
        # or a plain dict in tests.
        get = getattr(headers, "get", None)
        if callable(get):
            try:
                candidates.append(headers.get("X-MARC-Token", ""))
            except Exception:
                pass
            try:
                candidates.append(headers.get("X-Token", ""))
            except Exception:
                pass
            try:
                auth = headers.get("Authorization", "")
            except Exception:
                auth = ""
            if auth and auth.lower().startswith("bearer "):
                candidates.append(auth[7:].strip())
            else:
                candidates.append(auth)
        elif isinstance(headers, dict):
            lowered = {str(k).lower(): v for k, v in headers.items()}
            candidates.append(lowered.get("x-marc-token", ""))
            candidates.append(lowered.get("x-token", ""))
            auth = lowered.get("authorization", "")
            if isinstance(auth, str) and auth.lower().startswith("bearer "):
                candidates.append(auth[7:].strip())
            else:
                candidates.append(auth)
    if body_token:
        candidates.append(body_token)

    return any(c == expected for c in candidates if c)


def health_payload() -> dict:
    return {"ok": True, "device": DEVICE}


def handle_run(tool, args) -> tuple[int, dict]:
    """Core dispatch. Returns (http_status, payload).

    Never raises for bad input; always returns ok:false payload on refusal.
    """
    if not isinstance(tool, str) or not tool.strip():
        return 400, {"ok": False, "error": "missing tool"}

    name = tool.strip().lower()

    # Explicit deny-list first so intent is obvious in logs/tests.
    if name in DENIED_TOOLS:
        return 403, {"ok": False, "error": f"refused: {tool}"}

    if name not in ALLOWED_TOOLS:
        return 400, {"ok": False, "error": f"unknown tool: {tool}"}

    if not isinstance(args, dict):
        args = {} if args is None else {"value": args}

    if name == "open_app":
        label = (
            args.get("label")
            or args.get("app")
            or args.get("name")
            or args.get("path")
            or ""
        )
        if not isinstance(label, str) or not label.strip():
            return 400, {"ok": False, "error": "missing label"}
        label = label.strip()
        # Refuse dangerous labels that map to denied tools.
        if label.strip().lower() in DENIED_TOOLS:
            return 403, {"ok": False, "error": f"refused: {label}"}
        if is_sandbox():
            return 200, {
                "ok": True,
                "simulated": True,
                "tool": "open_app",
                "label": label,
            }
        startfile = getattr(os, "startfile", None)
        if callable(startfile):
            try:
                startfile(label)
            except Exception as exc:  # e.g. file not found
                return 500, {"ok": False, "error": f"open_app failed: {exc}"}
            return 200, {"ok": True, "tool": "open_app", "label": label}
        return 501, {
            "ok": False,
            "error": "open_app only supported on Windows (os.startfile missing)",
        }

    if name == "type_into":
        # pyautogui integration comes later; live mode cannot type.
        if is_sandbox():
            return 200, {
                "ok": True,
                "simulated": True,
                "tool": "type_into",
                "args": args,
            }
        return 501, {
            "ok": False,
            "error": "type_into not implemented (pyautogui later)",
        }

    # Unreachable given allowlist check, kept for safety.
    return 400, {"ok": False, "error": f"unknown tool: {tool}"}


class LaptopHandler(BaseHTTPRequestHandler):
    server_version = "MARC-Laptop/1.0"

    def log_message(self, fmt, *args):  # keep stdlib logging to stderr
        import sys

        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_json(200, health_payload())
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/run":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            self._send_json(400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(data, dict):
            self._send_json(400, {"ok": False, "error": "body must be a JSON object"})
            return

        body_token = data.get("token", "") if isinstance(data.get("token"), str) else ""
        if not check_auth(self.headers, body_token):
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        status, payload = handle_run(data.get("tool"), data.get("args", {}))
        self._send_json(status, payload)


def run() -> None:
    port = get_port()
    httpd = HTTPServer(("0.0.0.0", port), LaptopHandler)
    print(f"MARC laptop worker on 0.0.0.0:{port} (sandbox={is_sandbox()})", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
