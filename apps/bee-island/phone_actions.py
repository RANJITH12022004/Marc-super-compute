"""Phone action intents (pure, stdlib only).

Maps planner/Muse tool steps to Android intent dicts used by PhoneActions.
"""

__all__ = ["intent_for"]

_ACTION_SEND = "android.intent.action.SEND"
_ACTION_SENDTO = "android.intent.action.SENDTO"
_ACTION_VIEW = "android.intent.action.VIEW"
_ACTION_DIAL = "android.intent.action.DIAL"
_ACTION_MAIN = "android.intent.action.MAIN"

_WHATSAPP_PACKAGE = "com.whatsapp"
_SPOTIFY_PACKAGE = "com.spotify.music"
_YOUTUBE_PACKAGE = "com.google.android.youtube"
_SPOTIFY_MARKET = "market://details?id=com.spotify.music"

_ALIASES = {
    "music_play": "play_music",
    "phone_dial": "dial",
    "app_open": "open_app",
    "type": "type_into",
}

_KNOWN_TOOLS = {
    "whatsapp_send",
    "play_music",
    "mail_compose",
    "dial",
    "open_app",
    "type_into",
}


def _to_str(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _has_blocked_text(value):
    try:
        low = _to_str(value).lower()
    except Exception:
        return False
    return "reboot" in low or "shutdown" in low


def _args_contain_blocked(args):
    # Recursively scan arg values for reboot/shutdown.
    stack = [args]
    seen = 0
    while stack:
        seen += 1
        if seen > 1000:
            return False
        cur = stack.pop()
        if isinstance(cur, dict):
            for v in cur.values():
                if isinstance(v, str):
                    if _has_blocked_text(v):
                        return True
                elif isinstance(v, dict):
                    stack.append(v)
                elif isinstance(v, (list, tuple, set)):
                    stack.append(v)
                elif v is not None and not isinstance(v, (int, float, bool)):
                    try:
                        if _has_blocked_text(v):
                            return True
                    except Exception:
                        pass
        elif isinstance(cur, (list, tuple, set)):
            for v in cur:
                if isinstance(v, str):
                    if _has_blocked_text(v):
                        return True
                elif isinstance(v, (dict, list, tuple, set)):
                    stack.append(v)
        elif isinstance(cur, str):
            if _has_blocked_text(cur):
                return True
    return False


def _extract_tool_and_args(step):
    if step is None:
        return None, {}
    if isinstance(step, dict):
        tool = step.get("tool", None)
        if tool is None:
            for key in ("name", "function_name", "function", "tool_name", "action"):
                val = step.get(key)
                if isinstance(val, str):
                    tool = val
                    break
                if isinstance(val, dict):
                    nested_name = val.get("name")
                    if isinstance(nested_name, str):
                        tool = nested_name
                        break
        args = step.get("args", None)
        if args is None:
            for key in ("arguments", "input", "parameters", "params"):
                if key in step:
                    args = step.get(key)
                    break
            else:
                # Nested function container may hold arguments.
                nested = step.get("function")
                if isinstance(nested, dict):
                    for key in ("arguments", "args", "input", "parameters"):
                        if key in nested:
                            args = nested.get(key)
                            break
                if args is None:
                    args = {}
        return tool, args
    if isinstance(step, (list, tuple)):
        # Tolerate tuple-like planner results: (tool, args, device).
        try:
            if len(step) == 0:
                return None, {}
            tool = step[0] if len(step) >= 1 else None
            args = step[1] if len(step) >= 2 else {}
            if isinstance(tool, dict):
                return _extract_tool_and_args(tool)
            return tool, args
        except Exception:
            return None, {}
    return None, {}


def _coerce_args(args):
    if args is None:
        return {}
    if isinstance(args, dict):
        return dict(args)
    return {}


def _first_nonempty(args, keys):
    for key in keys:
        if isinstance(args, dict) and key in args:
            val = _to_str(args.get(key)).strip()
            # For type_into text we want to preserve inner text but
            # strip detection still works; return raw string coerced.
            if val != "":
                # Return original coerced (stripped of outer whitespace
                # except for type text where we keep as-is? callers
                # handle stripping as needed).
                return _to_str(args.get(key))
    return ""


def intent_for(step):
    """Map a planner step to an Android intent dict or None.

    Returns ``{action, package, data, extras}`` or ``None`` for
    unknown/refuse tools. Never returns reboot/shutdown intents.
    """
    tool_raw, args_raw = _extract_tool_and_args(step)
    if not isinstance(tool_raw, str):
        return None
    tool = tool_raw.strip().lower()
    if not tool:
        return None
    # Never include reboot/shutdown, even as tool names.
    if "reboot" in tool or "shutdown" in tool:
        return None
    tool = _ALIASES.get(tool, tool)
    if "reboot" in tool or "shutdown" in tool:
        return None
    if tool not in _KNOWN_TOOLS:
        return None
    # Refuse-like pseudo tools.
    if tool in ("refuse", "reject", "cancel"):
        return None

    args = _coerce_args(args_raw)
    # Block any reboot/shutdown content in args.
    try:
        if _args_contain_blocked(args):
            return None
    except Exception:
        return None

    if tool == "whatsapp_send":
        body = ""
        for key in ("text", "sms_body", "message", "body"):
            if key in args and args.get(key) is not None:
                candidate = _to_str(args.get(key))
                if candidate.strip() != "":
                    body = candidate
                    break
        else:
            # All empty/missing: default to empty string.
            for key in ("text", "sms_body", "message", "body"):
                if key in args:
                    body = _to_str(args.get(key))
                    break
        if _has_blocked_text(body):
            return None
        return {
            "action": _ACTION_SEND,
            "package": _WHATSAPP_PACKAGE,
            "data": None,
            "extras": {"sms_body": body},
        }

    if tool == "play_music":
        query = ""
        for key in ("query", "text", "q", "song", "title", "music"):
            if key in args and args.get(key) is not None:
                candidate = _to_str(args.get(key)).strip()
                if candidate != "":
                    query = candidate
                    break
        if _has_blocked_text(query):
            return None
        if not query:
            return {
                "action": _ACTION_VIEW,
                "package": _SPOTIFY_PACKAGE,
                "data": _SPOTIFY_MARKET,
                "extras": {},
            }
        return {
            "action": _ACTION_VIEW,
            "package": _SPOTIFY_PACKAGE,
            "data": "spotify:search:" + query,
            "extras": {},
        }

    if tool == "mail_compose":
        to = ""
        for key in ("to", "recipient", "email", "address"):
            if key in args and args.get(key) is not None:
                candidate = _to_str(args.get(key)).strip()
                if candidate != "":
                    to = candidate
                    break
        else:
            for key in ("to", "recipient", "email", "address"):
                if key in args:
                    to = _to_str(args.get(key)).strip()
                    break
        subject = ""
        for key in ("subject", "title"):
            if key in args and args.get(key) is not None:
                candidate = _to_str(args.get(key))
                if candidate.strip() != "":
                    subject = candidate
                    break
        else:
            for key in ("subject", "title"):
                if key in args:
                    subject = _to_str(args.get(key))
                    break
        if _has_blocked_text(to) or _has_blocked_text(subject):
            return None
        return {
            "action": _ACTION_SENDTO,
            "package": None,
            "data": "mailto:" + to,
            "extras": {"subject": subject},
        }

    if tool == "dial":
        to = ""
        for key in ("to", "number", "phone", "contact", "tel"):
            if key in args and args.get(key) is not None:
                candidate = _to_str(args.get(key)).strip()
                if candidate != "":
                    to = candidate
                    break
        else:
            for key in ("to", "number", "phone", "contact", "tel"):
                if key in args:
                    to = _to_str(args.get(key)).strip()
                    break
        if _has_blocked_text(to):
            return None
        return {
            "action": _ACTION_DIAL,
            "package": None,
            "data": "tel:" + to,
            "extras": {},
        }

    if tool == "open_app":
        app = ""
        for key in ("app", "name", "package", "app_name", "application"):
            if key in args and args.get(key) is not None:
                candidate = _to_str(args.get(key)).strip()
                if candidate != "":
                    app = candidate
                    break
        else:
            for key in ("app", "name", "package", "app_name", "application"):
                if key in args:
                    app = _to_str(args.get(key)).strip()
                    break
        if _has_blocked_text(app):
            return None
        low = app.lower()
        if "spotify" in low:
            return {
                "action": _ACTION_MAIN,
                "package": _SPOTIFY_PACKAGE,
                "data": None,
                "extras": {},
            }
        if "youtube" in low or "youtu" in low:
            return {
                "action": _ACTION_MAIN,
                "package": _YOUTUBE_PACKAGE,
                "data": None,
                "extras": {},
            }
        if app and "." in app and " " not in app:
            return {
                "action": _ACTION_MAIN,
                "package": app,
                "data": None,
                "extras": {},
            }
        return {
            "action": _ACTION_MAIN,
            "package": None,
            "data": None,
            "extras": {},
        }

    if tool == "type_into":
        text = ""
        for key in ("text", "body", "message", "query", "input"):
            if key in args and args.get(key) is not None:
                # Preserve text as-is (do not strip inner content).
                candidate = _to_str(args.get(key))
                if candidate.strip() != "":
                    text = candidate
                    break
        else:
            for key in ("text", "body", "message", "query", "input"):
                if key in args:
                    text = _to_str(args.get(key))
                    break
        if _has_blocked_text(text):
            return None
        return {
            "action": "type",
            "package": None,
            "data": None,
            "extras": {"text": text},
        }

    return None
