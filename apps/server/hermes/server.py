"""Hermes loopback HTTP server (stdlib http.server, stdlib only).

- Binds 127.0.0.1:8732 (HERMES_BIND/HERMES_PORT). Never 0.0.0.0. Never funnel.
- Marc is the only client. Loopback only.
- GET  /health -> {ok:true}
- GET  /status -> {ok:true, active}
- POST /stop   -> clears active
- POST /run    -> JSON {goal, workdir}; validates safety, records run.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import paths as _paths  # type: ignore
except Exception:
    _paths = None  # type: ignore

try:
    import session as _session  # type: ignore
except Exception:
    _session = None  # type: ignore


def bind_host() -> str:
    # Loopback only. Never 0.0.0.0.
    raw = (os.environ.get("HERMES_BIND") or "").strip()
    if raw and raw != "127.0.0.1" and raw.lower() != "localhost":
        return "127.0.0.1"
    return "127.0.0.1"


def bind_port() -> int:
    raw = (os.environ.get("HERMES_PORT") or "").strip()
    if raw:
        try:
            port = int(raw)
            if 1 <= port <= 65535:
                return port
        except ValueError:
            pass
    return 8732


def _is_safe_workdir(path) -> bool:
    if _paths is not None:
        try:
            return bool(_paths.is_safe_workdir(path))
        except Exception:
            pass
    if path is None:
        return False
    text = str(path).strip()
    if not text or text in ("/", "//"):
        return False
    norm = text.replace("\\", "/")
    if "mark-laptop" in text or "mark-laptop" in norm:
        return False
    if "/home/rox/marc/android" in text or "/home/rox/marc/android" in norm:
        return False
    return True


def _is_safe_goal(goal) -> bool:
    if _paths is not None:
        try:
            return bool(_paths.is_safe_goal(goal))
        except Exception:
            pass
    if goal is None or not str(goal).strip():
        return False
    import re as _re

    lowered = str(goal).lower()
    for blocked in ("reboot", "shutdown", "sudo"):
        if blocked in lowered:
            return False
    if _re.search(r"\brm\b", str(goal), _re.IGNORECASE):
        return False
    return True


def _mind_dir_from_payload(payload: dict) -> str:
    raw = ""
    try:
        raw = str(payload.get("mind_dir") or payload.get("path") or "").strip()
    except Exception:
        raw = ""
    if not raw:
        raw = (os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "").strip()
    if not raw:
        raw = "./var/mind"
    if not _is_safe_workdir(raw):
        return ""
    return raw


def _run_mind_job(kind: str, payload: dict) -> dict:
    """Run mind_* / laptop_home_ingest under mind dir only."""
    mind = _mind_dir_from_payload(payload)
    if not mind:
        return {"ok": False, "error": "unsafe mind_dir refused", "kind": kind}
    job_id = str(payload.get("id") or payload.get("job_id") or kind)
    path = str(payload.get("export") or payload.get("file") or "").strip()
    try:
        muse_brain = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "marc-muse",
        )
        if muse_brain not in sys.path:
            sys.path.insert(0, muse_brain)
    except Exception:
        pass
    status = "done"
    detail = ""
    try:
        if kind == "mind_reindex":
            from brain import index as _idx  # type: ignore

            n = _idx.rebuild(mind)
            _idx.record_job(job_id, kind, "done", mind, mind_dir=mind)
            detail = "rebuilt %s chunks" % n
        elif kind == "mind_ingest":
            from brain import index as _idx  # type: ignore

            if path and _is_safe_workdir(path):
                try:
                    import ingest as _ingest  # type: ignore

                    if hasattr(_ingest, "ingest_path"):
                        _ingest.ingest_path(path)
                except Exception as exc:
                    detail = "ingest err: %s" % str(exc)[:120]
            source = str(payload.get("source") or "").strip().lower()
            if source in ("github", "gh", "all"):
                try:
                    from connectors import github as _gh  # type: ignore

                    _gh.ingest_repos(mind_dir=mind)
                except Exception as exc:
                    detail = (detail + "; " if detail else "") + "github: %s" % str(exc)[:80]
            if source in ("gmail", "mail", "google", "all"):
                try:
                    from connectors import google as _google  # type: ignore

                    _google.fetch_mail_digest(mind_dir=mind)
                except Exception as exc:
                    detail = (detail + "; " if detail else "") + "mail: %s" % str(exc)[:80]
            n = _idx.rebuild(mind)
            _idx.record_job(job_id, kind, "done", path or mind, mind_dir=mind)
            detail = detail or ("ingest+reindex %s" % n)
        elif kind == "style_distill":
            from brain import index as _idx  # type: ignore

            if path and _is_safe_workdir(path):
                try:
                    import ingest as _ingest  # type: ignore

                    if hasattr(_ingest, "ingest_path"):
                        _ingest.ingest_path(path)
                except Exception as exc:
                    detail = "distill err: %s" % str(exc)[:120]
            _idx.ensure_schema(mind)
            _idx.record_job(job_id, kind, "done", path or mind, mind_dir=mind)
            detail = detail or "style_distill ok"
        elif kind == "laptop_home_ingest":
            from brain import index as _idx  # type: ignore
            from brain import laptop_ingest as _li  # type: ignore

            home = str(payload.get("home") or payload.get("root") or "").strip() or None
            if home and not _is_safe_workdir(home):
                return {"ok": False, "error": "unsafe home refused", "kind": kind}
            res = _li.walk_home(root=home, mind_dir=mind)
            count = 0
            if isinstance(res, dict):
                try:
                    count = int(res.get("count") or res.get("ingested") or 0)
                except Exception:
                    count = 0
                detail = str(res.get("error") or ("laptop ingested %s" % count))
            else:
                detail = "laptop_home_ingest ok"
            _idx.record_job(job_id, kind, "done" if (isinstance(res, dict) and res.get("ok", True)) else "error",
                            home or mind, mind_dir=mind)
            return {
                "ok": bool(isinstance(res, dict) and res.get("ok", True)),
                "kind": kind,
                "status": "done",
                "text": detail,
                "summary": detail,
                "mind_dir": mind,
                "id": job_id,
                "result": res if isinstance(res, dict) else {},
            }
        else:
            return {"ok": False, "error": "unknown kind", "kind": kind}
    except Exception as exc:
        status = "error"
        detail = str(exc)[:200]
        return {"ok": False, "kind": kind, "status": status, "error": detail, "mind_dir": mind}
    return {
        "ok": True,
        "kind": kind,
        "status": status,
        "text": detail,
        "summary": detail,
        "mind_dir": mind,
        "id": job_id,
    }


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except Exception:
        length = 0
    if length <= 0:
        return {}
    try:
        raw = handler.rfile.read(length)
    except Exception:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesLoopback/1.0"

    def log_message(self, fmt, *args):  # quiet
        return

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):  # noqa: N802
        path = (self.path or "").split("?", 1)[0]
        if path == "/health":
            self._send({"ok": True})
            return
        if path == "/status":
            active = None
            if _session is not None:
                try:
                    active = _session.get_active()
                except Exception:
                    active = None
            self._send({"ok": True, "active": active})
            return
        self._send({"ok": False, "error": "not found"}, status=404)

    def do_POST(self):  # noqa: N802
        path = (self.path or "").split("?", 1)[0]
        if path == "/stop":
            # Drain body if present.
            try:
                _read_json(self)
            except Exception:
                pass
            stopped = None
            if _session is not None:
                try:
                    res = _session.project_stop()
                    stopped = res.get("stopped") if isinstance(res, dict) else None
                except Exception:
                    stopped = None
            self._send({"ok": True, "stopped": stopped, "active": None})
            return
        if path == "/run":
            payload = _read_json(self)
            kind = str(payload.get("kind") or payload.get("job") or "").strip().lower()
            if kind in (
                "mind_ingest",
                "mind_reindex",
                "style_distill",
                "laptop_home_ingest",
            ):
                self._send(_run_mind_job(kind, payload))
                return
            goal = payload.get("goal", "")
            workdir = payload.get("workdir", "")
            # Default workdir to active if not supplied.
            if (not str(workdir or "").strip()) and _session is not None:
                try:
                    active = _session.get_active()
                    if isinstance(active, dict) and active.get("workdir"):
                        workdir = active.get("workdir")
                except Exception:
                    pass
            import re as _re

            goal_text = _re.sub(r"\s+", " ", str(goal or "")).strip()
            wd_text = str(workdir or "").strip()
            if not _is_safe_goal(goal_text):
                err = "blocked goal refused (reboot/shutdown/sudo/rm)"
                if _paths is not None:
                    try:
                        err = str(_paths.goal_error(goal_text) or err)
                    except Exception:
                        pass
                self._send({"ok": False, "error": err}, status=400)
                return
            if not _is_safe_workdir(wd_text):
                err = "unsafe workdir refused"
                if _paths is not None:
                    try:
                        err = str(_paths.workdir_error(wd_text) or err)
                    except Exception:
                        pass
                self._send({"ok": False, "error": err}, status=400)
                return
            summary = goal_text[:500]
            self._send(
                {
                    "ok": True,
                    "sandbox": False,
                    "text": summary,
                    "summary": summary,
                    "workdir": wd_text,
                    "goal": goal_text,
                }
            )
            return
        self._send({"ok": False, "error": "not found"}, status=404)


def run(host: str = "127.0.0.1", port: int = 8732) -> None:
    # Enforce loopback: never bind 0.0.0.0.
    if not host or host == "0.0.0.0" or host.strip() == "":
        host = "127.0.0.1"
    host = host.strip()
    if host != "127.0.0.1" and host.lower() != "localhost":
        host = "127.0.0.1"
    server = HTTPServer((host, int(port)), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> int:
    run(bind_host(), bind_port())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Handler", "run", "main", "bind_host", "bind_port"]
