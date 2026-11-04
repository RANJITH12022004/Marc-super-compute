"""Markdown vault — markdown is the soul, never JSON.

Persists under ``MARC_MIND_DIR`` (default ``./var/mind``)::

    <mind>/
      ME.md
      NOW.md
      index.md
      daily/
        YYYY-MM-DD.md
      failed/
        YYYY-MM-DD.md
      notes/
        <slug>.md
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

Name: Ranjith Kumar Dasari
Called: Ranjith (everyone calls him Ranjith)

Ranjith Kumar Dasari is the human Marc works for — AI software engineer, friend, and boss.
Based in Bangalore (Bengaluru), India.
Marc remembers who Ranjith is from this file. Markdown is the soul; never JSON.

## Languages / భాషలు / भाषाएँ / மொழிகள்

- English: default for work, plans, code, and notes.
- Telugu (తెలుగు): fluent. Marc can reply in Telugu when asked.
  - నమస్కారం Ranjith! నేను Marc — మీ AI సాఫ్ట్‌వేర్ ఇంజనీర్ సహాయకుడిని.
- Hindi (हिन्दी): comfortable. Marc can reply in Hindi when asked.
  - नमस्ते Ranjith! मैं Marc हूँ — आपका AI सॉफ़्टवेयर इंजीनियर दोस्त और सहायक।
- Tamil (தமிழ்): some Tamil — understands and can mix a little; not primary.
  - வணக்கம் Ranjith! நான் Marc — சில தமிழ் பேசலாம்.

## Work

- Role: AI software engineer (Bangalore).
- Style: focused, direct, professional. Plans, code, follow-through.

## Friends

- Warm, playful. English + Telugu + Hindi mix; light Tamil welcome.
- Everyone calls him Ranjith.

## Notes

- Full name: Ranjith Kumar Dasari
- City: Bangalore / Bengaluru
- Work: AI software engineering
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
        # ME.md — create only if missing / empty (never clobber trained soul).
        me_path = base / "ME.md"
        try:
            existing = me_path.read_text(encoding="utf-8") if me_path.exists() else ""
        except Exception:
            existing = ""
        if not (existing or "").strip():
            _atomic_write(me_path, _ME_DEFAULT)
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


# ---------------------------------------------------------------------------
# Asked / failed / NOW-last / notes — markdown soul, atomic writes, stdlib only.
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = (
    "authorization",
    "bearer",
    "api key",
    "api-key",
    "api_key",
    "apikey",
)


def _is_secret_line(line: str) -> bool:
    low = str(line or "").lower()
    for pat in _SECRET_PATTERNS:
        if pat in low:
            return True
    return False


def _sanitize_failed_field(value) -> str:
    """Flatten to one line; strip secret lines; never leak secrets."""
    text = "" if value is None else str(value)
    if not text.strip():
        return ""
    lines = text.splitlines()
    kept = [ln for ln in lines if not _is_secret_line(ln)]
    if not kept:
        return "[redacted]"
    flat = " ".join(ln.strip() for ln in kept).strip()
    # Keep the ' | ' bullet delimiter unambiguous.
    flat = flat.replace("|", "/")
    flat = re.sub(r"\s+", " ", flat).strip()
    if not flat:
        return "[redacted]"
    if _is_secret_line(flat):
        return "[redacted]"
    return flat


def _one_line(value) -> str:
    text = "" if value is None else str(value)
    flat = " ".join(text.splitlines()).strip()
    flat = flat.replace("|", "/")
    return re.sub(r"\s+", " ", flat).strip()


def _today_str() -> str:
    from datetime import datetime

    try:
        return datetime.now().astimezone().date().isoformat()
    except Exception:
        from datetime import datetime as _dt

        return _dt.now().date().isoformat()


def _now_hm() -> str:
    from datetime import datetime

    try:
        return datetime.now().astimezone().strftime("%H:%M")
    except Exception:
        from datetime import datetime as _dt

        return _dt.now().strftime("%H:%M")


def _append_bullet(rel: str, bullet: str, header: str) -> Path:
    bullet = str(bullet or "").rstrip()
    if not bullet.endswith("\n"):
        bullet = bullet + "\n"
    with _LOCK:
        path = _resolve(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        try:
            if path.is_file():
                existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        except Exception:
            existing = ""
        if not (existing or "").strip():
            new_text = header + bullet
        else:
            if not existing.endswith("\n"):
                existing += "\n"
            new_text = existing + bullet
        _atomic_write(path, new_text)
        return Path(path)


def _format_action(item) -> str:
    if isinstance(item, str):
        return re.sub(r"\s+", " ", item.strip())
    ok = True
    tool = ""
    if isinstance(item, dict):
        if "ok" in item:
            ok = item.get("ok")
        elif "success" in item:
            ok = item.get("success")
        elif "status" in item:
            ok = item.get("status")
        elif "result" in item:
            ok = item.get("result")
        else:
            ok = True
        for key in ("tool", "name", "action", "tool_name"):
            if key in item and item.get(key) not in (None, ""):
                tool = item.get(key)
                break
    elif isinstance(item, (list, tuple)):
        if len(item) >= 2:
            ok = item[0]
            tool = item[1]
        elif len(item) == 1:
            tool = item[0]
            ok = True
        else:
            return ""
    else:
        return re.sub(r"\s+", " ", str(item).strip())
    if isinstance(ok, str):
        low = ok.strip().lower()
        if low in ("ok", "success", "successful", "pass", "passed", "true", "done", "1"):
            is_ok = True
        elif low in ("fail", "failed", "failure", "error", "false", "0"):
            is_ok = False
        else:
            is_ok = bool(ok)
    else:
        is_ok = bool(ok)
    tool_s = "" if tool is None else re.sub(r"\s+", " ", str(tool).replace("|", "/").strip())
    prefix = "ok" if is_ok else "fail"
    if tool_s:
        return "%s %s" % (prefix, tool_s)
    return prefix


def _extract_field(text: str, field: str) -> str:
    try:
        m = re.search(r"^%s:\s*(.*)$" % re.escape(field), text or "", re.MULTILINE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""


def append_asked(text, source="") -> Path:
    """Append one bullet to ``daily/YYYY-MM-DD.md`` with time.

    Format: ``- HH:MM | <text>`` plus `` | <source>`` when given.
    Secret-looking lines are stripped, never persisted.
    """
    day = _today_str()
    hm = _now_hm()
    clean_text = _sanitize_failed_field(text)
    clean_source = _sanitize_failed_field(source) if str(source or "").strip() else ""
    if not clean_text:
        clean_text = "(empty)"
    if clean_source:
        bullet = "- %s | %s | %s" % (hm, clean_text, clean_source)
    else:
        bullet = "- %s | %s" % (hm, clean_text)
    header = "# Daily %s\n\n" % day
    path = _append_bullet("daily/%s.md" % day, bullet, header)
    try:
        here = Path(__file__).resolve()
        cand = here.parents[2] / "server" / "cognee" / "memory.py"
        if cand.is_file():
            import importlib.util as _ilu

            spec = _ilu.spec_from_file_location("_marc_cognee_vault", str(cand))
            if spec is not None and spec.loader is not None:
                mod = _ilu.module_from_spec(spec)
                spec.loader.exec_module(mod)
                remember = getattr(mod, "remember", None)
                if callable(remember):
                    remember(clean_text, dataset="personal")
    except Exception:
        pass
    return path


def append_failed(utterance, tool="", device="", error="") -> Path:
    """Append one bullet to ``failed/YYYY-MM-DD.md``.

    Format: ``- HH:MM | utterance | tool | device | error``.
    NEVER persists secrets: any line containing Authorization/Bearer/
    api-key variants is stripped (whole field -> ``[redacted]`` if needed).
    """
    day = _today_str()
    hm = _now_hm()
    u = _sanitize_failed_field(utterance)
    t = _sanitize_failed_field(tool)
    d = _sanitize_failed_field(device)
    e = _sanitize_failed_field(error)
    bullet = "- %s | %s | %s | %s | %s" % (hm, u, t, d, e)
    header = "# Failed %s\n\n" % day
    return _append_bullet("failed/%s.md" % day, bullet, header)


def last_failed(n=5) -> list[str]:
    """Return the last *n* failed bullets as strings (oldest first)."""
    try:
        count = int(n)
    except Exception:
        count = 5
    if count <= 0:
        return []
    lines: list[str] = []
    try:
        base = _base() / "failed"
        if base.is_dir():
            files = sorted([p for p in base.glob("*.md") if p.is_file()])
            for fp in files:
                try:
                    text = fp.read_text(encoding="utf-8")
                except OSError:
                    continue
                except Exception:
                    continue
                for raw in (text or "").splitlines():
                    s = raw.strip()
                    if not s:
                        continue
                    if s.startswith("- "):
                        lines.append(s)
                    elif re.match(r"^\d{1,2}:\d{2}\s*\|", s):
                        lines.append(s)
    except Exception:
        return []
    if not lines and count:
        # Fall back to today's file via read_md (covers odd env setups).
        try:
            text = read_md("failed/%s.md" % _today_str())
        except Exception:
            text = ""
        for raw in (text or "").splitlines():
            s = raw.strip()
            if s.startswith("- "):
                lines.append(s)
    return lines[-count:]


def update_now_last(actions) -> Path:
    """Write NOW.md ``Last:`` as the last 3 actions (``ok/fail tool``)."""
    items: list[str] = []
    try:
        seq = list(actions) if actions is not None else []
    except TypeError:
        seq = [actions]
    for a in seq:
        s = _format_action(a)
        if s:
            items.append(s)
    last3 = items[-3:]
    last_val = ", ".join(last3)
    with _LOCK:
        try:
            path = _resolve("NOW.md")
        except ValueError:
            path = _base() / "NOW.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        try:
            if path.is_file():
                existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        except Exception:
            existing = ""
        if not (existing or "").strip():
            existing = _default_now_text()
        out_lines: list[str] = []
        found = False
        for raw in existing.splitlines():
            if not found and re.match(r"^Last:\s*", raw):
                out_lines.append("Last: %s" % last_val)
                found = True
            else:
                out_lines.append(raw)
        if not found:
            # Insert after '# NOW' when present, else prepend.
            inserted = False
            fresh: list[str] = []
            for i, raw in enumerate(out_lines):
                fresh.append(raw)
                if not inserted and raw.strip() == "# NOW":
                    fresh.append("Last: %s" % last_val)
                    inserted = True
            if not inserted:
                fresh = ["# NOW", "", "Last: %s" % last_val] + fresh
            out_lines = fresh
        # Refresh Updated: timestamp.
        from datetime import datetime

        try:
            updated = datetime.now().astimezone().isoformat(timespec="seconds")
        except Exception:
            updated = datetime.now().isoformat(timespec="seconds")
        refreshed: list[str] = []
        seen_updated = False
        for raw in out_lines:
            if re.match(r"^Updated:\s*", raw):
                refreshed.append("Updated: %s" % updated)
                seen_updated = True
            else:
                refreshed.append(raw)
        if not seen_updated:
            refreshed.append("Updated: %s" % updated)
        out_lines = refreshed
        new_text = "\n".join(out_lines).rstrip() + "\n"
        _atomic_write(path, new_text)
        return Path(path)


def save_note(title, body) -> Path:
    """Save a markdown note to ``notes/<slug>.md``. Returns the path."""
    raw_title = "" if title is None else str(title).strip()
    if not raw_title:
        raw_title = "untitled"
    slug = _safe_slug(raw_title, "untitled")
    text_body = "" if body is None else (body if isinstance(body, str) else str(body))
    text_body = text_body.strip()
    if text_body:
        text = "# %s\n\n%s\n" % (raw_title, text_body)
    else:
        text = "# %s\n" % raw_title
    return write_md("notes/%s.md" % slug, text)


def merge_me_facts(facts) -> str:
    """Append/replace ## GitHub / ## Mail / ## Phone sections in ME.md.

    Never wipes the rest of the soul. Returns the new ME.md text.
    """
    if not isinstance(facts, dict):
        facts = {}
    seed()
    try:
        text = read_md("ME.md") or ""
    except Exception:
        text = _ME_DEFAULT
    if not (text or "").strip():
        text = _ME_DEFAULT

    def _upsert_section(body: str, heading: str, content: str) -> str:
        if not content or not str(content).strip():
            return body
        block = "## %s\n\n%s\n" % (heading, str(content).strip())
        pat = re.compile(
            r"(?ms)^##\s+%s\s*\n.*?(?=^##\s|\Z)" % re.escape(heading)
        )
        if pat.search(body):
            return pat.sub(block + "\n", body, count=1).rstrip() + "\n"
        return body.rstrip() + "\n\n" + block

    out = text
    if facts.get("github"):
        out = _upsert_section(out, "GitHub", facts.get("github"))
    if facts.get("mail"):
        out = _upsert_section(out, "Mail", facts.get("mail"))
    if facts.get("phone"):
        out = _upsert_section(out, "Phone", facts.get("phone"))
    write_md("ME.md", out if out.endswith("\n") else out + "\n")
    return out


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
    "append_asked",
    "append_failed",
    "last_failed",
    "update_now_last",
    "save_note",
    "merge_me_facts",
]
