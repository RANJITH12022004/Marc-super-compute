"""Fast-path skip-muse regex for marc-muse.

LOCAL_PHRASES documents the single-command local phrases that bypass Muse:
  LOCAL_PHRASES = ("open spotify", "type ", "youtube")
- "open spotify" (case insensitive, regex ``\\bopen\\s+spotify\\b``)
- "type ..." (starts with ``type `` after stripping, case insensitive)
- "youtube ..." (first command contains ``youtube``, case insensitive)

Anything involving email/whatsapp, compound (then/and then/after that/;/and)
or demo keywords never skips Muse (returns False).
"""

import re

# Documented local phrases that may skip Muse when they appear as a
# single simple command.
LOCAL_PHRASES = ("open spotify", "type ", "youtube")

_OPEN_SPOTIFY_RE = re.compile(r"\bopen\s+spotify\b", re.I)
_TYPE_PREFIX_RE = re.compile(r"^type\s+", re.I)
_SPLIT_RE = re.compile(r"\s*(?:;\s*|\bafter that\b|\band then\b|\bthen\b)\s*", re.I)
_EMAIL_RE = re.compile(r"\b(e-?mail|gmail|\bmail\b|mail_send|mail_compose)\b", re.I)
_WHATSAPP_RE = re.compile(r"\bwhats\s*app\b|\bwhatsapp\b", re.I)
_COMPOUND_RE = re.compile(r";|\bafter that\b|\band then\b|\bthen\b", re.I)
_DEMO_RE = re.compile(r"\bdemo\b", re.I)
_SECOND_CMD_RE = re.compile(
    r"^(open|launch|close|type|play|search|send|press|hit|youtube|spotify)\b",
    re.I,
)


def _first_command(low):
    """Return first command chunk (before then/after that/;/and)."""
    part = _SPLIT_RE.split(low or "")[0] if low else ""
    # Split on standalone " and " to isolate the first command.
    bits = re.split(r"\s+\band\b\s+", part)
    return bits[0] if bits else part


def _is_and_compound(stripped):
    """True when ' and ' joins what looks like two commands."""
    parts = re.split(r"\s+\band\b\s+", stripped or "")
    if len(parts) < 2:
        return False
    # If every chunk after the first starts with a command verb, compound.
    for tail in parts[1:]:
        if _SECOND_CMD_RE.match(tail.strip()):
            return True
        # Two local cues joined by 'and' (e.g. spotify + type) is compound.
        if _OPEN_SPOTIFY_RE.search(tail) or "youtube" in tail.lower():
            return True
    # Fallback: first chunk is a local cue and there is a trailing chunk
    # that looks like a second instruction (heuristic: >1 word or verb).
    first = parts[0].strip().lower()
    first_is_local = bool(
        _OPEN_SPOTIFY_RE.search(first)
        or _TYPE_PREFIX_RE.match(parts[0].strip())
        or "youtube" in first
    )
    if first_is_local and any(p.strip() for p in parts[1:]):
        # Only treat as compound when tail is not a tiny query word;
        # e.g. "youtube rock and roll" tail "roll" is single word query,
        # so do not block. "open spotify and type hi" tail has verb.
        # Heuristic: tail with 2+ words or starting with verb => compound.
        for tail in parts[1:]:
            t = tail.strip()
            if not t:
                continue
            if len(t.split()) >= 2:
                return True
    return False


def skip_muse(text):
    """Return True when *text* is a simple local command, else False.

    True for:
      - ``open spotify`` (case insensitive)
      - ``type ...`` (starts with ``type `` after strip, case insensitive)
      - ``youtube ...`` (first command contains ``youtube``)
    False for email/whatsapp/compound/demo and everything else.
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped:
        return False
    low = stripped.lower()

    # Never skip for email / whatsapp.
    if _EMAIL_RE.search(low) or _WHATSAPP_RE.search(low):
        return False
    # Never skip compound (then/and then/after that/;) or demo keyword.
    if _COMPOUND_RE.search(low):
        return False
    if _DEMO_RE.search(low):
        return False
    # 'and' joining two commands counts as compound -> no skip.
    if _is_and_compound(stripped):
        return False

    # open spotify (case insensitive).
    if _OPEN_SPOTIFY_RE.search(low):
        return True
    # type ... (starts with "type ").
    if _TYPE_PREFIX_RE.match(stripped):
        return True
    # youtube ... (first command contains youtube).
    first = _first_command(low)
    if "youtube" in first:
        return True
    return False


def island_budget_line():
    """Return a short (<=40 chars) status line containing 'budget'."""
    return "island budget ok"


def hop_cap_exceeded(used, cap):
    """Return True when used >= cap, else False."""
    try:
        return float(used) >= float(cap)
    except Exception:
        try:
            return bool(used >= cap)
        except Exception:
            return False
