"""Driving vs desk context profile (stdlib only)."""

from __future__ import annotations

import re

try:  # Reuse config caps when importable; duplicate 6/8 otherwise.
    from config import hop_cap as _cfg_hop_cap  # type: ignore
except Exception:
    _cfg_hop_cap = None  # type: ignore

try:
    from config import is_driving as _cfg_is_driving  # type: ignore
except Exception:
    _cfg_is_driving = None  # type: ignore

_DRIVING_HOP_CAP = 6
_DESK_HOP_CAP = 8

_FALLBACK_REPLY = "On it."
_CONFIRM_SUFFIX = " Say yes or cancel."
_MAX_PROMPT_LEN = 40

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def normalize(context=None) -> str:
    """Normalize *context* to ``"desk"`` or ``"driving"``."""
    if _cfg_is_driving is not None:
        try:
            return "driving" if _cfg_is_driving(context) else "desk"
        except Exception:
            pass
    raw = context
    try:
        if hasattr(raw, "context"):
            raw = getattr(raw, "context")
        elif isinstance(raw, dict) and "context" in raw:
            raw = raw.get("context")
    except Exception:
        pass
    try:
        value = str(raw or "").strip().lower()
    except Exception:
        value = ""
    if value == "driving":
        return "driving"
    return "desk"


def profile(context=None) -> dict:
    """Return per-context profile dict."""
    name = normalize(context)
    driving = name == "driving"
    # Prefer config hop_cap when it agrees with the 6/8 spec; otherwise
    # fall back to the duplicated caps so this module never fails.
    hop = _DRIVING_HOP_CAP if driving else _DESK_HOP_CAP
    if _cfg_hop_cap is not None:
        try:
            cfg_val = int(_cfg_hop_cap(name))
            if driving and cfg_val == _DRIVING_HOP_CAP:
                hop = cfg_val
            elif not driving and cfg_val == _DESK_HOP_CAP:
                hop = cfg_val
        except Exception:
            pass
    return {
        "name": name,
        "hop_cap": hop,
        "confirm_via": "voice",
        "max_reply_sentences": 1 if driving else 2,
        "max_reply_chars": 80 if driving else 160,
        "chip_allowed": False if driving else True,
    }


def shorten(reply, context=None) -> str:
    """Shorten *reply* to the context budget; never return empty."""
    prof = profile(context)
    max_sentences = int(prof.get("max_reply_sentences", 2) or 2)
    max_chars = int(prof.get("max_reply_chars", 160) or 160)
    try:
        text = str(reply if reply is not None else "").strip()
    except Exception:
        text = ""
    if not text:
        return _FALLBACK_REPLY
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return _FALLBACK_REPLY
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text) if p and p.strip()]
    if not parts:
        parts = [text]
    kept = " ".join(parts[:max(1, max_sentences)]).strip()
    if not kept:
        return _FALLBACK_REPLY
    if len(kept) > max_chars:
        kept = kept[:max_chars].rstrip()
    if not kept:
        return _FALLBACK_REPLY
    return kept


def confirm_prompt(tool) -> str:
    """Return a short voice-confirm one-liner (<=40 chars)."""
    try:
        raw = str(tool if tool is not None else "").strip()
    except Exception:
        raw = ""
    label = raw.replace("_", " ").replace("-", " ").strip()
    label = re.sub(r"\s+", " ", label).strip()
    if label:
        words = []
        for word in label.split(" "):
            if not word:
                continue
            words.append(word[:1].upper() + word[1:])
        label = " ".join(words).strip()
    if not label:
        label = "Confirm"
    budget = _MAX_PROMPT_LEN - len(_CONFIRM_SUFFIX) - 1  # room for "?"
    if budget < 1:
        budget = 1
    if len(label) > budget:
        label = label[:budget].rstrip()
        if not label:
            label = "Confirm"[:budget]
    prompt = "%s?%s" % (label, _CONFIRM_SUFFIX)
    if len(prompt) > _MAX_PROMPT_LEN:
        prompt = prompt[:_MAX_PROMPT_LEN].rstrip()
    return prompt


def is_voice_confirm(context=None) -> bool:
    """Return True always — ride confirmations go over voice."""
    return True


__all__ = [
    "normalize",
    "profile",
    "shorten",
    "confirm_prompt",
    "is_voice_confirm",
]
