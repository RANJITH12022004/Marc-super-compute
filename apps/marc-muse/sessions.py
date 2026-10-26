"""Session markdown store — markdown is the soul, json is the machine.

Persists under ``MARC_MIND_DIR`` (default ``./var/mind``)::

    <mind>/
      NOW.md
      daily/YYYY-MM-DD.md
      sessions/{safe_id}.md
      people/
      projects/
      style/
      audit/YYYY-MM-DD.md

All writes are atomic (tmp + os.replace) and guarded by a thread lock.
Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path

_LOCK = threading.RLock()

_SUBDIRS = ("daily", "sessions", "people", "projects", "style", "audit")

_NOW_KEYS = ("Focus", "Last", "Open", "Office", "Updated")

_FOLLOWUP_EXACT = frozenset(
    {
        "send it",
        "send",
        "the first",
        "the first one",
        "first one",
        "continue",
        "next",
        "do it",
        "go ahead",
        "yes send",
        "send that",
    }
)
_FOLLOWUP_HINTS = ("send it", "the first", "continue")


# ---------------------------------------------------------------- dirs ---

def mind_dir() -> Path:
    """Return the mind vault directory from env (``MARC_MIND_DIR``)."""
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path(raw.strip() or "./var/mind")


def _today() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    try:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def _atomic_write(path: Path, text: str) -> None:
    """Write *text* to *path* atomically (tmp file + os.replace)."""
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / (path.name + ".%d.tmp" % os.getpid())
    # Unique-ish tmp when threads collide.
    counter = 0
    candidate = tmp
    while candidate.exists():
        counter += 1
        candidate = parent / ("%s.%d.%d.tmp" % (path.name, os.getpid(), counter))
    tmp = candidate
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def _default_now_text() -> str:
    return (
        "# NOW\n"
        "\n"
        "Focus: \n"
        "Last: \n"
        "Open: \n"
        "Office: \n"
        "Updated: %s\n" % _now_iso()
    )


def ensure_vault() -> Path:
    """Create the vault dirs + NOW.md. Returns the mind dir Path."""
    with _LOCK:
        base = mind_dir()
        base.mkdir(parents=True, exist_ok=True)
        for sub in _SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
        now_path = base / "NOW.md"
        if not now_path.exists():
            _atomic_write(now_path, _default_now_text())
        return base


def _now_path() -> Path:
    return mind_dir() / "NOW.md"


# ---------------------------------------------------------------- NOW ----

def _parse_now(text: str) -> dict[str, str]:
    data: dict[str, str] = {k: "" for k in _NOW_KEYS}
    for line in (text or "").splitlines():
        stripped = line.strip()
        for key in _NOW_KEYS:
            prefix = key + ":"
            if stripped.startswith(prefix):
                data[key] = stripped[len(prefix):].strip()
                break
    return data


def _render_now(data: dict[str, str]) -> str:
    lines = ["# NOW", ""]
    for key in _NOW_KEYS:
        lines.append("%s: %s" % (key, (data.get(key) or "").strip()))
    return "\n".join(lines) + "\n"


def _read_now() -> dict[str, str]:
    ensure_vault()
    try:
        text = _now_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {k: "" for k in _NOW_KEYS}
    except OSError:
        return {k: "" for k in _NOW_KEYS}
    return _parse_now(text)


def _write_now(data: dict[str, str]) -> None:
    ensure_vault()
    _atomic_write(_now_path(), _render_now(data))


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def set_focus(text: str) -> str:
    """Set the Focus line in NOW.md. Returns the stored value."""
    value = _one_line(text)
    with _LOCK:
        data = _read_now()
        data["Focus"] = value
        data["Updated"] = _now_iso()
        _write_now(data)
    return value


def set_open(text: str) -> str:
    """Set the Open line in NOW.md. Returns the stored value."""
    value = _one_line(text)
    with _LOCK:
        data = _read_now()
        data["Open"] = value
        data["Updated"] = _now_iso()
        _write_now(data)
    return value


def set_office(text: str) -> str:
    """Set the Office line in NOW.md. Returns the stored value."""
    value = _one_line(text)
    with _LOCK:
        data = _read_now()
        data["Office"] = value
        data["Updated"] = _now_iso()
        _write_now(data)
    return value


def set_last(text: str) -> str:
    """Append to the Last line, keeping only the last 3 entries."""
    value = _one_line(text)
    with _LOCK:
        data = _read_now()
        existing = (data.get("Last") or "").strip()
        if existing:
            parts = [p.strip() for p in existing.split(" | ")]
            parts = [p for p in parts if p]
        else:
            parts = []
        if value:
            parts.append(value)
        parts = parts[-3:]
        data["Last"] = " | ".join(parts)
        data["Updated"] = _now_iso()
        _write_now(data)
    return data["Last"]


def get_now() -> dict[str, str]:
    """Return the parsed NOW.md mapping."""
    with _LOCK:
        return _read_now()


def now_speak() -> str:
    """Human-readable summary of NOW.md (Focus/Last/Open/Office/Updated)."""
    with _LOCK:
        data = _read_now()
    focus = (data.get("Focus") or "").strip()
    last = (data.get("Last") or "").strip()
    open_v = (data.get("Open") or "").strip()
    office = (data.get("Office") or "").strip()
    updated = (data.get("Updated") or "").strip()
    parts: list[str] = []
    if focus:
        parts.append("Focus is %s." % focus)
    else:
        parts.append("No focus set.")
    if last:
        parts.append("Last: %s." % last)
    else:
        parts.append("Nothing done yet.")
    if open_v:
        parts.append("Open: %s." % open_v)
    if office:
        parts.append("Office: %s." % office)
    if updated:
        parts.append("Updated %s." % updated)
    return " ".join(parts)


# --------------------------------------------------------------- daily ---

def append_daily(line: str, source: str = "") -> Path:
    """Append *line* to ``daily/YYYY-MM-DD.md``. Returns the file path."""
    text = _one_line(line)
    src = _one_line(source)
    with _LOCK:
        ensure_vault()
        path = mind_dir() / "daily" / ("%s.md" % _today())
        stamp = datetime.now().strftime("%H:%M")
        if src:
            entry = "- [%s] (%s) %s\n" % (stamp, src, text)
        else:
            entry = "- [%s] %s\n" % (stamp, text)
        if not path.exists():
            header = "# %s\n\n" % _today()
            _atomic_write(path, header + entry)
        else:
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                existing = ""
            if not existing.endswith("\n") and existing:
                existing += "\n"
            _atomic_write(path, existing + entry)
        return path


# ------------------------------------------------------------ sessions ---

_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def safe_session_id(session_id: str) -> str:
    """Sanitize *session_id* for use as a filename."""
    cleaned = _SAFE_RE.sub("_", str(session_id or "").strip()).strip("_")
    if not cleaned:
        cleaned = "session"
    return cleaned[:120]


def session_path(session_id: str) -> Path:
    """Return the markdown path for *session_id* (no followup resolving)."""
    return mind_dir() / "sessions" / ("%s.md" % safe_session_id(session_id))


def _extract_json_block(text: str) -> dict | None:
    m = re.search(r"```json\s*\n(.*?)```", text or "", re.S)
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def save_session(session_id: str, payload: dict) -> Path:
    """Save *payload* to ``sessions/{safe_id}.md`` as markdown + fenced json."""
    if not isinstance(payload, dict):
        try:
            payload = dict(payload)  # type: ignore[arg-type]
        except Exception:
            payload = {"value": payload}
    sid = str(session_id or "").strip() or "session"
    with _LOCK:
        ensure_vault()
        path = session_path(sid)
        try:
            body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception:
            body = json.dumps({"value": str(payload)}, indent=2)
        updated = _now_iso()
        reply = _one_line(str(payload.get("reply", "")))[:500]
        lines = ["# Session %s" % sid, ""]
        lines.append("- Updated: %s" % updated)
        lines.append("- ID: %s" % sid)
        lines.append("")
        if reply:
            lines.append("## Reply")
            lines.append("")
            lines.append(reply)
            lines.append("")
        plan = payload.get("plan")
        if isinstance(plan, list) and plan:
            lines.append("## Plan")
            lines.append("")
            for i, step in enumerate(plan, 1):
                if isinstance(step, dict):
                    tool = str(step.get("tool", "?"))
                    device = str(step.get("device", ""))
                    label = "%s" % tool
                    if device:
                        label += " (%s)" % device
                    detail = ""
                    args = step.get("args")
                    if isinstance(args, dict):
                        detail = _one_line(json.dumps(args, ensure_ascii=False))[:300]
                    if detail:
                        lines.append("%d. %s — %s" % (i, label, detail))
                    else:
                        lines.append("%d. %s" % (i, label))
                else:
                    lines.append("%d. %s" % (i, _one_line(str(step))[:300]))
            lines.append("")
        lines.append("## Payload")
        lines.append("")
        lines.append("```json")
        lines.append(body)
        lines.append("```")
        lines.append("")
        _atomic_write(path, "\n".join(lines))
        return path


def _load_session_file(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    payload = _extract_json_block(text)
    if payload is not None:
        return payload
    # Fallback: whole file is raw json.
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _iter_session_files() -> list[Path]:
    base = mind_dir() / "sessions"
    try:
        files = [p for p in base.glob("*.md") if p.is_file()]
    except OSError:
        return []
    # Newest first.
    try:
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files.sort(key=lambda p: p.name, reverse=True)
    return files


def latest_session_id() -> str | None:
    """Return the safe id stem of the most recently modified session."""
    with _LOCK:
        files = _iter_session_files()
    if not files:
        return None
    return files[0].stem


def latest_session() -> dict | None:
    """Return the payload of the most recently modified session, or None."""
    with _LOCK:
        files = _iter_session_files()
        if not files:
            return None
        first = files[0]
        return _load_session_file(first)


def is_followup(text: str) -> bool:
    """Return True when *text* looks like a followup ('send it', ...)."""
    norm = _one_line(text).lower()
    if not norm:
        return False
    if norm in _FOLLOWUP_EXACT:
        return True
    if len(norm) <= 40 and any(h in norm for h in _FOLLOWUP_HINTS):
        return True
    return False


def resolve_session(session_id: str) -> dict | None:
    """Load *session_id*, resolving followup phrases to the latest session."""
    if is_followup(session_id):
        return latest_session()
    return load_session(session_id)


def load_session(session_id: str) -> dict | None:
    """Load a session payload by id.

    Followup phrases like ``send it`` / ``the first`` / ``continue``
    resolve to the latest session.
    """
    sid = str(session_id or "").strip()
    if not sid:
        return None
    if is_followup(sid):
        return latest_session()
    with _LOCK:
        ensure_vault()
        path = session_path(sid)
        return _load_session_file(path)


# --------------------------------------------------------------- audit ---

def record_audit(event: str, detail: str = "") -> Path:
    """Append an audit line to ``audit/YYYY-MM-DD.md``. Returns the path."""
    ev = _one_line(event)
    det = _one_line(detail)
    with _LOCK:
        ensure_vault()
        path = mind_dir() / "audit" / ("%s.md" % _today())
        stamp = _now_iso()
        if det:
            entry = "- [%s] %s: %s\n" % (stamp, ev, det)
        else:
            entry = "- [%s] %s\n" % (stamp, ev)
        if not path.exists():
            header = "# Audit %s\n\n" % _today()
            _atomic_write(path, header + entry)
        else:
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                existing = ""
            if existing and not existing.endswith("\n"):
                existing += "\n"
            _atomic_write(path, existing + entry)
        return path


__all__ = [
    "mind_dir",
    "ensure_vault",
    "set_focus",
    "set_open",
    "set_office",
    "set_last",
    "get_now",
    "now_speak",
    "append_daily",
    "safe_session_id",
    "session_path",
    "save_session",
    "load_session",
    "latest_session",
    "latest_session_id",
    "is_followup",
    "resolve_session",
    "record_audit",
]
