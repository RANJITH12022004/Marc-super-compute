"""marc-muse HTTP service — live Muse planner on Rox loopback :8096.

Entry:  python apps/marc-muse/server.py
Bind:   MARC_MUSE_BIND : MARC_MUSE_PORT  (default 127.0.0.1:8096)
"""

import importlib.util
import json
import os
import sys
import hashlib
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

try:
    import sessions
except Exception:
    sessions = None  # type: ignore

try:
    import meta_cloud
except Exception:
    meta_cloud = None  # type: ignore

try:
    import office
except Exception:
    office = None  # type: ignore

try:
    import forms
except Exception:
    forms = None  # type: ignore

try:
    import drafts
except Exception:
    drafts = None  # type: ignore


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


# ------------------------------------------------------- webhook helpers ---

def _webhook_verify_tokens():
    """Tokens accepted for hub.verify_token (MARC_TOKEN / MARC_WEBHOOK_VERIFY)."""
    toks = []
    for key in ("MARC_TOKEN", "MARC_WEBHOOK_VERIFY"):
        try:
            v = (os.environ.get(key) or "").strip()
        except Exception:
            v = ""
        if v and v not in toks:
            toks.append(v)
    # Convenience aliases (never required, but accepted when set).
    for key in ("META_VERIFY_TOKEN", "MARC_VERIFY_TOKEN", "VERIFY_TOKEN"):
        try:
            v = (os.environ.get(key) or "").strip()
        except Exception:
            v = ""
        if v and v not in toks:
            toks.append(v)
    return toks


def _webhook_secret():
    """App secret used to verify webhook signatures (X-Hub-Signature-256)."""
    for key in (
        "MARC_WEBHOOK_SECRET",
        "META_APP_SECRET",
        "META_WEBHOOK_SECRET",
        "WHATSAPP_APP_SECRET",
        "MARC_APP_SECRET",
        "WEBHOOK_SECRET",
        "APP_SECRET",
    ):
        try:
            v = (os.environ.get(key) or "").strip()
        except Exception:
            v = ""
        if v:
            return v
    return ""


def _verify_meta_signature(raw: bytes, sig_header: str) -> bool:
    """Verify Meta X-Hub-Signature-256 header against the webhook secret.

    Returns True when no secret is configured (open mode) so local/dev and
    tests without a secret still pass. When a secret is configured the
    header must be ``sha256=<hex hmac>``.
    """
    secret = _webhook_secret()
    if not secret:
        return True
    if not sig_header:
        return False
    sig = (sig_header or "").strip()
    digest = ""
    algo = "sha256"
    if sig.startswith("sha256="):
        digest = sig[len("sha256="):].strip()
        algo = "sha256"
    elif sig.startswith("sha1="):
        digest = sig[len("sha1="):].strip()
        algo = "sha1"
    else:
        digest = sig
        algo = "sha256"
    if not digest:
        return False
    try:
        if algo == "sha1":
            expected = hmac.new(secret.encode("utf-8"), raw or b"", hashlib.sha1).hexdigest()
        else:
            expected = hmac.new(secret.encode("utf-8"), raw or b"", hashlib.sha256).hexdigest()
    except Exception:
        return False
    try:
        return hmac.compare_digest(digest.lower(), expected.lower())
    except Exception:
        return digest == expected


# Back-compat aliases for the signature helper.
_verify_signature = _verify_meta_signature
verify_signature = _verify_meta_signature
verify_webhook_signature = _verify_meta_signature


def _desk_index_path():
    """Locate desk/index.html if present, else None."""
    candidates = []
    try:
        here = Path(__file__).resolve().parent
        candidates.append(here / "desk" / "index.html")
    except Exception:
        pass
    try:
        candidates.append(Path.cwd() / "desk" / "index.html")
    except Exception:
        pass
    try:
        candidates.append(Path.cwd() / "apps" / "marc-muse" / "desk" / "index.html")
    except Exception:
        pass
    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except Exception:
            continue
    return None


def _fallback_webhook_messages(payload):
    """Best-effort WhatsApp/Cloud webhook message extractor.

    Handles the standard Cloud API shape:
    entry[].changes[].value.messages[] with text.body + from.
    """
    msgs = []
    try:
        data = payload if isinstance(payload, dict) else {}
        entries = data.get("entry")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                changes = entry.get("changes")
                if not isinstance(changes, list):
                    continue
                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    value = change.get("value")
                    if not isinstance(value, dict):
                        continue
                    for m in (value.get("messages") or []):
                        if not isinstance(m, dict):
                            continue
                        text = ""
                        t = m.get("text")
                        if isinstance(t, dict):
                            text = str(t.get("body") or t.get("text") or "")
                        elif isinstance(t, str):
                            text = t
                        if not text:
                            text = str(m.get("body") or m.get("message") or "")
                        sender = str(m.get("from") or m.get("sender") or m.get("wa_id") or "")
                        mid = str(m.get("id") or "")
                        msgs.append({"from": sender, "text": text, "id": mid,
                                     "source": "meta", "raw": m})
        if not msgs and isinstance(data.get("messages"), list):
            for m in data["messages"]:
                if isinstance(m, dict):
                    t = m.get("text")
                    if isinstance(t, dict):
                        t = t.get("body") or ""
                    msgs.append({"from": str(m.get("from") or ""),
                                 "text": str(t or m.get("body") or ""),
                                 "source": "meta", "raw": m})
                else:
                    msgs.append({"text": str(m), "source": "meta"})
        if not msgs:
            # Single-message shortcut: {"text": "...", "from": "..."}.
            if isinstance(data.get("text"), str) and data.get("text"):
                msgs.append({"from": str(data.get("from") or ""),
                             "text": data.get("text"), "source": "meta"})
            elif isinstance(data.get("text"), dict) and data["text"].get("body"):
                msgs.append({"from": str(data.get("from") or ""),
                             "text": str(data["text"].get("body") or ""),
                             "source": "meta"})
    except Exception:
        pass
    return msgs


def _call_parse_webhook(payload):
    """Call meta_cloud.parse_webhook(payload) with graceful fallback."""
    mc = globals().get("meta_cloud")
    if mc is None:
        try:
            mc = importlib.import_module("meta_cloud")
        except Exception:
            mc = None
    if mc is not None:
        try:
            fn = getattr(mc, "parse_webhook", None)
            if callable(fn):
                return fn(payload)
        except Exception:
            pass
    return None


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

    def _send_text(self, code, text):
        body = (text or "").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code, html_text):
        body = (html_text or "").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_desk(self):
        desk = _desk_index_path()
        if desk is None:
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            html = desk.read_text(encoding="utf-8")
        except Exception:
            self._send(404, {"ok": False, "error": "not found"})
            return
        self._send_html(200, html)

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

    def _read_raw(self, limit=1_000_000):
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length < 0 or length > limit:
            return None
        if length == 0:
            return b""
        try:
            return self.rfile.read(length)
        except Exception:
            return None

    def _need_auth(self):
        if not _authorized(self):
            self._send(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def _handle_meta_verify(self, parsed):
        # Meta verify: GET /webhooks/meta?hub.mode=subscribe
        #   &hub.verify_token=<token>&hub.challenge=<challenge>
        # Auth: hub.verify_token must equal MARC_TOKEN or MARC_WEBHOOK_VERIFY.
        try:
            qs = parse_qs(parsed.query or "")
        except Exception:
            qs = {}
        mode = (qs.get("hub.mode") or [""])[0]
        token = (qs.get("hub.verify_token") or [""])[0]
        challenge = (qs.get("hub.challenge") or [""])[0]
        if mode and mode != "subscribe":
            self._send(403, {"ok": False, "error": "forbidden"})
            return
        expected = _webhook_verify_tokens()
        if expected:
            ok = False
            for exp in expected:
                try:
                    if hmac.compare_digest(token or "", exp):
                        ok = True
                        break
                except Exception:
                    if (token or "") == exp:
                        ok = True
                        break
            if not ok:
                self._send(403, {"ok": False, "error": "forbidden"})
                return
        if not challenge:
            self._send(400, {"ok": False, "error": "missing hub.challenge"})
            return
        # Echo hub.challenge as plain text per Meta docs.
        self._send_text(200, challenge)

    def _handle_meta_webhook(self):
        # POST /webhooks/meta — verify signature, parse, append to daily log.
        raw = self._read_raw()
        if raw is None:
            self._send(400, {"ok": False, "error": "bad body"})
            return
        sig = (self.headers.get("X-Hub-Signature-256")
               or self.headers.get("X-Hub-Signature")
               or "")
        if not _verify_meta_signature(raw, sig):
            self._send(403, {"ok": False, "error": "bad signature"})
            return
        try:
            text = (raw or b"").decode("utf-8", "replace")
            payload = json.loads(text) if text.strip() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        messages = _call_parse_webhook(payload)
        if messages is None:
            messages = _fallback_webhook_messages(payload)
        if isinstance(messages, dict):
            if isinstance(messages.get("messages"), list):
                messages = messages.get("messages")
            else:
                messages = [messages]
        if not isinstance(messages, list):
            try:
                messages = list(messages)  # type: ignore
            except Exception:
                messages = []
        count = 0
        for m in messages:
            try:
                if isinstance(m, dict):
                    t = m.get("text")
                    if isinstance(t, dict):
                        t = t.get("body") or t.get("text") or ""
                    text_v = str(t if t is not None else (m.get("body") or ""))
                    if not text_v:
                        # Fall back to raw json for empty texts so nothing is lost.
                        try:
                            text_v = json.dumps(m, ensure_ascii=False)[:500]
                        except Exception:
                            text_v = str(m)[:500]
                    sender = str(m.get("from") or m.get("sender") or "")
                    line = ("%s: %s" % (sender, text_v)).strip() if sender else text_v.strip()
                    src = str(m.get("source") or "meta")
                else:
                    line = str(m)
                    src = "meta"
                if sessions is not None and hasattr(sessions, "append_daily"):
                    sessions.append_daily(line, source=src)
                count += 1
            except Exception:
                continue
        self._send(200, {"ok": True, "count": count})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = (parsed.path or "/").rstrip("/") or "/"
        if path == "/webhooks/meta":
            self._handle_meta_verify(parsed)
            return
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
        if path == "/island":
            if not self._need_auth():
                return
            try:
                import island
                body = island.snapshot()
                body["ok"] = True
            except Exception:
                body = {"ok": True, "state": "idle", "line": "", "agents": []}
            self._send(200, body)
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
        if path == "/drafts":
            if not self._need_auth():
                return
            if drafts is None or not hasattr(drafts, "list_drafts"):
                self._send(503, {"ok": False, "error": "drafts missing"})
                return
            try:
                qs = parse_qs(parsed.query or "")
            except Exception:
                qs = {}
            status = (qs.get("status") or [""])[0] if qs else ""
            if not status:
                status = (qs.get("filter") or [""])[0] if qs else ""
            try:
                if status:
                    items = drafts.list_drafts(status=status)
                else:
                    items = drafts.list_drafts()
            except TypeError:
                try:
                    items = drafts.list_drafts()
                except Exception as exc:
                    self._send(500, {"ok": False, "error": str(exc)})
                    return
            except Exception as exc:
                self._send(500, {"ok": False, "error": str(exc)})
                return
            self._send(200, {"ok": True, "drafts": items})
            return
        if path == "/forms/demo":
            if not self._need_auth():
                return
            demo = None
            if forms is not None and hasattr(forms, "demo_html_path"):
                try:
                    demo = Path(forms.demo_html_path())
                except Exception:
                    demo = None
            if demo is None:
                demo = Path(__file__).resolve().parent / "sandbox" / "forms" / "demo.html"
            if not demo.is_file():
                self._send(404, {"ok": False, "error": "demo form missing"})
                return
            html = demo.read_text(encoding="utf-8")
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/", "/desk", "/desk/index.html", "/index.html"):
            self._serve_desk()
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/webhooks/meta":
            self._handle_meta_webhook()
            return
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
        if path == "/utterance":
            data = self._read_json()
            text = data.get("text") or ""
            if not str(text).strip():
                self._send(400, {"ok": False, "error": "empty text"})
                return
            context = data.get("context") or os.environ.get("MARC_CONTEXT") or "desk"
            source = data.get("source") or data.get("session_id") or "phone"
            try:
                import island
                island.set_state("listen")
            except Exception:
                pass
            result = planner.plan(
                text=text,
                session_id=source,
                target=data.get("target", "auto"),
                note=data.get("note", ""),
                context=context,
            )
            plan = result.get("plan") or []
            try:
                import island
                island.set_state("plan")
                names = []
                import agents as _ag
                names = [a.get("name") for a in _ag.spawn(plan)]
                island.set_state("wave", agents=names)
                if any(s.get("confirm") for s in plan):
                    island.set_state("confirm", agents=names)
            except Exception:
                pass
            snap = {}
            try:
                import island
                snap = island.snapshot()
            except Exception:
                snap = {}
            self._send(200, {
                "ok": True,
                "reply": result.get("reply", ""),
                "session_id": result.get("session_id") or source,
                "plan": plan,
                "island": snap,
                "source": source,
                "context": context,
            })
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
        if path == "/office":
            if office is None:
                self._send(503, {"ok": False, "error": "office missing"})
                return
            data = self._read_json()
            self._send(200, office.start_task(data.get("goal") or data.get("text") or ""))
            return
        if path in ("/office/stop", "/office/stop/"):
            if office is None:
                self._send(503, {"ok": False, "error": "office missing"})
                return
            data = self._read_json()
            self._send(200, office.stop_task(data.get("id") or data.get("task_id") or ""))
            return
        if path == "/forms/fill":
            if forms is None:
                self._send(503, {"ok": False, "error": "forms missing"})
                return
            data = self._read_json()
            html_path = data.get("html_path") or data.get("path")
            values = data.get("values") or data
            self._send(200, forms.fill(html_path, values if isinstance(values, dict) else {}))
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
