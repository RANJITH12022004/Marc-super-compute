"""voice_gate.py - stdlib-only transcript classifier."""

import re

WAKE_PHRASES = ("hey jarvis", "hey marc", "hey mark", "remark")

_PAUSE_CHARS = set(list(",.;:!?") + ["\u2026", "\u2014", "\u2013", "-", '"', "'", "(", "[", "{"])

_REFUSE_TOKENS = ("reboot", "shutdown", "sudo", "rm -rf", "poweroff")

_CONFIRM_PHRASES = (
    "yes",
    "yeah",
    "yep",
    "ok",
    "okay",
    "send it",
    "send that",
    "do it",
    "go ahead",
)

_CANCEL_PHRASES = (
    "no",
    "nope",
    "cancel",
    "nevermind",
    "never mind",
    "don't send",
    "dont send",
    "do not send",
    "stop",
)

_SLEEP_RE = re.compile(r"\bsleep\b", re.IGNORECASE)
_GOODBYE_RE = re.compile(r"\bgood\s*bye\b|\bgood-bye\b", re.IGNORECASE)
_STOP_MARC_RE = re.compile(r"\bstop\s+marc\b", re.IGNORECASE)


def _strip_pause(after_raw):
    t = after_raw.lstrip()
    while t and (t[0] in _PAUSE_CHARS or t[0].isspace()):
        t = t[1:].lstrip()
        if len(t) == 0:
            break
    return t.strip()


def _match_wake(stripped, low):
    for phrase in sorted(WAKE_PHRASES, key=len, reverse=True):
        if low == phrase:
            return (phrase, "")
        if low.startswith(phrase):
            nxt_idx = len(phrase)
            nxt_char = low[nxt_idx] if nxt_idx < len(low) else ""
            if nxt_char != "" and nxt_char.isalnum():
                continue
            after_raw = stripped[len(phrase):]
            if phrase == "hey mark":
                after_stripped = after_raw.strip()
                if after_stripped == "":
                    return (phrase, "")
                first = after_stripped[0]
                if first in _PAUSE_CHARS:
                    return (phrase, _strip_pause(after_raw))
                return ("IGNORE_HEY_MARK", None)
            return (phrase, _strip_pause(after_raw))
    return (None, None)


def _normalize_pending(s):
    t = s.strip().lower()
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(" \t\n\r.,!?;:\u2026\u2014\u2013-\"'()[]{}").strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _phrase_match(norm, phrases):
    for p in phrases:
        if norm == p:
            return True
        if norm.startswith(p):
            rest_idx = len(p)
            if rest_idx >= len(norm):
                return True
            nxt = norm[rest_idx]
            if not nxt.isalnum():
                return True
    return False


def classify(text, listening=False, pending_confirm=False, context="desk"):
    original = text if isinstance(text, str) else ("" if text is None else str(text))
    stripped = original.strip()
    low = stripped.lower()

    if stripped == "":
        return {"intent": "utterance", "remainder": "", "context": context}

    for tok in _REFUSE_TOKENS:
        if tok in low:
            return {"intent": "refuse", "remainder": stripped, "context": context}

    kind, rem = _match_wake(stripped, low)
    if kind == "IGNORE_HEY_MARK":
        return {"intent": "ignore", "remainder": original, "context": context}
    if kind is not None:
        return {"intent": "wake", "remainder": rem, "context": context}

    if _SLEEP_RE.search(stripped) or _GOODBYE_RE.search(stripped) or _STOP_MARC_RE.search(stripped):
        return {"intent": "sleep", "remainder": stripped, "context": context}

    if pending_confirm:
        norm = _normalize_pending(stripped)
        if _phrase_match(norm, _CONFIRM_PHRASES):
            return {"intent": "confirm", "remainder": stripped, "context": context}
        if _phrase_match(norm, _CANCEL_PHRASES):
            return {"intent": "cancel", "remainder": stripped, "context": context}

    return {"intent": "utterance", "remainder": stripped, "context": context}
