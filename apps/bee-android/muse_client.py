"""Muse Responses client (stdlib only).

Covers the Meta Muse ``/responses`` endpoint helpers shared with the
Java ``MuseClient``. Never prints or logs the API key.
"""

import json
import urllib.request

BASE = "https://api.meta.ai/v1"
RESPONSES_URL = BASE + "/responses"

SPARK = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"
VOICE = "muse-voice-transcribe-1.0"

__all__ = [
    "BASE",
    "RESPONSES_URL",
    "SPARK",
    "WONDER",
    "VOICE",
    "build_headers",
    "redact",
    "user_message",
    "parse_sse_events",
    "capture_response_id",
    "is_expired_ref",
    "build_payload",
    "post",
]


def build_headers(api_key):
    """Return request headers for the Responses API.

    Never prints the key.
    """
    return {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type": "application/json",
    }


def redact(headers):
    """Return a copy of ``headers`` with the Authorization value masked."""
    if headers is None:
        return {}
    copied = dict(headers)
    if "Authorization" in copied:
        copied["Authorization"] = "Bearer ***"
    return copied


def user_message(text):
    """Wrap ``text`` as a ``message`` / ``user`` / ``input_text`` item."""
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }


def parse_sse_events(buffer):
    """Parse a raw SSE buffer into a list of dicts.

    Only ``data: <JSON>`` lines are considered. Blank lines, non-data
    lines, the ``[DONE]`` sentinel, and non-JSON / non-dict payloads are
    skipped.
    """
    if not buffer:
        return []
    if not isinstance(buffer, str):
        try:
            buffer = str(buffer)
        except Exception:
            return []
    events = []
    for raw_line in buffer.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def capture_response_id(event):
    """Extract ONLY ``event['response']['id']``.

    Never returns the top-level SSE/event ``id``. Returns ``None`` unless
    ``response`` is a dict holding a non-empty string ``id``.
    """
    if not isinstance(event, dict):
        return None
    resp = event.get("response")
    if not isinstance(resp, dict):
        return None
    rid = resp.get("id")
    if isinstance(rid, str) and rid:
        return rid
    return None


def _coerce_text(msg):
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        parts = []
        for key in ("message", "error", "detail", "code", "type"):
            val = msg.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
            elif isinstance(val, dict):
                for sub in ("message", "code", "type", "detail"):
                    sub_val = val.get(sub)
                    if isinstance(sub_val, str) and sub_val:
                        parts.append(sub_val)
        if parts:
            return " ".join(parts)
        try:
            return str(msg)
        except Exception:
            return ""
    try:
        return str(msg)
    except Exception:
        return ""


def is_expired_ref(msg):
    """Return True when ``msg`` references a missing/expired response.

    True when the referenced response was not found or expired. Handles
    plain strings, dict-shaped errors, and other objects via ``str()``.
    """
    text = _coerce_text(msg)
    if not text:
        return False
    low = text.lower()
    if "expir" in low:
        return True
    if "not found" in low or "not_found" in low:
        return True
    return False


def build_payload(model, text, previous_response_id=None, stream=False):
    """Build a ``/responses`` JSON payload (stdlib types only)."""
    if isinstance(text, list):
        inputs = list(text)
    else:
        inputs = [user_message(text)]
    payload = {"model": model, "input": inputs}
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    if stream:
        payload["stream"] = True
    return payload


def post(api_key, payload, timeout=30):
    """POST ``payload`` to RESPONSES_URL with stdlib urllib.

    Never prints the key. Returns the decoded JSON body (or raw text
    under ``{"text": ...}`` when the body is not JSON).
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(RESPONSES_URL, data=data, method="POST")
    for key, value in build_headers(api_key).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {"text": raw}
    return parsed
