"""Drafts queue -- file-backed, sandbox-safe (stdlib only).

Drafts live as markdown files under ``MARC_MIND_DIR/drafts/{id}.md`` with
YAML-like header fields Channel, Person, Mouth, Status, Body.

``enqueue`` never sends. ``confirm`` in sandbox sets status
``sent-sandbox`` and does not call network. ``block`` sets ``blocked``.
All writes are atomic (tmp + os.replace) and guarded by a thread lock.
"""

from __future__ import annotations

import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

_LOCK = threading.RLock()

_VALID_MOUTH = ("personal", "business")
_VALID_STATUS = ("queued", "confirmed", "sent-sandbox", "blocked")

_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def mind_dir() -> Path:
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path((raw or "").strip() or "./var/mind")


def drafts_dir() -> Path:
    return mind_dir() / "drafts"


def _ensure_drafts_dir() -> Path:
    path = drafts_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    try:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def _is_sandbox(mode=None) -> bool:
    if mode is not None:
        return str(mode or "").strip().lower() == "sandbox"
    raw = os.environ.get("MARC_MODE") or os.environ.get("MODE") or "sandbox"
    return str(raw or "").strip().lower() == "sandbox"


def _new_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return "%s-%s" % (stamp, suffix)


def safe_draft_id(draft_id: str) -> str:
    cleaned = _SAFE_RE.sub("_", str(draft_id or "").strip()).strip("_")
    if not cleaned:
        cleaned = _new_id()
    return cleaned[:120]


def draft_path(draft_id: str) -> Path:
    return drafts_dir() / ("%s.md" % safe_draft_id(draft_id))


def write_file(path, text: str) -> Path:
    target = Path(path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / ("%s.%d.tmp" % (target.name, os.getpid()))
    counter = 0
    candidate = tmp
    while candidate.exists():
        counter += 1
        candidate = parent / ("%s.%d.%d.tmp" % (target.name, os.getpid(), counter))
    tmp = candidate
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, target)
    return target


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_mouth(mouth) -> str:
    m = str(mouth or "personal").strip().lower() or "personal"
    if m in _VALID_MOUTH:
        return m
    return "personal"


def _normalize_status(status) -> str:
    s = str(status or "queued").strip().lower() or "queued"
    if s in _VALID_STATUS:
        return s
    return "queued"


def _render_draft(data: dict) -> str:
    draft_id = str(data.get("id") or "").strip() or _new_id()
    channel = _one_line(data.get("channel", ""))
    person = _one_line(data.get("person", ""))
    mouth = _normalize_mouth(data.get("mouth"))
    status = _normalize_status(data.get("status"))
    created = str(data.get("created") or _now_iso())
    updated = str(data.get("updated") or created)
    reason = _one_line(data.get("reason", ""))
    body = str(data.get("body", "") or "").strip("\n")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    lines = ["# Draft %s" % draft_id, ""]
    lines.append("Channel: %s" % channel)
    lines.append("Person: %s" % person)
    lines.append("Mouth: %s" % mouth)
    lines.append("Status: %s" % status)
    lines.append("Id: %s" % draft_id)
    lines.append("Created: %s" % created)
    lines.append("Updated: %s" % updated)
    if reason:
        lines.append("Reason: %s" % reason)
    lines.append("Body: %s" % _one_line(body)[:500])
    for key in sorted(meta.keys()):
        k = _one_line(str(key))
        if not k or not re.match(r"^[A-Za-z0-9_.-]+$", k):
            continue
        if k.lower() in ("channel", "person", "mouth", "status", "id",
                         "created", "updated", "reason", "body"):
            continue
        lines.append("%s: %s" % (k, _one_line(str(meta.get(key, "")))[:500]))
    lines.append("")
    lines.append("## Body")
    lines.append("")
    lines.append(body if body else "")
    lines.append("")
    return "\n".join(lines)


def _parse_draft(text: str, fallback_id: str = "") -> dict:
    data: dict = {
        "id": fallback_id,
        "channel": "",
        "person": "",
        "mouth": "personal",
        "status": "queued",
        "created": "",
        "updated": "",
        "reason": "",
        "body": "",
        "meta": {},
    }
    text = text or ""
    parts = re.split(r"^##\s*Body\s*$", text, maxsplit=1, flags=re.M | re.I)
    header = parts[0] if parts else text
    body_section = parts[1] if len(parts) > 1 else ""
    for line in header.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        low = key.lower()
        if low == "channel":
            data["channel"] = value
        elif low == "person":
            data["person"] = value
        elif low == "mouth":
            data["mouth"] = _normalize_mouth(value)
        elif low == "status":
            data["status"] = _normalize_status(value)
        elif low == "id":
            data["id"] = value or data["id"]
        elif low == "created":
            data["created"] = value
        elif low == "updated":
            data["updated"] = value
        elif low == "reason":
            data["reason"] = value
        elif low == "body":
            if not body_section.strip():
                data["body"] = value
            # else: full body lives under ## Body; skip header copy.
        else:
            try:
                data["meta"][key] = value
            except Exception:
                pass
    if str(body_section).strip():
        data["body"] = str(body_section).strip("\n").strip()
    if not data["id"]:
        data["id"] = fallback_id
    if not data["id"]:
        mt = re.search(r"^#\s*Draft\s+(\S+)", text, re.M | re.I)
        if mt:
            data["id"] = mt.group(1).strip()
    return data


def _read_draft_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    return _parse_draft(text, fallback_id=path.stem)


def _resolve_id(draft_id=None, **kwargs) -> str:
    if draft_id is not None and str(draft_id).strip() != "":
        return str(draft_id).strip()
    for key in ("id", "draft_id", "draft"):
        if key in kwargs and kwargs[key] not in (None, ""):
            return str(kwargs[key]).strip()
    return ""


def enqueue(channel="", person="", body="", mouth="personal", meta=None, **_extra) -> dict:
    if isinstance(channel, dict):
        payload = channel
        channel = payload.get("channel", "") or ""
        person = payload.get("person", "") or payload.get("to", "") or ""
        body = payload.get("body", "") or payload.get("text", "") or ""
        if not mouth or mouth == "personal":
            mouth = payload.get("mouth", "personal") or "personal"
        if meta is None:
            meta = payload.get("meta")
    if isinstance(person, dict) and isinstance(channel, str):
        step = person
        args = step.get("args", {}) if isinstance(step.get("args"), dict) else {}
        person = args.get("to") or args.get("contact") or args.get("person") or ""
        body = args.get("text") or args.get("body") or args.get("message") or body or ""
        tool = step.get("tool", "") or ""
        meta = meta if isinstance(meta, dict) else {}
        if "tool" not in meta:
            meta["tool"] = tool
        channel = tool or str(channel) or "message"
    draft_id = _new_id()
    now = _now_iso()
    data = {
        "id": draft_id,
        "channel": _one_line(channel),
        "person": _one_line(person),
        "mouth": _normalize_mouth(mouth),
        "status": "queued",
        "created": now,
        "updated": now,
        "reason": "",
        "body": str(body or ""),
        "meta": dict(meta) if isinstance(meta, dict) else {},
    }
    if _extra:
        try:
            for k, v in _extra.items():
                if k not in data["meta"]:
                    data["meta"][k] = v
        except Exception:
            pass
    with _LOCK:
        _ensure_drafts_dir()
        write_file(draft_path(draft_id), _render_draft(data))
    result = dict(data)
    result["path"] = str(draft_path(draft_id))
    return result


def list_drafts(status=None, **_kwargs) -> list:
    wanted = None
    raw_status = status if status is not None else _kwargs.get("filter")
    if raw_status not in (None, ""):
        wanted = _normalize_status(raw_status)
    with _LOCK:
        _ensure_drafts_dir()
        try:
            files = [p for p in drafts_dir().glob("*.md") if p.is_file()]
        except OSError:
            return []
        drafts = []
        for path in files:
            parsed = _read_draft_file(path)
            if parsed is None:
                continue
            parsed["path"] = str(path)
            drafts.append(parsed)
    if wanted is not None:
        drafts = [d for d in drafts if _normalize_status(d.get("status")) == wanted]

    def _sort_key(d: dict) -> str:
        return str(d.get("created") or d.get("updated") or d.get("id") or "")
    drafts.sort(key=_sort_key, reverse=True)
    return drafts


def get(draft_id=None, **kwargs):
    resolved = _resolve_id(draft_id, **kwargs)
    if not resolved:
        return None
    with _LOCK:
        _ensure_drafts_dir()
        parsed = _read_draft_file(draft_path(resolved))
        if parsed is None:
            return None
        parsed["path"] = str(draft_path(resolved))
        return parsed


def confirm(draft_id=None, **kwargs):
    resolved = _resolve_id(draft_id, **kwargs)
    if not resolved:
        return None
    with _LOCK:
        _ensure_drafts_dir()
        path = draft_path(resolved)
        parsed = _read_draft_file(path)
        if parsed is None:
            return None
        parsed["status"] = "sent-sandbox" if _is_sandbox() else "confirmed"
        parsed["updated"] = _now_iso()
        write_file(path, _render_draft(parsed))
        parsed["path"] = str(path)
        return parsed


def block(draft_id=None, reason="", **kwargs):
    if isinstance(draft_id, dict):
        kwargs.setdefault("id", draft_id.get("id"))
        draft_id = None
    resolved = _resolve_id(draft_id, **kwargs)
    if not resolved:
        return None
    if reason in (None, "") and "reason" in kwargs:
        reason = kwargs.get("reason", "")
    with _LOCK:
        _ensure_drafts_dir()
        path = draft_path(resolved)
        parsed = _read_draft_file(path)
        if parsed is None:
            return None
        parsed["status"] = "blocked"
        parsed["reason"] = _one_line(reason)
        parsed["updated"] = _now_iso()
        write_file(path, _render_draft(parsed))
        parsed["path"] = str(path)
        return parsed


__all__ = [
    "mind_dir",
    "drafts_dir",
    "draft_path",
    "safe_draft_id",
    "write_file",
    "enqueue",
    "list_drafts",
    "get",
    "confirm",
    "block",
]
