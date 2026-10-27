"""Muse tools schema, payload builders, parsing, and redaction (stdlib only)."""

import json


SPARK = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"
VOICE = "muse-voice-transcribe-1.0"
RESPONSES_URL = "https://api.meta.ai/v1/responses"

MAX_MIND_CONTEXT_CHARS = 2000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "whatsapp_send",
            "description": "Send a WhatsApp message",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient"},
                    "text": {"type": "string", "description": "Message text"},
                },
                "required": ["to", "text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Play music matching a query",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Music search query"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_compose",
            "description": "Compose an email",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient"},
                    "subject": {"type": "string", "description": "Email subject"},
                },
                "required": ["to", "subject"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dial",
            "description": "Dial a phone number or contact",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Number or contact to dial"},
                },
                "required": ["to"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open an application",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "App name to open"},
                },
                "required": ["app"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_into",
            "description": "Type text into the focused field",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
]

_NAME_ALIASES = {
    "music_play": "play_music",
    "phone_dial": "dial",
    "app_open": "open_app",
    "type": "type_into",
}


def build_headers(api_key):
    """Return request headers for the Muse API."""
    return {
        "Authorization": "Bearer " + str(api_key),
        "Content-Type": "application/json",
    }


def redact(headers):
    """Return a copy of headers with the Authorization value masked."""
    copied = dict(headers or {})
    for key in list(copied.keys()):
        if isinstance(key, str) and key.lower() == "authorization":
            copied[key] = "Bearer ***"
    copied["Authorization"] = "Bearer ***"
    return copied


def _clamp_mind_context(mind_context, limit=MAX_MIND_CONTEXT_CHARS):
    """Clamp mind context to a bounded string."""
    if mind_context is None:
        return ""
    if not isinstance(mind_context, str):
        try:
            mind_context = str(mind_context)
        except Exception:
            return ""
    mind_context = mind_context.strip()
    if not mind_context:
        return ""
    if len(mind_context) > limit:
        mind_context = mind_context[:limit]
    return mind_context


def inject_mind(payload, mind_context):
    """Prepend clamped mind context to the user input text.

    Only mutates input text content in place; never adds ``Authorization``
    or bearer secrets. Returns the same payload object.
    """
    if not isinstance(payload, dict):
        return payload
    # Payload body must never carry Authorization / secrets.
    payload.pop("Authorization", None)
    payload.pop("authorization", None)
    clamped = _clamp_mind_context(mind_context)
    if not clamped:
        return payload
    prefix = "[mind]\n" + clamped + "\n\n"
    try:
        items = payload.get("input")
    except Exception:
        return payload
    if not isinstance(items, list) or not items:
        return payload
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("role") == "user"
            and isinstance(item.get("content"), str)
        ):
            item["content"] = prefix + item["content"]
            return payload
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("content"), str):
            item["content"] = prefix + item["content"]
            return payload
    return payload


def build_complete_payload(model, text, mind_context=None):
    """Build a Responses API payload with tools and auto tool choice.

    If mind_context is given, its clamped form is prepended to the user
    content. The payload never contains ``Authorization`` or bearer secrets
    (auth belongs in headers, not the body).
    """
    payload = {
        "model": model,
        "input": [{"role": "user", "content": text}],
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    if mind_context:
        inject_mind(payload, mind_context)
    # Defensive: never leak Authorization into the body.
    payload.pop("Authorization", None)
    payload.pop("authorization", None)
    return payload


def _coerce_args(raw):
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
        return {}
    return {}


def _extract_name_and_args(item):
    name = item.get("name")
    sentinel = object()
    raw = item.get("arguments", sentinel)
    if raw is sentinel:
        for key in ("args", "input", "parameters"):
            val = item.get(key, sentinel)
            if val is not sentinel:
                raw = val
                break
        else:
            raw = None
    nested = item.get("function")
    if isinstance(nested, dict):
        if name is None:
            name = nested.get("name")
        if raw is None:
            raw = nested.get("arguments", nested.get("args", nested.get("input", None)))
    nested_fc = item.get("function_call")
    if isinstance(nested_fc, dict):
        if name is None:
            name = nested_fc.get("name")
        if raw is None:
            raw = nested_fc.get("arguments", nested_fc.get("args", nested_fc.get("input", None)))
    if name is None:
        for key in ("tool", "function_name"):
            val = item.get(key)
            if isinstance(val, str):
                name = val
                break
    if not isinstance(name, str):
        return None, {}
    args = _coerce_args(raw)
    return name, args


def parse_function_calls(obj):
    """Walk a Muse JSON dict (or list of output items) into plan steps.

    Returns a list of dicts: {id, tool, args, device, after}.
    """
    if isinstance(obj, dict):
        output = obj.get("output", [])
    elif isinstance(obj, list):
        output = obj
    else:
        return []
    if not isinstance(output, list):
        return []
    steps = []
    counter = 0
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in ("function_call", "tool_call"):
            continue
        name, args = _extract_name_and_args(item)
        if name is None:
            continue
        tool = _NAME_ALIASES.get(name, name)
        device = "phone"
        dev = args.get("device")
        if isinstance(dev, str) and dev.strip().lower() in ("laptop", "server"):
            device = dev.strip().lower()
        if args.get("on_laptop") is True:
            device = "laptop"
        after_val = item.get("after", None)
        if isinstance(after_val, list):
            after = list(after_val)
        else:
            after = []
        counter += 1
        steps.append(
            {
                "id": "s%d" % counter,
                "tool": tool,
                "args": args,
                "device": device,
                "after": after,
            }
        )
    return steps


__all__ = [
    "SPARK",
    "WONDER",
    "VOICE",
    "RESPONSES_URL",
    "TOOLS",
    "build_headers",
    "redact",
    "build_complete_payload",
    "inject_mind",
    "parse_function_calls",
]
