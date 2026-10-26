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


def plan(text="", session_id="phone", target="auto", note="", context=None):
    sid = (session_id or "phone").strip() or "phone"
    if is_stopped():
        return {"reply": "Muse isn't running.", "session_id": sid, "plan": []}
    if is_paused():
        return {"reply": "Muse budget paused.", "session_id": sid, "plan": []}

    raw = text or note or ""
    raw = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if not raw:
        return {"reply": "Say that again?", "session_id": sid, "plan": []}
    if is_refused(raw):
        return {"reply": "I can't do that.", "session_id": sid, "plan": []}

    local = _local_plan(raw, sid, target)
    if local.get("plan"):
        return local

    spark = _call_spark(raw, sid, target, note, context)
    if spark is not None:
        return spark
    # Sandbox boot without a key: valid contract, no crash.
    return {"reply": "Got it — nothing to do yet.", "session_id": sid, "plan": []}
