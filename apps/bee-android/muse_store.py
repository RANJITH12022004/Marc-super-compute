"""Muse key-vault mask store (stdlib only, no network, no secrets).

Mirrors apps/bee-android/src/com/marc/island/MuseStore.java.
On device, the real key lives in EncryptedSharedPreferences; this module
models the same contract with a plain dict so it stays testable.

Only the masked form is ever shown; the mask never contains the plaintext.
"""

from __future__ import annotations

ELLIPSIS = "\u2026"

SPARK_MODEL = "muse-spark-1.3"
WONDER_MODEL = "muse-wonder-1.0"
VOICE_MODEL = "muse-voice-transcribe-1.0"

# Store field names (kept in sync with MuseStore.java).
KEY_API_KEY = "api_key"
KEY_MASK = "key_mask"


def mask_key(key) -> str:
    """Return a masked view of ``key`` showing only the last 4 chars.

    Examples:
        mask_key('LLM_abcdefghijk') -> 'LLM_\u2026hijk'
        mask_key('') -> ''
        mask_key(None) -> ''

    The returned mask never equals the plaintext and never contains the
    full plaintext for keys longer than 4 chars.
    """
    if key is None:
        return ""
    s = str(key) if not isinstance(key, str) else key
    if s == "":
        return ""
    if len(s) <= 4:
        # Too short to reveal anything: mask everything.
        return ELLIPSIS * len(s)
    if len(s) <= 8:
        # Short key: ellipsis + last 4 only (no prefix to avoid overlap).
        return ELLIPSIS + s[-4:]
    # Long key: first 4 + ellipsis + last 4, e.g. 'LLM_...hijk'.
    return s[:4] + ELLIPSIS + s[-4:]


def save_key(store: dict, key) -> str:
    """Store ``key`` in ``store`` and record its masked view.

    Rejects empty/blank keys with ValueError. Stores the real key under
    ``api_key`` (alias ``key``) and the masked view under ``key_mask``
    (aliases ``mask``/``masked_key``). Returns the mask.
    """
    if store is None or not isinstance(store, dict):
        raise TypeError("store must be a dict")
    s = "" if key is None else (key if isinstance(key, str) else str(key))
    if not isinstance(s, str) or s.strip() == "":
        raise ValueError("key must be a non-empty string")
    mask = mask_key(s)
    store[KEY_API_KEY] = s
    store["key"] = s
    store[KEY_MASK] = mask
    store["mask"] = mask
    store["masked_key"] = mask
    return mask


def has_key(store: dict) -> bool:
    """Return True when ``store`` holds a non-blank key."""
    if store is None or not isinstance(store, dict):
        return False
    for field in (KEY_API_KEY, "key"):
        try:
            v = store.get(field)
        except AttributeError:
            return False
        if isinstance(v, str) and v.strip() != "":
            return True
        if v is not None and not isinstance(v, str) and str(v).strip() != "":
            return True
    return False


def get_mask(store: dict) -> str:
    """Return the stored mask, or '' when absent."""
    if store is None or not isinstance(store, dict):
        return ""
    for field in (KEY_MASK, "mask", "masked_key"):
        v = store.get(field)
        if isinstance(v, str) and v != "":
            return v
    # Fall back to deriving from the stored key (never the plaintext itself).
    for field in (KEY_API_KEY, "key"):
        v = store.get(field)
        if isinstance(v, str) and v != "":
            return mask_key(v)
    return ""


def clear_key(store: dict) -> None:
    """Remove any stored key and mask from ``store``."""
    if store is None or not isinstance(store, dict):
        raise TypeError("store must be a dict")
    for field in (KEY_API_KEY, "key", KEY_MASK, "mask", "masked_key"):
        if field in store:
            del store[field]


def default_models() -> dict:
    """Return default model names for spark/wonder/voice."""
    return {
        "spark": SPARK_MODEL,
        "wonder": WONDER_MODEL,
        "voice": VOICE_MODEL,
    }


def needle_enabled() -> bool:
    """Needle is never enabled in this vault (always False)."""
    return False


__all__ = [
    "ELLIPSIS",
    "SPARK_MODEL",
    "WONDER_MODEL",
    "VOICE_MODEL",
    "KEY_API_KEY",
    "KEY_MASK",
    "mask_key",
    "save_key",
    "has_key",
    "get_mask",
    "clear_key",
    "default_models",
    "needle_enabled",
]
