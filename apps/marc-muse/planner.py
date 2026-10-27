"""Muse planner — local heuristic + Muse spark fallback.

Contract per docs/marc_prd.md:
  {reply, session_id, plan[{id, after, kind, device, tool, args, confirm}]}

Rules:
- confirm=true when tool is in CONFIRM_TOOLS.
- In sandbox, confirm-gated send steps still appear but with
  confirm=true and args.draft=true (never auto-send).
- Split sequential steps on then / and then / after that.
- Detect repeat ('for each', 'N times') and followup ('send it', 'the first').
- Never call needle / laya / qwen binaries or ports.
- Hard-refuse reboot / shutdown / sudo / rm -rf / with empty plan.
"""

import os
import re

CONFIRM_DEFAULT = (
    "mail_send,mail_compose,whatsapp_send,instagram_send,"
    "sms_send,calendar_create,dial,open_food_search"
)

# Tools that send externally (subset of CONFIRM_TOOLS that become drafts).
SEND_TOOLS = {
    "mail_send",
    "mail_compose",
    "whatsapp_send",
    "instagram_send",
    "sms_send",
    "calendar_create",
    "dial",
}

_STOPPED = False


def get_mode():
    mode = (os.environ.get("MARC_MODE") or "sandbox").strip().lower()
    return mode if mode in ("sandbox", "live") else "sandbox"


def get_confirm_tools():
    raw = os.environ.get("CONFIRM_TOOLS", CONFIRM_DEFAULT)
    return {t.strip() for t in raw.split(",") if t.strip()}


def is_stopped():
    return _STOPPED


def set_stopped():
    global _STOPPED
    _STOPPED = True


def clear_stopped():
    global _STOPPED
    _STOPPED = False


def is_paused():
    for key in ("MARC_CREDIT_PAUSED", "MARC_BUDGET_PAUSED", "MARC_SPARK_PAUSED"):
        if (os.environ.get(key) or "").strip().lower() in ("1", "true", "yes"):
            return True
    if (os.environ.get("MARC_CREDIT_DAILY_CAP") or "").strip() == "0":
        return True
    if (os.environ.get("MARC_CREDIT_REMAINING") or "").strip() == "0":
        return True
    try:
        import credit

        if credit.paused():
            return True
    except Exception:
        pass
    return False


_REFUSE_RES = [
    re.compile(r"\brm\s+(-[a-z]*r[a-z]*\s+)+/\s*($|\s)", re.I),
    re.compile(r"\brm\s+(-[a-z]*r[a-z]*\s+)+/\*", re.I),
    re.compile(r"\brm\s+-rf\s+/\b", re.I),
    re.compile(r"\breboot\b", re.I),
    re.compile(r"\bshutdown\b", re.I),
    re.compile(r"\bpoweroff\b", re.I),
    re.compile(r"\bsudo\b", re.I),
]


def is_refused(text):
    t = text or ""
    return any(rx.search(t) for rx in _REFUSE_RES)


_SPLIT_RE = re.compile(r"\s*(?:;\s*|\bafter that\b|\band then\b|\bthen\b)\s*", re.I)

_REPEAT_RES = [
    re.compile(r"\bfor each\b", re.I),
    re.compile(r"\b(\d+)\s*times\b", re.I),
    re.compile(r"\brepeat\b", re.I),
    re.compile(r"\bevery\b.+\b(day|night|morning|hour)\b", re.I),
]

_FOLLOWUP_HINTS = ("send it", "the first", "next", "pause", "resume")

_VALID_DEVICES = ("phone", "laptop", "server")


def _split_clauses(text):
    parts = [p.strip(" ,.") for p in _SPLIT_RE.split(text or "")]
    return [p for p in parts if p]


def _expand_combined(clause):
    """Split 'open X type Y send it' style single chunks without 'then'."""
    out = [clause]
    m = re.match(r"^(open\s+.+?)\s+(?:and\s+)?type\s+(.+)$", clause.strip(), re.I)
    if m:
        out = [m.group(1).strip(), "type " + m.group(2).strip()]
    expanded = []
    for c in out:
        m2 = re.match(
            r"^(.+?)\s+(?:and\s+)?(send it|press enter|hit send|hit enter)\s*$",
            c,
            re.I,
        )
        if m2 and len(m2.group(1).strip()) > 2:
            expanded += [m2.group(1).strip(), m2.group(2).strip()]
        else:
            expanded.append(c)
    return expanded


def _resolve_device(clause, target):
    low = (clause or "").lower()
    if "on my phone" in low or "on the phone" in low:
        return "phone"
    if "on my laptop" in low or "on the laptop" in low:
        return "laptop"
    if "on the server" in low or "on my server" in low:
        return "server"
    t = (target or "").strip().lower()
    if t in _VALID_DEVICES:
        return t
    if re.search(r"server status|check (the )?server|service_|docker|cpu|ram", low):
        return "server"
    if re.search(r"gmail|google drive|calendar invite|spreadsheet", low):
        return "laptop"
    return "phone"


def _strip_device_phrase(clause):
    return re.sub(r"\bon (my|the) (phone|laptop|server)\b", "", clause or "", flags=re.I).strip()


def _clause_to_tool(clause):
    """Return (tool, args) for one clause."""
    c = _strip_device_phrase(clause)
    low = c.lower().strip()

    if re.match(r"^(send it|press enter|hit send|hit enter|send)$", low):
        return "type_into", {"text": "", "send": True}
    if re.match(r"^(next|pause|resume)\b", low):
        return "type_into", {"text": low, "send": False}

    # 'open Google/YouTube and search for <q>' without a 'then' splitter.
    m = re.match(r"^(?:open|launch)\s+\S+\s+and search for\s+(.+)$", c, re.I)
    if m:
        q = m.group(1).strip()
        if "youtube" in low:
            return "youtube_search", {"query": q}
        return "google_search", {"query": q}

    if "youtube" in low:
        m2 = re.search(r"search\s+youtube\s+for\s+(.+)", c, re.I)
        m3 = re.search(r"youtube\s+for\s+(.+)", c, re.I)
        m4 = re.search(r"search\s+for\s+(.+)", c, re.I)
        found = m2 or m3 or m4
        q = found.group(1).strip() if found else low
        q = re.sub(r"^(play|search)\s+", "", q, flags=re.I).strip()
        return "youtube_search", {"query": q}

    if "google" in low and "search" in low:
        m5 = re.search(r"search\s+google\s+for\s+(.+)", c, re.I)
        m4 = re.search(r"search\s+for\s+(.+)", c, re.I)
        found = m5 or m4
        q = found.group(1).strip() if found else c
        return "google_search", {"query": q}

    if re.search(r"\b(play|spotify|music)\b", low):
        q = re.sub(r"^(play|on spotify|spotify)\s+", "", c, flags=re.I).strip()
        q = re.sub(r"\bon spotify\s*$", "", q, flags=re.I).strip()
        return "play_music", {"query": q or c}

    if re.search(r"check (the )?server|server status|server health|cpu|how.*server", low):
        return "server_status", {}
    m = re.search(r"(?:restart|reboot the|status of)\s+(api|desk|bridge|muse|ollama|n8n)\b", low)
    if m:
        verb = "service_restart" if "restart" in low else "service_status"
        return verb, {"service": m.group(1).lower()}
    if "docker" in low:
        if "restart" in low:
            m2 = re.search(r"docker\s+restart\s+(\S+)", low)
            return "docker_restart", {"container": (m2.group(1) if m2 else "n8n")}
        return "docker_list", {}

    if re.search(r"\bwhats?app\b", low):
        m2 = re.search(r"(?:to\s+)?([\w .]+?)\s+(?:saying|that|message|text)\s+(.+)", c, re.I)
        to = m2.group(1).strip() if m2 else ""
        body = m2.group(2).strip() if m2 else c
        return "whatsapp_send", {"to": to, "text": body}
    if re.search(r"\b(mail|email|gmail)\b", low) and re.search(r"\b(send|compose|write|mail)\b", low):
        m2 = re.search(r"(?:to\s+)([\w.@ ]+?)(?:\s+(?:saying|that|subject|about)\s+(.+))?$", c, re.I)
        to = m2.group(1).strip() if m2 else ""
        body = m2.group(2).strip() if (m2 and m2.group(2)) else c
        tool = "mail_send" if re.search(r"\bsend\b", low) else "mail_compose"
        return tool, {"to": to, "subject": "", "text": body}
    if re.search(r"\b(sms|text (him|her|them|message))\b", low):
        return "sms_send", {"to": "", "text": c}
    if re.search(r"\b(instagram|insta|dm)\b", low):
        return "instagram_send", {"to": "", "text": c}
    if re.search(r"\b(calendar|invite|schedule|meeting)\b", low) and re.search(
        r"\b(create|invite|schedule|add|book)\b", low
    ):
        return "calendar_create", {"title": c}
    if re.match(r"^(call|dial)\b", low):
        who = re.sub(r"^(call|dial)\s+", "", c, flags=re.I).strip()
        return "dial", {"contact": who}
    if re.search(r"\b(swiggy|zomato|order food|food)\b", low):
        q = re.sub(r"^(search|order|find)\s+", "", c, flags=re.I).strip()
        return "open_food_search", {"query": q}

    if re.search(r"\b(take|photo|selfie|camera|picture)\b", low):
        return "camera_action", {"mode": "selfie" if "selfie" in low else "photo"}

    if re.search(r"what was i doing|who am i|what.*(ip|address)", low):
        return "mind_recall", {"query": c}
    m = re.match(r"^remember\s+(.+)", c, re.I)
    if m:
        return "mind_note", {"text": m.group(1).strip()}
    m = re.match(r"^forget\s+(.+)", c, re.I)
    if m:
        return "mind_note", {"text": "forget: " + m.group(1).strip()}

    m = re.match(r"^(open|launch|close)\s+(.+)$", c, re.I)
    if m:
        verb, label = m.group(1).lower(), m.group(2).strip()
        label = re.sub(r"\s+(app|application)\s*$", "", label, flags=re.I).strip()
        ms = re.search(r"^(.+?)\s+and search for\s+(.+)$", label, re.I)
        if ms:
            return "open_app", {"label": ms.group(1).strip()}
        tool = "open_app" if verb in ("open", "launch") else "close_app"
        return tool, {"label": label}

    m = re.match(r"^type\s+(.+)$", c, re.I)
    if m:
        body = m.group(1).strip()
        send = bool(re.search(r"\b(send it|and send|press enter|enter)\b", body, re.I))
        body = re.sub(r"\s*(and\s+)?(send it|press enter|hit enter)\s*$", "", body, flags=re.I).strip()
        return "type_into", {"text": body, "send": send}
    if low.startswith("search for ") or low.startswith("search "):
        q = re.sub(r"^search(\s+for)?\s+", "", c, flags=re.I).strip()
        return "google_search", {"query": q}
    if re.search(r"^https?://", c.strip()):
        return "open_url", {"url": c.strip()}

    return "type_into", {"text": c}


def _kind_for(clause, full_text, tool):
    low = (clause or "").lower()
    if any(h in low for h in _FOLLOWUP_HINTS):
        return "followup"
    for rx in _REPEAT_RES:
        if rx.search(full_text or "") or rx.search(clause or ""):
            return "repeat"
    if re.search(r"\biterate\b|\bkeep fixing\b|\buntil done\b", full_text or "", re.I):
        return "iterate"
    return "once"


def _local_plan(text, session_id, target):
    mode = get_mode()
    confirm_tools = get_confirm_tools()
    clauses = []
    for chunk in _split_clauses(text):
        clauses.extend(_expand_combined(chunk))
    if not clauses:
        return {"reply": "Say that again?", "session_id": session_id, "plan": []}

    plan = []
    prev_id = None
    for i, clause in enumerate(clauses):
        tool, args = _clause_to_tool(clause)
        device = _resolve_device(clause, target)
        kind = _kind_for(clause, text, tool)
        sid = "s%d" % (i + 1)
        after = [] if i == 0 else [prev_id]
        args = dict(args or {})
        confirm = tool in confirm_tools
        if mode == "sandbox" and (tool in confirm_tools or tool in SEND_TOOLS):
            args["draft"] = True
            confirm = True if tool in confirm_tools else confirm
            if tool in SEND_TOOLS and tool not in confirm_tools:
                # Still surfaced as a draft step even if env removed it.
                args["draft"] = True
        if kind == "repeat" and not any(k in args for k in ("count", "limit", "max_iters")):
            m = re.search(r"\b(\d+)\s*times\b", text, re.I)
            args["count"] = int(m.group(1)) if m else 3
        if kind == "iterate" and "max_iters" not in args:
            args["goal"] = text.strip()[:200]
            args["max_iters"] = 5
        plan.append(
            {
                "id": sid,
                "after": after,
                "kind": kind,
                "device": device,
                "tool": tool,
                "args": args,
                "confirm": bool(confirm),
            }
        )
        prev_id = sid

    reply = _short_reply(plan, text)
    return {"reply": reply, "session_id": session_id, "plan": plan}


def _short_reply(plan, text):
    if not plan:
        return "Got it."
    draft = any((s.get("args") or {}).get("draft") for s in plan)
    first = plan[0]
    tool = first.get("tool", "")
    args = first.get("args") or {}
    if tool == "open_app" and args.get("label"):
        base = "Opening %s." % args["label"]
    elif tool == "youtube_search":
        base = "Searching YouTube."
    elif tool == "google_search":
        base = "Searching Google."
    elif tool == "play_music":
        base = "Playing it."
    elif tool == "server_status":
        base = "Checking the server."
    elif tool == "type_into":
        base = "Typing that now."
    elif len(plan) == 1:
        base = "On it."
    else:
        base = "On it — %d steps queued." % len(plan)
    if draft:
        base += " Saved as draft — nothing sent."
    return base


def _call_spark(text, session_id, target, note, context):
    """Call Muse spark for leftover text. Returns contract dict or None.

    Never touches needle / laya / qwen ports even if installed.
    """
    api_key = (os.environ.get("MODEL_API_KEY") or "").strip()
    if not api_key or api_key == "LLM_...":
        return None
    url = (os.environ.get("MARC_SPARK_URL") or os.environ.get("MODEL_API_URL") or "").strip()
    if not url:
        return None
    lowered = url.lower()
    for bad in (":18096", ":8094", ":8091", ":11434"):
        if bad in lowered:
            return None  # needle / laya / qwen rollback ports — never call
    try:
        import json as _json
        import urllib.request as _req

        model = os.environ.get("MARC_SPARK_MODEL") or "muse-spark-1.3"
        payload = _json.dumps(
            {
                "model": model,
                "input": text,
                "session_id": session_id,
                "target": target,
                "note": note,
                "context": context,
                "mode": get_mode(),
            }
        ).encode("utf-8")
        req = _req.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
            method="POST",
        )
        with _req.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
        data = _json.loads(body) if body else {}
        if isinstance(data, dict) and isinstance(data.get("plan"), list):
            data.setdefault("reply", "On it.")
            data.setdefault("session_id", session_id)
            return data
        return None
    except Exception:
        return None


# ------------------------------------------------- voice_gate + driving ---

def _normalize_classify_result(res, raw):
    """Normalize voice_gate.classify output to (kind, remainder)."""
    kind = None
    remainder = ""
    try:
        if isinstance(res, (tuple, list)):
            if len(res) >= 1:
                kind = res[0]
            if len(res) >= 2:
                remainder = res[1]
        elif isinstance(res, dict):
            kind = (
                res.get("action")
                or res.get("kind")
                or res.get("intent")
                or res.get("type")
                or res.get("label")
                or res.get("command")
            )
            remainder = (
                res.get("remainder")
                or res.get("rest")
                or res.get("remainder_text")
                or res.get("text")
                or res.get("utterance")
                or res.get("query")
                or ""
            )
            if kind is None:
                for _k in (
                    "refuse", "sleep", "stop_marc", "stop", "confirm",
                    "cancel", "ignore", "wake", "utterance",
                ):
                    if res.get(_k):
                        kind = _k
                        break
        else:
            kind = res
            remainder = raw
    except Exception:
        return None
    if kind is None:
        return None
    try:
        kind_s = str(kind).strip().lower().replace("-", "_").replace(" ", "_")
    except Exception:
        return None
    if not isinstance(remainder, str):
        try:
            remainder = str(remainder) if remainder is not None else ""
        except Exception:
            remainder = ""
    return (kind_s, remainder)


def _fallback_classify(text):
    """Local voice-gate fallback when voice_gate module is absent."""
    raw = text or ""
    low = raw.strip().lower()
    stripped = low.strip(" ,.!?;:")
    # hard-refuse patterns double as voice refuse
    try:
        if raw and is_refused(raw):
            return ("refuse", "")
    except Exception:
        pass
    # exact wake words -> wake with empty remainder
    if stripped in (
        "hey marc", "hi marc", "hello marc", "ok marc", "okay marc",
        "hey muse", "hi muse", "hello muse", "marc", "muse",
        "wake", "wake up", "wake up marc", "hey marc wake",
    ):
        return ("wake", "")
    # wake prefix with remainder, e.g. "hey marc open youtube"
    _wake_prefixes = (
        "hey marc", "hi marc", "hello marc", "ok marc", "okay marc",
        "hey muse", "hi muse", "hello muse", "marc,", "marc",
        "muse,", "muse",
    )
    for pref in sorted(_wake_prefixes, key=len, reverse=True):
        if low.startswith(pref):
            rest = raw[len(pref):].strip()
            rest = rest.lstrip(" ,:;-").strip()
            if not rest:
                return ("wake", "")
            return ("wake", rest)
    # sleep / stop marc -> stopped
    if re.search(r"\bstop\s+marc\b", low) or re.search(r"\bstop\s+muse\b", low):
        return ("stop_marc", "")
    if re.search(r"\bsleep\b", low):
        return ("sleep", "")
    if stripped in ("stop", "stop it", "stop now", "stop marc", "stop muse"):
        return ("stop_marc", "")
    # ignore -> background / not for marc
    if re.search(r"\bignore\b", low):
        return ("ignore", "")
    # confirm (short yes-like utterances)
    if stripped in (
        "yes", "y", "yep", "yeah", "yup", "confirm", "confirmed",
        "send", "send it", "do it", "ok", "okay",
        "yes send", "yes send it", "confirm send", "ok send",
    ):
        return ("confirm", "")
    if re.match(r"^\s*(yes|yep|yeah|yup|confirm|confirmed)\b", low):
        return ("confirm", "")
    # cancel
    if re.search(r"\bcancel\b", low):
        return ("cancel", "")
    if stripped in ("no", "nope", "cancel", "never mind", "nevermind"):
        return ("cancel", "")
    if re.match(r"^\s*(no|nope|cancel)\b", low):
        return ("cancel", "")
    if re.search(r"\bdon'?t send\b", low) or re.search(r"\bnever ?mind\b", low):
        return ("cancel", "")
    return ("utterance", raw)


def _voice_classify(raw, context=None):
    """Classify via voice_gate.classify with local fallback."""
    try:
        import sys as _sys

        _vg = None
        try:
            import voice_gate as _vg_imported  # type: ignore
            _vg = _vg_imported
        except Exception:
            try:
                _vg = _sys.modules.get("voice_gate")
            except Exception:
                _vg = None
        if _vg is not None:
            fn = getattr(_vg, "classify", None)
            if callable(fn):
                res = None
                try:
                    res = fn(raw)
                except TypeError:
                    try:
                        res = fn(raw, context)
                    except TypeError:
                        try:
                            res = fn(text=raw)
                        except Exception:
                            res = None
                except Exception:
                    res = None
                if res is not None:
                    parsed = _normalize_classify_result(res, raw)
                    if parsed is not None:
                        return parsed
    except Exception:
        pass
    return _fallback_classify(raw or "")


def _resolve_driving(raw_context):
    """Return True when driving context is active.

    Accepts context as None (reads MARC_CONTEXT/CONTEXT), str, dict, or
    an object exposing .context / .shorten / .profile / .is_driving.
    """
    ctx = raw_context
    if isinstance(ctx, str):
        v = ctx.strip().lower()
        if v == "driving":
            return True
        if v in ("desk", ""):
            return False
        # unknown string -> fall through to env
    elif isinstance(ctx, dict):
        for _k in ("context", "MARC_CONTEXT", "CONTEXT"):
            try:
                _v = ctx.get(_k)
            except Exception:
                _v = None
            if isinstance(_v, str):
                _vv = _v.strip().lower()
                if _vv == "driving":
                    return True
                if _vv == "desk":
                    return False
        try:
            if ctx.get("driving") is True or ctx.get("is_driving") is True:
                return True
            if ctx.get("driving") is False or ctx.get("is_driving") is False:
                return False
        except Exception:
            pass
        try:
            if callable(ctx.get("shorten")):
                return True
        except Exception:
            pass
        try:
            if ctx.get("profile") is not None:
                return True
        except Exception:
            pass
        # inconclusive dict -> fall through to env
    elif ctx is not None:
        try:
            _cval = getattr(ctx, "context", None)
            if isinstance(_cval, str):
                if _cval.strip().lower() == "driving":
                    return True
                if _cval.strip().lower() == "desk":
                    return False
        except Exception:
            pass
        try:
            _iv = getattr(ctx, "is_driving", None)
            if callable(_iv):
                try:
                    if bool(_iv()):
                        return True
                except Exception:
                    pass
            elif isinstance(_iv, bool):
                return bool(_iv)
        except Exception:
            pass
        try:
            if callable(getattr(ctx, "shorten", None)):
                return True
        except Exception:
            pass
        try:
            if getattr(ctx, "profile", None) is not None:
                return True
        except Exception:
            pass
        try:
            if getattr(ctx, "driving", None) is True:
                return True
            if getattr(ctx, "driving", None) is False:
                return False
        except Exception:
            pass
        # inconclusive object -> fall through to env
    # env fallback: MARC_CONTEXT takes precedence over CONTEXT (config parity).
    try:
        _marc = (os.environ.get("MARC_CONTEXT") or "").strip().lower()
        if _marc in ("driving", "desk"):
            return _marc == "driving"
        _alias = (os.environ.get("CONTEXT") or "").strip().lower()
        if _alias in ("driving", "desk"):
            return _alias == "driving"
    except Exception:
        pass
    return False


def _drive_shorten_fallback(s):
    """Shorten a reply for driving: keep short replies exact, trim long ones."""
    if not s:
        return s
    t = str(s)
    # Preserve short voice-gate replies exactly (Sending., Stopping., etc.).
    if len(t) <= 80 and t.count(".") <= 1 and t.count("!") <= 1 and t.count("?") <= 1:
        return t
    parts = re.split(r"(?<=[.!?])\s+", t.strip())
    first = parts[0].strip() if parts and parts[0].strip() else t.strip()
    if len(first) > 80:
        first = first[:77].rstrip() + "..."
    return first or t


def _apply_driving_shorten(reply, raw_context):
    """Shorten every driving reply via context.shorten when available."""
    if not reply:
        return reply
    try:
        if isinstance(raw_context, dict):
            try:
                _fn = raw_context.get("shorten")
                if callable(_fn):
                    _out = _fn(reply)
                    if isinstance(_out, str) and _out:
                        return _out
            except Exception:
                pass
            try:
                _prof = raw_context.get("profile")
                if isinstance(_prof, dict):
                    _fn2 = _prof.get("shorten")
                    if callable(_fn2):
                        _out = _fn2(reply)
                        if isinstance(_out, str) and _out:
                            return _out
                elif _prof is not None:
                    _fn2 = getattr(_prof, "shorten", None)
                    if callable(_fn2):
                        _out = _fn2(reply)
                        if isinstance(_out, str) and _out:
                            return _out
            except Exception:
                pass
        elif raw_context is not None and not isinstance(raw_context, str):
            try:
                _fn = getattr(raw_context, "shorten", None)
                if callable(_fn):
                    _out = _fn(reply)
                    if isinstance(_out, str) and _out:
                        return _out
            except Exception:
                pass
            try:
                _prof = getattr(raw_context, "profile", None)
                if _prof is not None:
                    if isinstance(_prof, dict):
                        _fn2 = _prof.get("shorten")
                    else:
                        _fn2 = getattr(_prof, "shorten", None)
                    if callable(_fn2):
                        _out = _fn2(reply)
                        if isinstance(_out, str) and _out:
                            return _out
            except Exception:
                pass
    except Exception:
        pass
    return _drive_shorten_fallback(reply)


def _driving_cap(raw_context):
    """Hop cap for driving via context.profile hop_cap (default 6)."""
    _default = 6
    try:
        if isinstance(raw_context, dict):
            try:
                _prof = raw_context.get("profile")
                if isinstance(_prof, dict) and "hop_cap" in _prof:
                    return max(0, int(_prof["hop_cap"]))
                if _prof is not None and not isinstance(_prof, dict):
                    _hc = getattr(_prof, "hop_cap", None)
                    if callable(_hc):
                        _hc = _hc()
                    if _hc is not None:
                        return max(0, int(_hc))
            except Exception:
                pass
            try:
                if "hop_cap" in raw_context:
                    return max(0, int(raw_context["hop_cap"]))
            except Exception:
                pass
        elif raw_context is not None and not isinstance(raw_context, str):
            try:
                _prof = getattr(raw_context, "profile", None)
                if _prof is not None:
                    if isinstance(_prof, dict):
                        if "hop_cap" in _prof:
                            return max(0, int(_prof["hop_cap"]))
                    else:
                        _hc = getattr(_prof, "hop_cap", None)
                        if callable(_hc):
                            _hc = _hc()
                        if _hc is not None:
                            return max(0, int(_hc))
            except Exception:
                pass
            try:
                _hc = getattr(raw_context, "hop_cap", None)
                if _hc is not None:
                    if callable(_hc):
                        _hc = _hc()
                    return max(0, int(_hc))
            except Exception:
                pass
    except Exception:
        pass
    return _default


def plan(text="", session_id="phone", target="auto", note="", context=None, pending_confirm=False, **kwargs):
    sid = (session_id or "phone").strip() or "phone"
    # pending_confirm may arrive via kwargs aliases.
    if not pending_confirm:
        for _k in ("pending_confirm", "pending", "awaiting_confirm", "confirm_pending"):
            try:
                if kwargs.get(_k):
                    pending_confirm = bool(kwargs.get(_k))
                    break
            except Exception:
                continue
    raw_context = context
    if raw_context is None:
        for _k in ("context", "marc_context", "MARC_CONTEXT"):
            try:
                if kwargs.get(_k) is not None:
                    raw_context = kwargs.get(_k)
                    break
            except Exception:
                continue
    # pending_confirm may also hide inside a dict context.
    if not pending_confirm and isinstance(raw_context, dict):
        try:
            if raw_context.get("pending_confirm"):
                pending_confirm = True
        except Exception:
            pass
    is_drive = _resolve_driving(raw_context)

    def _maybe_shorten(reply):
        if is_drive:
            try:
                return _apply_driving_shorten(reply, raw_context)
            except Exception:
                return reply
        return reply

    raw_input = text or note or ""
    raw_input = raw_input.strip() if isinstance(raw_input, str) else str(raw_input).strip()

    # Voice-gate classify at the start.
    if raw_input:
        kind, remainder = _voice_classify(raw_input, raw_context)
    else:
        kind, remainder = ("utterance", raw_input)
    k = (kind or "").strip().lower().replace("-", "_").replace(" ", "_")

    if k == "refuse":
        return {"reply": "I can't do that.", "session_id": sid, "plan": []}
    if k in ("sleep", "stop", "stop_marc", "stop_muse", "sleep_marc", "go_to_sleep"):
        try:
            set_stopped()
        except Exception:
            pass
        return {"reply": _maybe_shorten("Stopping."), "session_id": sid, "plan": []}
    if k in ("confirm", "confirmed", "yes", "approve", "accept"):
        if pending_confirm:
            return {
                "reply": _maybe_shorten("Sending."),
                "session_id": sid,
                "plan": [],
                "confirmed": True,
            }
    if k in ("cancel", "cancelled", "canceled", "no", "deny", "reject"):
        if pending_confirm:
            return {
                "reply": _maybe_shorten("Cancelled. Nothing sent."),
                "session_id": sid,
                "plan": [],
                "confirmed": False,
                "cancelled": True,
            }
    if k in ("ignore", "ignored"):
        return {"reply": "", "session_id": sid, "plan": [], "ignored": True}
    if k in ("wake", "wake_up", "hey_marc", "hi_marc", "hello"):
        rem = (remainder or "").strip() if isinstance(remainder, str) else ""
        if not rem:
            return {
                "reply": _maybe_shorten("I'm listening."),
                "session_id": sid,
                "plan": [],
                "listening": True,
            }
        raw_input = rem

    if is_stopped():
        return {"reply": _maybe_shorten("Muse isn't running."), "session_id": sid, "plan": []}
    if is_paused():
        return {"reply": _maybe_shorten("Muse budget paused."), "session_id": sid, "plan": []}

    raw = raw_input.strip() if isinstance(raw_input, str) else str(raw_input).strip()
    if not raw:
        return {"reply": _maybe_shorten("Say that again?"), "session_id": sid, "plan": []}
    if is_refused(raw):
        return {"reply": "I can't do that.", "session_id": sid, "plan": []}

    local = _local_plan(raw, sid, target)
    if local.get("plan"):
        if is_drive:
            try:
                cap = _driving_cap(raw_context)
            except Exception:
                cap = 6
            try:
                pl = local.get("plan") or []
                if isinstance(pl, list) and len(pl) > cap:
                    pl = pl[:cap]
                    local["plan"] = pl
                    try:
                        local["reply"] = _short_reply(pl, raw)
                    except Exception:
                        pass
                local["reply"] = _apply_driving_shorten(local.get("reply") or "", raw_context)
            except Exception:
                pass
        return local

    # Serializable context for spark (never pass live objects with methods).
    spark_ctx = raw_context
    if spark_ctx is not None and not isinstance(spark_ctx, (dict, str, list, int, float, bool)):
        try:
            _cval = getattr(spark_ctx, "context", None)
            if isinstance(_cval, str):
                spark_ctx = _cval
            else:
                spark_ctx = str(spark_ctx)
        except Exception:
            spark_ctx = None
    spark = _call_spark(raw, sid, target, note, spark_ctx)
    if spark is not None:
        if is_drive:
            try:
                cap = _driving_cap(raw_context)
            except Exception:
                cap = 6
            try:
                pl = spark.get("plan") or []
                if isinstance(pl, list) and len(pl) > cap:
                    spark["plan"] = pl[:cap]
            except Exception:
                pass
            try:
                spark["reply"] = _apply_driving_shorten(spark.get("reply") or "On it.", raw_context)
            except Exception:
                pass
        spark.setdefault("reply", "On it.")
        spark.setdefault("session_id", sid)
        return spark
    # Sandbox boot without a key: valid contract, no crash.
    return {"reply": _maybe_shorten("Got it — nothing to do yet."), "session_id": sid, "plan": []}
