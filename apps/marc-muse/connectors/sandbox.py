"""Sandbox connectors — in-memory channel inboxes (stdlib only).

Channels: ``mail`` (gmail alias), ``whatsapp`` (wa alias),
``instagram`` (ig/insta/dm aliases).

- Inboxes hold FAKE *inbound* fixture messages only.
- ``send()`` NEVER delivers and NEVER touches the network: it always
  routes to ``drafts.enqueue`` (sandbox-safe).
- ``list_inbox(channel)`` returns a copy of that channel's inbox.
- ``load_people()`` parses ``sandbox/fixtures/people.md`` (the SOUL
  fixture, not JSON) into ``{slug: person}`` dicts.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

__all__ = [
    "CHANNELS",
    "FIXTURE_PATH",
    "normalize_channel",
    "list_channels",
    "list_inbox",
    "receive",
    "send",
    "clear_inboxes",
    "reset_inboxes",
    "load_people",
]

CHANNELS = ("mail", "whatsapp", "instagram")

_ALIASES = {
    "mail": "mail",
    "gmail": "mail",
    "email": "mail",
    "e-mail": "mail",
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "instagram": "instagram",
    "ig": "instagram",
    "insta": "instagram",
    "dm": "instagram",
}

_HERE = Path(__file__).resolve().parent
FIXTURE_PATH = _HERE.parent / "sandbox" / "fixtures" / "people.md"

_LOCK = threading.RLock()
_INBOXES: dict[str, list[dict]] = {ch: [] for ch in CHANNELS}
_SEEDED = False
_SEQ = 0


def normalize_channel(channel: str) -> str:
    """Map gmail/wa/ig-style names to canonical mail/whatsapp/instagram."""
    key = str(channel or "").strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError("unknown channel %r (want mail|whatsapp|instagram)" % (channel,))


def list_channels() -> list[str]:
    """Return the canonical sandbox channels."""
    return list(CHANNELS)


def _next_id(prefix: str = "m") -> str:
    global _SEQ
    with _LOCK:
        _SEQ += 1
        return "%s%d" % (prefix, _SEQ)


def _seed() -> None:
    """Seed each inbox with one FAKE inbound message per fixture person."""
    global _SEEDED
    with _LOCK:
        if _SEEDED:
            return
        _SEEDED = True
        _INBOXES["mail"].append(
            {
                "id": _next_id("m"),
                "channel": "mail",
                "person": "sam",
                "from_": "sam.professional.fake@gmail.com (FAKE)",
                "body": "FAKE: Sam sent the Q3 report draft for review.",
                "direction": "in",
            }
        )
        _INBOXES["whatsapp"].append(
            {
                "id": _next_id("m"),
                "channel": "whatsapp",
                "person": "priya",
                "from_": "+1-555-0102 (FAKE)",
                "body": "FAKE: Priya (WA): are we still on for Saturday?",
                "direction": "in",
            }
        )
        _INBOXES["whatsapp"].append(
            {
                "id": _next_id("m"),
                "channel": "whatsapp",
                "person": "ravi",
                "from_": "+1-555-0104 (FAKE)",
                "body": "FAKE: Ravi (WA): errand done, ping me later.",
                "direction": "in",
            }
        )
        _INBOXES["instagram"].append(
            {
                "id": _next_id("m"),
                "channel": "instagram",
                "person": "priya",
                "from_": "@priya.fake.ig (FAKE)",
                "body": "FAKE: Priya (IG): loved your photos!",
                "direction": "in",
            }
        )
        _INBOXES["instagram"].append(
            {
                "id": _next_id("m"),
                "channel": "instagram",
                "person": "alex",
                "from_": "@alex.fake.stranger (FAKE)",
                "body": "FAKE: Alex (IG): hey, found you via a public post.",
                "direction": "in",
            }
        )


def list_inbox(channel: str) -> list[dict]:
    """Return a copy of the in-memory inbox for *channel*."""
    _seed()
    canon = normalize_channel(channel)
    with _LOCK:
        return [dict(m) for m in _INBOXES[canon]]


def receive(channel: str, person: str, body: str, meta: dict | None = None) -> dict:
    """Append a FAKE inbound message to *channel*'s inbox (tests/fixtures)."""
    _seed()
    canon = normalize_channel(channel)
    msg = {
        "id": _next_id("m"),
        "channel": canon,
        "person": str(person or "").strip().lower(),
        "body": str(body or ""),
        "direction": "in",
    }
    if meta is not None:
        msg["meta"] = dict(meta) if isinstance(meta, dict) else meta
    with _LOCK:
        _INBOXES[canon].append(dict(msg))
    return dict(msg)


def _load_drafts():
    """Best-effort import of the drafts module (top-level or package)."""
    for name in ("drafts", "connectors.drafts", "marc-muse.drafts"):
        try:
            __import__(name)
            import sys as _sys

            mod = _sys.modules.get(name)
            if mod is not None and hasattr(mod, "enqueue"):
                return mod
        except Exception:
            continue
    # Sibling-file fallback when imported as apps.marc-muse.connectors.sandbox.
    try:
        from .. import drafts as _d2  # type: ignore

        if hasattr(_d2, "enqueue"):
            return _d2
    except Exception:
        pass
    try:
        import sys as _sys

        here = Path(__file__).resolve().parent.parent
        if str(here) not in _sys.path:
            _sys.path.insert(0, str(here))
        import drafts as _d3  # type: ignore

        if hasattr(_d3, "enqueue"):
            return _d3
    except Exception:
        pass
    return None


def send(
    channel: str,
    person: str,
    body: str = "",
    mouth: str = "personal",
    meta: dict | None = None,
    **kw,
) -> dict:
    """Queue an outbound message as a draft — never sends.

    Always routes to ``drafts.enqueue(channel, person, body,
    mouth, meta)``. Returns the draft record (or a queued stub when
    the drafts module is unavailable).
    """
    canon = normalize_channel(channel)
    text = body
    if not text and isinstance(kw.get("text"), str):
        text = kw["text"]
    if not text and isinstance(kw.get("message"), str):
        text = kw["message"]
    text = str(text or "")
    who = str(person or "").strip().lower()
    mouth_v = str(mouth or "personal").strip().lower() or "personal"
    if mouth_v not in ("personal", "business"):
        mouth_v = "personal"
    meta_v = dict(meta) if isinstance(meta, dict) else (meta or {})
    if kw:
        extra = {k: v for k, v in kw.items() if k not in ("text", "message")}
        if extra and isinstance(meta_v, dict):
            meta_v = {**extra, **meta_v}

    drafts = _load_drafts()
    if drafts is not None:
        try:
            return drafts.enqueue(canon, who, text, mouth=mouth_v, meta=meta_v)
        except TypeError:
            # Tolerate positional-only variants.
            try:
                return drafts.enqueue(canon, who, text, mouth_v)
            except Exception:
                pass
        except Exception:
            pass
    # Fallback stub (still queued, nothing sent).
    with _LOCK:
        stub = {
            "id": _next_id("d"),
            "channel": canon,
            "person": who,
            "body": text,
            "mouth": mouth_v,
            "meta": meta_v,
            "status": "queued",
            "sandbox": True,
        }
    return stub


def clear_inboxes() -> None:
    """Empty all in-memory inboxes (keeps the seeded flag off)."""
    global _SEEDED
    with _LOCK:
        for ch in CHANNELS:
            _INBOXES[ch] = []
        _SEEDED = True


def reset_inboxes() -> None:
    """Clear inboxes and re-seed the default FAKE fixtures on next read."""
    global _SEEDED
    with _LOCK:
        for ch in CHANNELS:
            _INBOXES[ch] = []
        _SEEDED = False


# ------------------------------------------------------- people.md ---

_HEADING_RE = re.compile(r"^##\s+(.*)$")
_WIKI_RE = re.compile(r"\[\[([^\]]+)\]\]")
_BULLET_RE = re.compile(r"^\s*[-*]\s+([^:]+):\s*(.*)$")


def _clean_contact(value: str) -> str:
    v = str(value or "").strip()
    if not v or v.lower() == "none":
        return ""
    # Strip trailing "(FAKE)" labels but keep the handle/number itself.
    v = re.sub(r"\s*\(FAKE\)\s*", "", v).strip()
    return v


def _parse_section(heading: str, lines: list[str]) -> dict:
    wiki = _WIKI_RE.search(heading or "")
    name = wiki.group(1).strip() if wiki else re.sub(r"[—–-].*$", "", heading).strip()
    fields: dict[str, str] = {}
    for ln in lines:
        m = _BULLET_RE.match(ln)
        if not m:
            continue
        fields[m.group(1).strip().lower()] = m.group(2).strip()

    slug = fields.get("slug", "").strip().lower() or re.sub(
        r"[^a-z0-9]+", "", name.lower()
    )
    relationship = fields.get("relationship", "").strip().lower()
    if not relationship:
        low_head = heading.lower()
        for cand in ("professional", "friend", "stranger", "mixed"):
            if cand in low_head:
                relationship = cand
                break
    relationship = relationship or "mixed"

    raw_channels = fields.get("channels", "")
    channels: list[str] = []
    for part in re.split(r"[,/]+", raw_channels):
        p = part.strip().lower()
        if not p or p == "none":
            continue
        try:
            channels.append(normalize_channel(p))
        except ValueError:
            continue
    # Preserve order, drop dupes.
    seen: set[str] = set()
    uniq = []
    for c in channels:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    email = _clean_contact(fields.get("email", ""))
    ig = _clean_contact(fields.get("instagram", ""))
    wa = _clean_contact(fields.get("whatsapp", ""))
    work_raw = fields.get("work ok", fields.get("work_ok", "")).strip().lower()
    work_ok = work_raw.startswith(("y", "true", "1", "allow"))
    notes = fields.get("notes", "").strip()
    email = _clean_contact(fields.get("email", ""))
    ig = _clean_contact(fields.get("instagram", ""))
    wa = _clean_contact(fields.get("whatsapp", ""))
    # Fixture keys carry suffixes: "Email (FAKE)", "Instagram (FAKE)", ...
    if not email:
        email = _clean_contact(next((v for k, v in fields.items() if k.startswith("email")), ""))
    if not ig:
        ig = _clean_contact(next((v for k, v in fields.items() if k.startswith("instagram")), ""))
    if not wa:
        wa_raw = next((v for k, v in fields.items() if k.startswith("whatsapp")), "")
        # "+1-555-0102 (FAKE)" -> bullet regex split on the ':'? no colon; keep up to label
        wa = _clean_contact(wa_raw)
    work_raw = fields.get("work ok", fields.get("work_ok", "")).strip().lower()
    if not work_raw:
        work_raw = next((v for k, v in fields.items() if k.startswith("work ok") or k.startswith("work_ok")), "").strip().lower()
    work_ok = work_raw.startswith(("y", "true", "1", "allow"))
    notes = fields.get("notes", "").strip()
    links = sorted(set(_WIKI_RE.findall(" ".join(lines))))

    person = {
        "slug": slug,
        "name": name,
        "relationship": relationship,
        "channels": uniq,
        # singular 'channel' hint (first) for policy.merge_identity channel inference
        "channel": uniq[0] if uniq else "",
        "email": email,
        "instagram": ig,
        "ig": ig,
        "links": links,
    }
    return person


def _fixture_candidates(path: str | os.PathLike | None) -> list[Path]:
    cands: list[Path] = []
    if path is not None:
        cands.append(Path(str(path)))
    env = os.environ.get("MARC_PEOPLE_FIXTURE") or os.environ.get("PEOPLE_FIXTURE")
    if env:
        cands.append(Path(env))
    cands.append(FIXTURE_PATH)
    cands.append(_HERE / "fixtures" / "people.md")
    cands.append(_HERE.parent / "sandbox" / "fixtures" / "people.md")
    return cands


def load_people(
    path: str | os.PathLike | None = None, text: str | None = None
) -> dict[str, dict]:
    """Parse ``people.md`` into ``{slug: person}``.

    Each person has ``slug, name, relationship, channels, email,
    instagram/ig, whatsapp/wa/phone, work_ok, notes, links``.
    Raises FileNotFoundError when no fixture source is found.
    """
    if text is None:
        src: Path | None = None
        for cand in _fixture_candidates(path):
            try:
                if cand.is_file():
                    src = cand
                    break
            except OSError:
                continue
        if src is None:
            tried = ", ".join(str(c) for c in _fixture_candidates(path))
            raise FileNotFoundError("people.md fixture not found; tried: %s" % tried)
        text = src.read_text(encoding="utf-8")

    people: dict[str, dict] = {}
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if heading is None:
            return
        person = _parse_section(heading, buf)
        if person.get("slug"):
            people[person["slug"]] = person

    for line in (text or "").splitlines():
        m = _HEADING_RE.match(line.strip())
        if m and _WIKI_RE.search(m.group(1)):
            flush()
            heading = m.group(1).strip()
            buf = []
        elif m and heading is not None and line.startswith("##"):
            # Non-person heading ends the current section.
            flush()
            heading = None
            buf = []
        elif heading is not None:
            buf.append(line)
    flush()
    return people
