"""Hermes loopback session — one active slug+workdir (stdlib only).

Marc is the only client. Loopback only.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import paths as _paths  # type: ignore
except Exception:
    _paths = None  # type: ignore


def _hermes_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _projects_file() -> str:
    override = (os.environ.get("HERMES_PROJECTS_FILE") or "").strip()
    if override:
        return override
    return os.path.join(_hermes_dir(), "projects.json")


def _load_projects() -> dict:
    path = _projects_file()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _is_safe_workdir(path) -> bool:
    if _paths is not None:
        try:
            return bool(_paths.is_safe_workdir(path))
        except Exception:
            pass
    # Fallback mirror of paths.is_safe_workdir.
    if path is None:
        return False
    text = str(path).strip()
    if not text:
        return False
    if text in ("/", "//"):
        return False
    normalized = text.replace("\\", "/")
    if normalized in ("/", "//"):
        return False
    if "mark-laptop" in text or "mark-laptop" in normalized:
        return False
    if "/home/rox/marc/android" in text or "/home/rox/marc/android" in normalized:
        return False
    return True


def _workdir_error(path) -> str:
    if _paths is not None:
        try:
            err = _paths.workdir_error(path)
            if err is None:
                return ""
            return str(err)
        except Exception:
            pass
    if path is None or not str(path).strip():
        return "empty workdir refused"
    text = str(path).strip()
    if text in ("/", "//"):
        return "root workdir refused"
    return "unsafe workdir refused"


# One active slug+workdir for the process.
_ACTIVE: dict = {"slug": None, "workdir": None}


def get_active() -> dict | None:
    slug = _ACTIVE.get("slug")
    workdir = _ACTIVE.get("workdir")
    if not slug:
        return None
    return {"slug": slug, "workdir": workdir}


def project_list() -> dict:
    projects = _load_projects()
    active = get_active()
    return {"ok": True, "projects": projects, "active": active}


def project_status() -> dict:
    active = get_active()
    return {"ok": True, "active": active}


def project_use(slug) -> dict:
    """Activate *slug*; stop previous. Refuse unknown/unsafe workdirs."""
    name = str(slug or "").strip()
    if not name:
        return {"ok": False, "error": "empty slug refused"}
    projects = _load_projects()
    if name not in projects:
        return {"ok": False, "error": "unknown project: %s" % name, "slug": name}
    entry = projects.get(name) or {}
    workdir = entry.get("workdir") if isinstance(entry, dict) else None
    if not _is_safe_workdir(workdir):
        return {
            "ok": False,
            "error": _workdir_error(workdir) or "unsafe workdir refused",
            "slug": name,
            "workdir": workdir,
        }
    previous = _ACTIVE.get("slug")
    prev_workdir = _ACTIVE.get("workdir")
    stopped = None
    if previous and previous != name:
        stopped = {"slug": previous, "workdir": prev_workdir, "stopped": True}
    _ACTIVE["slug"] = name
    _ACTIVE["workdir"] = workdir
    result: dict = {"ok": True, "slug": name, "workdir": workdir, "active": get_active()}
    if stopped is not None:
        result["previous"] = stopped
        result["previous_stopped"] = True
    else:
        result["previous"] = None
    return result


def project_stop() -> dict:
    """Clear active project."""
    prev = get_active()
    _ACTIVE["slug"] = None
    _ACTIVE["workdir"] = None
    return {"ok": True, "stopped": prev, "active": None}


__all__ = [
    "project_list",
    "project_use",
    "project_stop",
    "project_status",
    "get_active",
]
