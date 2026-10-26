"""Markdown vault — markdown is the soul, never JSON.

Persists under ``MARC_MIND_DIR`` (default ``./var/mind``)::

    <mind>/
      ME.md
      NOW.md
      index.md
      people/
        _template.md
      style/
        _template.md

Stdlib only. All writes are atomic (tmp + os.replace).
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

_LOCK = threading.RLock()

MIND_DIR = Path(os.environ.get("MARC_MIND_DIR", "") or "./var/mind")

_ME_DEFAULT = """# ME

Name: Ranjith

Ranjith is the human Marc works for — builder, friend, and boss.
Marc remembers who Ranjith is from this file. Markdown is the soul; never JSON.

## Languages / மொழிகள்

- Tamil (தமிழ்): Ranjith speaks Tamil. Marc can reply in Tamil when asked.
  - வணக்கம் Ranjith! நான் Marc — உங்களுக்கு உதவ தயார்.
- English: default working language for plans, code, and notes.

## Work vs Friends

How Marc shows up depends on context:

- Work: focused, direct, professional. Plans, code, follow-through.
  - [placeholder — what Ranjith does for work, team, office context]
- Friends: warm, playful, Tamil + English mix. Jokes are welcome.
  - [placeholder — how Ranjith talks with friends, nicknames, vibe]

## Notes

- [placeholder — hometown, interests, goals]
"""

_NOW_DEFAULT_FOCUS = ""
_NOW_DEFAULT_LAST = ""
_NOW_DEFAULT_OPEN = ""

_PEOPLE_TEMPLATE = """# Person: <name>

- Who: [placeholder — who this person is]
- Relation: [work / friend / family — placeholder]
- Context: [placeholder — how Ranjith knows them]
- Last: [placeholder — last interaction]
- Notes:
  - [placeholder]
"""

_STYLE_TEMPLATE = """# Style: <channel>/<slug>

- Channel: [placeholder — where this style applies, e.g. whatsapp, email, office]
- Tone: [placeholder — e.g. warm, direct, bilingual Tamil/English]
- Do:
  - [placeholder]
- Don't:
  - [placeholder]
- Example:
  - [placeholder — a line in this voice]
"""

_INDEX_DEFAULT = """# Mind Index

Markdown is the soul. Start here.

- [[ME]] — who Ranjith is
- [[NOW]] — what Ranjith is doing now
- [[people/_template]] — how to remember people
- [[style/_template]] — how to sound per channel

## People

- [[people/_template]]

## Style

- [[style/_template]]
"""


def mind_dir() -> Path:
    """Return the mind vault directory from env (``MARC_MIND_DIR``)."""
    raw = os.environ.get("MARC_MIND_DIR", "") or "./var/mind"
    raw = str(raw).strip() or "./var/mind"
    return Path(raw)


def _base() -> Path:
    return mind_dir()


def _resolve(rel: str) -> Path:
    base = _base()
    rel_s = str(rel or "").replace("\\", "/").strip()
    rel_s = rel_s.lstrip("/")
    if not rel_s:
        raise ValueError("empty path")
    # Block absolute / traversal attempts.
    parts = [p for p in rel_s.split("/") if p not in ("", ".")]
    clean: list[str] = []
    for p in parts:
        if p == "..":
            raise ValueError("path escapes vault: %r" % (rel,))
        clean.append(p)
    if not clean:
        raise ValueError("empty path")
    return base.joinpath(*clean)


def _atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / ("%s.%d.tmp" % (path.name, os.getpid()))
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


_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_slug(slug: str, default: str = "untitled") -> str:
    cleaned = _SAFE_RE.sub("_", str(slug or "").strip()).strip("_")
    if not cleaned:
        cleaned = default
    return cleaned[:120]


def _default_now_text() -> str:
    from datetime import datetime

    try:
        updated = datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        updated = datetime.now().isoformat(timespec="seconds")
    return (
        "# NOW\n"
        "\n"
        "Focus: %s\n"
        "Last: %s\n"
        "Open: %s\n"
        "Updated: %s\n" % (_NOW_DEFAULT_FOCUS, _NOW_DEFAULT_LAST, _NOW_DEFAULT_OPEN, updated)
    )


def read_md(rel: str) -> str:
    """Read a markdown file relative to the vault. Returns "" if missing."""
    try:
        path = _resolve(rel)
    except ValueError:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
    except Exception:
        return ""


def write_md(rel: str, text: str) -> Path:
    """Write *text* to *rel* atomically. Returns the file path."""
    path = _resolve(rel)
    if not isinstance(text, str):
        text = str(text)
    with _LOCK:
        _atomic_write(path, text)
    return path


def seed() -> Path:
    """Seed the vault: ME.md, NOW.md (if missing), templates, index.md."""
    with _LOCK:
        base = _base()
        base.mkdir(parents=True, exist_ok=True)
        (base / "people").mkdir(parents=True, exist_ok=True)
        (base / "style").mkdir(parents=True, exist_ok=True)
        # ME.md — who Ranjith is (always ensure it exists with identity).
        _atomic_write(base / "ME.md", _ME_DEFAULT)
        # NOW.md — only if missing so we never clobber live focus.
        now_path = base / "NOW.md"
        if not now_path.exists():
            _atomic_write(now_path, _default_now_text())
        # Templates.
        _atomic_write(base / "people" / "_template.md", _PEOPLE_TEMPLATE)
        _atomic_write(base / "style" / "_template.md", _STYLE_TEMPLATE)
        # Index with wikilinks.
        _atomic_write(base / "index.md", _INDEX_DEFAULT)
        return base


def list_people() -> list[str]:
    """List person slugs under people/ (excludes _template)."""
    base = _base() / "people"
    try:
        files = [p for p in base.glob("*.md") if p.is_file()]
    except OSError:
        return []
    out: list[str] = []
    for p in files:
        if p.stem == "_template":
            continue
        out.append(p.stem)
    out.sort()
    return out


def upsert_person(slug: str, body: str) -> Path:
    """Create/update people/<slug>.md with *body*. Returns the path."""
    safe = _safe_slug(slug, "person")
    text = body if isinstance(body, str) else str(body)
    if not text.endswith("\n"):
        text += "\n"
    return write_md("people/%s.md" % safe, text)


def upsert_style(channel: str, slug: str, body: str) -> Path:
    """Create/update style/<channel>/<slug>.md with *body*. Returns path."""
    safe_ch = _safe_slug(channel, "general")
    safe_slug = _safe_slug(slug, "untitled")
    text = body if isinstance(body, str) else str(body)
    if not text.endswith("\n"):
        text += "\n"
    return write_md("style/%s/%s.md" % (safe_ch, safe_slug), text)


def who_am_i() -> str:
    """Return the ME.md soul text (who Ranjith is)."""
    try:
        text = read_md("ME.md")
    except Exception:
        text = ""
    if not (text or "").strip():
        try:
            seed()
            text = read_md("ME.md")
        except Exception:
            text = ""
    text = (text or "").strip()
    if text:
        return text
    return _ME_DEFAULT.strip()


def what_was_i_doing() -> str:
    """Return what Ranjith was doing — live NOW via sessions, else NOW.md."""
    # 1) Prefer live session soul via sessions.now_speak when importable.
    try:
        from ..sessions import now_speak as _now_speak  # type: ignore

        try:
            out = _now_speak()
            if isinstance(out, str) and out.strip():
                return out.strip()
        except Exception:
            pass
    except Exception:
        pass
    # 2) File-location load (handles hyphenated package dir name).
    try:
        import importlib.util

        sess_file = Path(__file__).resolve().parent.parent / "sessions.py"
        if sess_file.is_file():
            spec = importlib.util.spec_from_file_location("_marc_muse_sessions", str(sess_file))
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                fn = getattr(mod, "now_speak", None)
                if callable(fn):
                    out = fn()
                    if isinstance(out, str) and out.strip():
                        return out.strip()
    except Exception:
        pass
    # 3) Fallback: markdown is the soul — NOW.md, never JSON.
    try:
        text = read_md("NOW.md")
    except Exception:
        text = ""
    text = (text or "").strip()
    if text:
        return text
    return "Nothing recorded yet."


__all__ = [
    "MIND_DIR",
    "mind_dir",
    "seed",
    "read_md",
    "write_md",
    "list_people",
    "upsert_person",
    "upsert_style",
    "who_am_i",
    "what_was_i_doing",
]
