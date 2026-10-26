"""Export ingest — WhatsApp / Instagram / mail exports into mind/raw/ (stdlib only).

Layout::

    <mind>/raw/<basename>   -- verbatim raw copies only (nothing else written here)

Parsers:

- :func:`parse_whatsapp_txt` — WhatsApp export ``DD/MM/YY, HH:MM - Name: msg``.
- :func:`parse_instagram_json` — list of ``{sender, text}`` (or IG export dict).
- :func:`parse_mail_mbox_or_lines` — mbox text or plain ``Sender: msg`` lines.

:func:`ingest_path` detects the format, writes a raw copy **only** under
``mind/raw/``, then calls ``style.distill`` grouped by person+channel.
Missing paths are skipped. All writes go through :func:`write_file`
(atomic tmp + os.replace). Stdlib only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

__all__ = [
    "mind_dir",
    "raw_dir",
    "write_file",
    "parse_whatsapp_txt",
    "parse_instagram_json",
    "parse_mail_mbox_or_lines",
    "ingest_path",
]

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

# WhatsApp export line: 'DD/MM/YY, HH:MM - Name: msg'
# Day/Month may be 1-2 digits, year 2 or 4 digits, optional seconds/AM-PM.
_WA_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s+"
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\s*-\s*(.*)$"
)


# ---------------------------------------------------------------- dirs ---

def mind_dir() -> Path:
    """Return the mind vault directory from env (``MARC_MIND_DIR``)."""
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path((str(raw) or "").strip() or "./var/mind")


def raw_dir(base: str | Path | None = None) -> Path:
    """Return ``<mind>/raw`` (created on demand by :func:`ingest_path`)."""
    root = Path(base) if base is not None else mind_dir()
    return root / "raw"


def _safe_basename(name: str, default: str = "export.dat") -> str:
    base = os.path.basename(str(name or "").strip()) or default
    base = _SAFE_RE.sub("_", base).strip("._") or default
    if len(base) > 120:
        stem, dot, ext = base.rpartition(".")
        if dot and len(ext) <= 10:
            keep = 120 - len(ext) - 1
            base = stem[:keep].rstrip("._") + "." + ext
        else:
            base = base[:120]
    return base or default


def write_file(path: str | Path, content: str | bytes) -> Path:
    """Atomically write *content* to *path* (tmp + os.replace)."""
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
    if isinstance(content, bytes):
        with open(tmp, "wb") as fh:
            fh.write(content)
            try:
                fh.flush()
                os.fsync(fh.fileno())
            except Exception:
                pass
    else:
        if not isinstance(content, str):
            content = str(content)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
            try:
                fh.flush()
                os.fsync(fh.fileno())
            except Exception:
                pass
    os.replace(tmp, target)
    return target


# -------------------------------------------------------------- whatsapp ---

def parse_whatsapp_txt(text: str) -> list[dict]:
    """Parse WhatsApp ``DD/MM/YY, HH:MM - Name: msg`` exports.

    Continuation lines (no timestamp prefix) are appended to the
    previous message. System lines without ``Name: msg`` are skipped.
    Returns ``[{sender, text, timestamp}]``.
    """
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", "replace")
        except Exception:
            text = ""
    lines = (text or "").splitlines()
    out: list[dict] = []
    for line in lines:
        stripped = line.strip("\ufeff").rstrip("\n")
        if not stripped.strip():
            continue
        m = _WA_RE.match(stripped.strip())
        if m:
            stamp = ("%s, %s" % (m.group(1).strip(), m.group(2).strip())).strip()
            rest = (m.group(3) or "").strip()
            if ": " in rest:
                name, _, msg = rest.partition(": ")
            elif rest.endswith(":"):
                name, msg = rest[:-1].strip(), ""
            else:
                # System notice ("Messages are end-to-end encrypted", etc.).
                continue
            name = name.strip()
            msg = msg.strip()
            if not name:
                continue
            # Skip obvious system senders with empty text.
            out.append({"sender": name, "text": msg, "timestamp": stamp})
        else:
            # Continuation of the previous message.
            if out:
                prev = out[-1].get("text") or ""
                add = stripped.strip()
                out[-1]["text"] = (prev + "\n" + add).strip() if prev else add
            # Else: stray line with no message yet — ignore.
    return out


# ------------------------------------------------------------- instagram ---

def _ig_sender(item: dict) -> str:
    for key in ("sender", "sender_name", "from", "author", "username", "name"):
        try:
            val = item.get(key)
        except Exception:
            continue
        if val not in (None, ""):
            return str(val).strip()
    return ""


def _ig_text(item: dict) -> str:
    for key in ("text", "content", "message", "body", "caption"):
        try:
            val = item.get(key)
        except Exception:
            continue
        if val is None:
            continue
        if isinstance(val, list):
            # Rare: list of segments — join string parts.
            parts = [str(p) for p in val if isinstance(p, (str, int, float))]
            joined = "".join(parts).strip()
            if joined:
                return joined
            continue
        s = str(val).strip()
        if s:
            return s
    return ""


def parse_instagram_json(obj) -> list[dict]:
    """Parse Instagram exports into ``[{sender, text}]``.

    Accepts a list of ``{sender, text}`` (plus IG aliases
    ``sender_name``/``content``/``message``) or a dict wrapping such a
    list under ``messages``/``conversation``/``data``/``chats``.
    A JSON string is decoded first. Entries with empty text are skipped.
    """
    if isinstance(obj, (bytes, bytearray)):
        try:
            obj = bytes(obj).decode("utf-8", "replace")
        except Exception:
            return []
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return []
    items: list = []
    if isinstance(obj, dict):
        for key in ("messages", "conversation", "data", "chats", "items", "thread"):
            val = obj.get(key)
            if isinstance(val, list):
                items = val
                break
        else:
            # Single message dict?
            if any(k in obj for k in ("sender", "sender_name", "from", "text", "content", "message")):
                items = [obj]
            else:
                return []
    elif isinstance(obj, (list, tuple)):
        items = list(obj)
    else:
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sender = _ig_sender(item)
        text = _ig_text(item)
        if not text:
            continue
        out.append({"sender": sender, "text": text})
    return out


# ------------------------------------------------------------------- mail ---

def _mail_sender(raw: str) -> str:
    s = (raw or "").strip().strip('"').strip()
    if not s:
        return ""
    # 'Display Name <addr@x>' -> Display Name
    m = re.match(r'^\s*"?([^"<]+?)"?\s*<[^>]+>\s*$', s)
    if m:
        name = m.group(1).strip().strip('"').strip()
        if name:
            return name
    # Bare <addr@x> -> addr@x
    m2 = re.match(r"^\s*<([^>]+)>\s*$", s)
    if m2:
        return m2.group(1).strip()
    return s


def _parse_mail_headers(header_text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    current = ""
    for line in (header_text or "").splitlines():
        if not line.strip():
            continue
        if line[0] in (" ", "\t") and current:
            headers[current] += " " + line.strip()
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key:
            current = key
            if key in headers:
                headers[key] += " " + value
            else:
                headers[key] = value
    return headers


def parse_mail_mbox_or_lines(text) -> list[dict]:
    """Parse mbox text **or** plain ``Sender: msg`` lines.

    - mbox: splits on ``^From <...>`` separators, parses ``From:`` /
      ``Subject:`` headers; ``text`` is ``subject + body``.
    - lines fallback: each non-empty line becomes a message; ``A: hi``
      splits into sender/text, otherwise sender is ``""``.
    Returns ``[{sender, text}]`` (mbox items also carry ``subject``).
    """
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", "replace")
        except Exception:
            text = ""
    elif isinstance(text, (list, tuple)):
        text = "\n".join(str(x) for x in text)
    text = str(text or "")
    if not text.strip():
        return []
    # Normalize newlines.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    has_mbox_sep = bool(re.search(r"(?m)^From \S", text))
    has_headers = bool(re.search(r"(?mi)^(From|Subject|Date|To)\s*:", text))
    out: list[dict] = []

    if has_mbox_sep or has_headers:
        chunks = re.split(r"(?m)^From [^\n]*\n", text)
        # If no separator but headers exist, the whole text is one mail.
        if len(chunks) == 1 and not has_mbox_sep and has_headers:
            chunks = [text]
        for chunk in chunks:
            if not chunk.strip():
                continue
            # Skip preamble before the first From_ line.
            if not re.search(r"(?mi)^(From|Subject|Date|To|Message-ID)\s*:", chunk):
                # Might still be a body-only chunk — treat lines fallback?
                continue
            parts = re.split(r"\n\s*\n", chunk, maxsplit=1)
            header_text = parts[0] if parts else ""
            body = parts[1] if len(parts) > 1 else ""
            headers = _parse_mail_headers(header_text)
            sender = _mail_sender(headers.get("from", ""))
            subject = (headers.get("subject", "") or "").strip()
            body = body.strip()
            # Strip common quoting of forwarded mbox escaping.
            lines = []
            for ln in body.splitlines():
                if ln.startswith(">From "):
                    lines.append(ln[1:])
                else:
                    lines.append(ln)
            body = "\n".join(lines).strip()
            combined = ((subject + "\n" + body).strip() if subject else body).strip()
            if not combined:
                continue
            item: dict = {"sender": sender, "text": combined}
            if subject:
                item["subject"] = subject
            out.append(item)
        if out:
            return out
        # Fall through to lines parsing when header parse yielded nothing.

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("From ") and len(s) < 200:
            continue
        m = re.match(r"^([^:<>@]{1,80}):\s*(.+)$", s)
        if m:
            name = m.group(1).strip()
            # Avoid treating mail headers as chat lines when they slipped here.
            if name.lower() in ("from", "to", "subject", "date", "cc", "bcc"):
                continue
            out.append({"sender": name, "text": m.group(2).strip()})
        else:
            out.append({"sender": "", "text": s})
    return out


# ------------------------------------------------------------ detection ---

def _looks_like_whatsapp(text: str) -> bool:
    count = 0
    for line in (text or "").splitlines()[:50]:
        if _WA_RE.match(line.strip()):
            count += 1
            if count >= 2:
                return True
    if count >= 1:
        # Single match plus continuation text still counts.
        return True
    return False


def _looks_like_json(text: str) -> bool:
    s = (text or "").lstrip("\ufeff").strip()
    if not s or s[0] not in ("[", "{"):
        return False
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def _detect_channel(path: str | Path, text: str) -> str:
    suffix = Path(str(path)).suffix.lower()
    if suffix == ".json":
        return "instagram"
    if suffix in (".mbox", ".eml"):
        return "mail"
    if suffix == ".txt":
        if _looks_like_whatsapp(text):
            return "whatsapp"
        if _looks_like_json(text):
            return "instagram"
        return "mail" if re.search(r"(?mi)^(From|Subject)\s*:", text) else "whatsapp"
    # Unknown suffix — sniff content.
    if _looks_like_json(text):
        return "instagram"
    if _looks_like_whatsapp(text):
        return "whatsapp"
    return "mail"


# ----------------------------------------------------------------- style ---

def _load_style_module():
    for name in ("style",):
        try:
            if name in sys.modules:
                mod = sys.modules[name]
                if mod is not None:
                    return mod
            __import__(name)
            mod = sys.modules.get(name)
            if mod is not None:
                return mod
        except Exception:
            continue
    # File-location fallback: sibling style.py (hyphenated package breaks imports).
    try:
        here = Path(__file__).resolve().parent
        cand = here / "style.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("marc_style_fallback", str(cand))
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["marc_style_fallback"] = mod
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                return mod
    except Exception:
        pass
    return None


def _call_distill(person: str, channel: str, messages: list[dict]):
    mod = _load_style_module()
    if mod is None:
        return None
    fn = getattr(mod, "distill", None)
    if not callable(fn):
        return None
    # Primary contract: distill(person, channel, messages).
    try:
        return fn(person, channel, messages)
    except TypeError:
        pass
    except Exception:
        return None
    try:
        return fn(person=person, channel=channel, messages=messages)
    except TypeError:
        pass
    except Exception:
        return None
    try:
        texts = [str(m.get("text", "")) for m in messages]
        return fn(person, channel, texts)
    except TypeError:
        pass
    except Exception:
        return None
    try:
        return fn({"person": person, "channel": channel, "messages": messages})
    except Exception:
        return None


# ---------------------------------------------------------------- ingest ---

def ingest_path(path: str | Path, channel: str | None = None) -> dict:
    """Ingest an export file into ``mind/raw/`` + style cards.

    - Missing path: returns ``{ok: False, reason: 'missing'}`` (no writes).
    - Detects format (``whatsapp`` | ``instagram`` | ``mail``) unless
      *channel* is given.
    - Writes a verbatim raw copy **only** under ``mind/raw/`` via
      :func:`write_file`.
    - Groups parsed messages by ``(person, channel)`` and calls
      ``style.distill(person, channel, messages)`` per group (skipped
      when the style module is unavailable).
    """
    src = Path(str(path or ""))
    if not str(path or "").strip() or not src.is_file():
        return {"ok": False, "reason": "missing", "path": str(path)}
    try:
        raw_bytes = src.read_bytes()
    except OSError as exc:
        return {"ok": False, "reason": "unreadable: %s" % exc, "path": str(src)}
    try:
        text = raw_bytes.decode("utf-8", "replace")
    except Exception:
        text = ""

    chosen = (str(channel or "").strip().lower() or _detect_channel(src, text))
    if chosen in ("email", "emails", "e-mail"):
        chosen = "mail"
    if chosen not in ("whatsapp", "instagram", "mail"):
        chosen = _detect_channel(src, text)

    try:
        if chosen == "instagram":
            try:
                obj = json.loads(text) if text.strip() else []
            except Exception:
                obj = text
            messages = parse_instagram_json(obj)
            if not messages:
                # Not actually JSON — fall back by sniffing.
                alt = _detect_channel(src, text)
                if alt == "whatsapp":
                    chosen = alt
                    messages = parse_whatsapp_txt(text)
                elif alt == "mail":
                    chosen = alt
                    messages = parse_mail_mbox_or_lines(text)
        elif chosen == "mail":
            messages = parse_mail_mbox_or_lines(text)
        else:
            chosen = "whatsapp"
            messages = parse_whatsapp_txt(text)
    except Exception as exc:
        return {"ok": False, "reason": "parse error: %s" % exc,
                "path": str(src), "channel": chosen}

    # Raw copy ONLY under mind/raw/ (gitignored conceptually).
    base = mind_dir()
    dest = base / "raw" / _safe_basename(src.name or "export.dat")
    try:
        write_file(dest, raw_bytes)
    except OSError as exc:
        return {"ok": False, "reason": "raw write error: %s" % exc,
                "path": str(src), "channel": chosen}

    # Group by person+channel for style distillation.
    groups: dict[tuple[str, str], list[dict]] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        person = str(msg.get("sender", "") or "").strip() or "unknown"
        key = (person, chosen)
        groups.setdefault(key, []).append(msg)

    distilled: list = []
    group_info: list[dict] = []
    for (person, ch), msgs in sorted(groups.items()):
        group_info.append({"person": person, "channel": ch, "count": len(msgs)})
        try:
            res = _call_distill(person, ch, msgs)
        except Exception:
            res = None
        distilled.append(res)

    return {
        "ok": True,
        "path": str(src),
        "channel": chosen,
        "raw": str(dest),
        "count": len(messages),
        "groups": group_info,
        "distilled": distilled,
    }
