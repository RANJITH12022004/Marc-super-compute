"""Hermes loopback client — local session + optional HTTP (stdlib only).

Marc is the only client. Loopback only (127.0.0.1:8732).
If HTTP is down, project_run falls back to a sandbox markdown note so
tests work without a Hermes binary.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import session as _session  # type: ignore
except Exception:
    _session = None  # type: ignore

try:
    import paths as _paths  # type: ignore
except Exception:
    _paths = None  # type: ignore


def base_url() -> str:
    raw = (os.environ.get("HERMES_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    return "http://127.0.0.1:8732"


HERMES_URL = base_url()
TIMEOUT = 120


def _base() -> str:
    return base_url()


def _http_get(path: str, timeout: int = 5):
    url = _base() + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return True, json.loads(body) if body.strip() else {}
            except Exception:
                return True, {"ok": True, "raw": body}
    except Exception:
        return False, None


def _http_post(path: str, payload: dict, timeout: int = TIMEOUT):
    url = _base() + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(body) if body.strip() else {}
            except Exception:
                parsed = {"ok": True, "raw": body}
            return True, parsed
    except Exception:
        return False, None


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


def _workdir_error(path) -> str:
    if _paths is not None:
        try:
            err = _paths.workdir_error(path)
            if err:
                return str(err)
        except Exception:
            pass
    return "unsafe workdir refused"


def _is_safe_goal(goal) -> bool:
    if _paths is not None:
        try:
            return bool(_paths.is_safe_goal(goal))
        except Exception:
            pass
    if goal is None or not str(goal).strip():
        return False
    lowered = str(goal).lower()
    import re as _re

    for blocked in ("reboot", "shutdown", "sudo"):
        if blocked in lowered:
            return False
    if _re.search(r"\brm\b", str(goal), _re.IGNORECASE):
        return False
    return True


def _goal_error(goal) -> str:
    if _paths is not None:
        try:
            err = _paths.goal_error(goal)
            if err:
                return str(err)
        except Exception:
            pass
    return "blocked goal refused (reboot/shutdown/sudo/rm)"


def _now_iso() -> str:
    try:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def _one_line(text: str) -> str:
    import re as _re

    return _re.sub(r"\s+", " ", str(text or "")).strip()


def project_list() -> dict:
    """Local session list + best-effort HTTP status (never fails)."""
    local = None
    if _session is not None:
        try:
            local = _session.project_list()
        except Exception:
            local = None
    if not isinstance(local, dict):
        local = {"ok": True, "projects": {}, "active": None}
    # Optional HTTP: best effort, never raises.
    try:
        ok_http, remote = _http_get("/status", timeout=5)
        if ok_http and isinstance(remote, dict):
            local = dict(local)
            local["remote"] = remote
            local["http"] = True
        else:
            local = dict(local)
            local["http"] = False
    except Exception:
        local = dict(local)
        local["http"] = False
    # Refresh module-level default (env may change in tests).
    try:
        local["url"] = _base()
    except Exception:
        pass
    return local


def project_use(slug) -> dict:
    """Activate via local session; best-effort HTTP health check."""
    if _session is None:
        return {"ok": False, "error": "hermes session unavailable"}
    try:
        result = _session.project_use(slug)
    except Exception as exc:
        return {"ok": False, "error": "project_use failed: %s" % exc}
    if not isinstance(result, dict):
        return {"ok": False, "error": "project_use failed"}
    # Optional HTTP touch — never overrides a local refusal.
    try:
        ok_http, _remote = _http_get("/health", timeout=5)
        result = dict(result)
        result["http"] = bool(ok_http)
        result["url"] = _base()
    except Exception:
        pass
    return result


def project_stop() -> dict:
    """Clear active via local session + best-effort HTTP /stop."""
    local = None
    if _session is not None:
        try:
            local = _session.project_stop()
        except Exception as exc:
            local = {"ok": False, "error": "project_stop failed: %s" % exc}
    if not isinstance(local, dict):
        local = {"ok": True, "stopped": None, "active": None}
    try:
        ok_http, remote = _http_post("/stop", {}, timeout=5)
        local = dict(local)
        local["http"] = bool(ok_http)
        if ok_http and isinstance(remote, dict):
            local["remote"] = remote
    except Exception:
        local = dict(local)
        local["http"] = False
    return local


def _sandbox_write(workdir: str, goal: str) -> dict:
    """Write sandbox note under workdir/var/hermes-last.md."""
    summary = _one_line(goal)[:500] or "hermes task"
    now = _now_iso()
    text = (
        "# Hermes sandbox run\n\n"
        "- Updated: %s\n"
        "- Goal: %s\n"
        "- Mode: sandbox (HTTP down — nothing sent)\n"
        "\n## Summary\n\n%s\n" % (now, summary, summary)
    )
    note_path = None
    try:
        base = Path(str(workdir))
        note_path = base / "var" / "hermes-last.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = note_path.parent / ("hermes-last.%d.tmp" % os.getpid())
        counter = 0
        cand = tmp
        while cand.exists():
            counter += 1
            cand = note_path.parent / ("hermes-last.%d.%d.tmp" % (os.getpid(), counter))
        tmp = cand
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, note_path)
    except Exception:
        note_path = None
    result: dict = {"ok": True, "sandbox": True, "text": summary}
    if note_path is not None:
        result["path"] = str(note_path)
    result["mode"] = "sandbox"
    return result


def project_run(goal, workdir=None) -> dict:
    """Run *goal* in *workdir* via HTTP, else sandbox note (never raises)."""
    goal_text = _one_line(goal)
    # Resolve workdir: explicit > active > refused.
    wd = str(workdir).strip() if workdir is not None else ""
    if not wd and _session is not None:
        try:
            active = _session.get_active()
            if isinstance(active, dict) and active.get("workdir"):
                wd = str(active.get("workdir") or "").strip()
            elif isinstance(active, dict) and active.get("slug"):
                # Fall back to project entry workdir via list.
                listed = _session.project_list()
                projs = listed.get("projects") if isinstance(listed, dict) else None
                if isinstance(projs, dict):
                    entry = projs.get(str(active.get("slug")) or "")
                    if isinstance(entry, dict) and entry.get("workdir"):
                        wd = str(entry.get("workdir") or "").strip()
        except Exception:
            pass
    if not _is_safe_goal(goal_text):
        return {"ok": False, "error": _goal_error(goal_text), "sandbox": False}
    if not wd or not _is_safe_workdir(wd):
        return {
            "ok": False,
            "error": _workdir_error(wd),
            "sandbox": False,
            "workdir": wd,
        }
    # Try HTTP first (loopback only, timeout 120).
    try:
        ok_http, remote = _http_post("/run", {"goal": goal_text, "workdir": wd}, timeout=TIMEOUT)
        if ok_http and isinstance(remote, dict) and remote.get("ok"):
            out = dict(remote)
            out.setdefault("sandbox", False)
            out.setdefault("workdir", wd)
            if "text" not in out and "summary" in out:
                out["text"] = out.get("summary")
            if "text" not in out:
                out["text"] = goal_text[:500]
            return out
        # If HTTP answered with explicit refusal, surface it.
        if ok_http and isinstance(remote, dict) and "ok" in remote and not remote.get("ok"):
            return {
                "ok": False,
                "error": str(remote.get("error") or "hermes refused"),
                "sandbox": False,
                "workdir": wd,
            }
    except Exception:
        pass
    # HTTP down (or no ok) -> sandbox note so tests work without binary.
    fb = _sandbox_write(wd, goal_text)
    fb["workdir"] = wd
    fb["http"] = False
    fb["url"] = _base()
    return fb


__all__ = ["project_list", "project_use", "project_run", "project_stop", "base_url"]
