"""ride_split — compound parser for Marc Ride demo (stdlib re only)."""
import re

_KEYWORDS = r"(?:text|whatsapp|play|email|mail|call|dial|open|auto\s*scroll|scroll|swipe|tap|click|type|search)"

_HARD_RE = re.compile(
    r"\s*;\s*|\s*\bafter that\b\s*|\s*\band then\b\s*|\s*\bthen\b\s*",
    re.I,
)

_COND_RE = re.compile(
    r",\s*(?:and\s+)?(?=" + _KEYWORDS + r"\b)|\s+and\s+(?=" + _KEYWORDS + r"\b)",
    re.I,
)

# Confirm only leftover gated tools. WA / mail / call / play / reels go now.
_NO_CONFIRM = {
    "whatsapp_send",
    "dial",
    "mail_compose",
    "mail_send",
    "play_music",
    "auto_scroll",
    "open_app",
    "youtube_play",
    "youtube_search",
    "notifications_list",
    "suggest_reply",
    "chat_touch",
}


def _wa_package(text):
    low = (text or "").lower()
    if "personal whatsapp" in low or "my whatsapp" in low:
        return "com.whatsapp"
    return "com.whatsapp.w4b"


def split_clauses(text):
    """Split compound utterance into clauses.

    Splits on ';' / 'after that' / 'and then' / 'then' unconditionally,
    and on commas and ' and ' when the next token is
    text|whatsapp|play|email|mail|call|dial|open.
    """
    if not text or not str(text).strip():
        return []
    s = str(text).strip()
    hard_parts = _HARD_RE.split(s)
    out = []
    for part in hard_parts:
        if part is None:
            continue
        subs = _COND_RE.split(part)
        for sub in subs:
            if sub is None:
                continue
            c = sub.strip()
            c = c.strip(" ,;.")
            c = c.strip()
            if not c:
                continue
            m = re.match(r"^and\s+(.+)$", c, re.I)
            if m and re.match(r"^" + _KEYWORDS + r"\b", m.group(1).strip(), re.I):
                c = m.group(1).strip()
                c = c.strip(" ,;.")
                if not c:
                    continue
            if c:
                out.append(c)
    return out


def _resolve_device(clause, target):
    low = (clause or "").lower()
    if re.search(r"\bon\s+(my|the)\s+laptop\b", low):
        return "laptop"
    if re.search(r"\bon\s+(my|the)\s+phone\b", low):
        return "phone"
    if re.search(r"\bon\s+(my|the)\s+server\b", low):
        return "server"
    t = (target or "auto")
    try:
        t = str(t).strip().lower()
    except Exception:
        t = "auto"
    if t in ("phone", "laptop", "server"):
        return t
    return "phone"


def _strip_device_phrase(clause):
    return re.sub(
        r"\bon\s+(my|the)\s+(phone|laptop|server)\b",
        "",
        clause or "",
        flags=re.I,
    ).strip().strip(" ,;.")


def _clean_name(raw):
    s = (raw or "").strip().strip(" ,;.:")
    s = re.sub(r"'s$", "", s, flags=re.I).strip()
    return s


def collapse_whole(text, target="auto"):
    """Map a full utterance to one tool when it is a known compound recipe."""
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    device = _resolve_device(raw, target)
    low = raw.lower()

    if re.search(r"\bwhats?app\b", low) and re.search(r"\bsearch\b", low):
        m = re.search(
            r"search\s+([A-Za-z0-9+. \-]+?)(?:'s)?(?:\s+chat)?[\s,]+"
            r"(?:open\s+(?:[A-Za-z0-9+. \-]+?'s\s+)?chat\s+(?:and\s+)?)?"
            r"(?:and\s+)?(?:text|message)(?:\s+him|\s+her|\s+them)?\s+(.+)$",
            raw,
            re.I,
        )
        if m:
            to = _clean_name(m.group(1))
            body = (m.group(2) or "").strip().strip(" ,;.")
            if to:
                return (
                    "whatsapp_send",
                    {"to": to, "text": body, "package": _wa_package(raw)},
                    device,
                )

    # instagram/insta + scroll => auto_scroll even WITHOUT the word reel.
    if re.search(r"\b(instagram|insta)\b", low) and re.search(
        r"\b(scroll|auto\s*scroll)\b", low
    ):
        return ("auto_scroll", {"direction": "up"}, device)

    yt = _youtube_recipe(raw, device)
    if yt is not None:
        return yt

    # open spotify play QUERY (optional 'and') => play_music.
    m = re.search(r"\bopen\s+spotify\s+(?:and\s+)?play\s+(.+)$", raw, re.I)
    if m:
        q = (m.group(1) or "").strip().strip(" ,;.")
        if q:
            return ("play_music", {"query": q}, device)
    # play QUERY on spotify => play_music.
    m = re.search(r"\bplay\s+(.+?)\s+on\s+spotify\b", raw, re.I)
    if m:
        q = (m.group(1) or "").strip().strip(" ,;.")
        if q:
            return ("play_music", {"query": q}, device)
    # Plain "play QUERY" collapses only when the whole utterance is one
    # clause, so multi-step text like "play X and text Y" still splits.
    try:
        _single = split_clauses(raw)
    except Exception:
        _single = [raw]
    if isinstance(_single, list) and len(_single) == 1:
        m = re.match(r"^\s*play\s+(.+)$", raw, re.I)
        if m:
            q = (m.group(1) or "").strip()
            q = re.sub(r"\bon\s+spotify\s*$", "", q, flags=re.I).strip()
            q = q.strip(" ,;.")
            if q:
                return ("play_music", {"query": q}, device)

    return None


def _youtube_recipe(raw, device):
    low = (raw or "").lower()
    if "youtube" not in low and "youtu" not in low:
        return None
    if re.search(r"\bfirst\b", low) and re.search(r"\b(play|video)\b", low):
        return ("youtube_play", {"mode": "first"}, device)
    m = re.search(r"\bsearch\s+(?:for\s+)?(.+)$", raw, re.I)
    if m:
        q = (m.group(1) or "").strip().strip(" ,;.")
        q = re.sub(r"\bon\s+(youtube|youtu\.?be)\s*$", "", q, flags=re.I).strip()
        q = q.strip(" ,;.")
        if q:
            return ("youtube_play", {"mode": "search", "query": q}, device)
    m = re.search(r"\bplay\s+(.+)$", raw, re.I)
    if m:
        q = (m.group(1) or "").strip().strip(" ,;.")
        q = re.sub(r"\bon\s+(youtube|youtu\.?be)\s*$", "", q, flags=re.I).strip()
        q = q.strip(" ,;.")
        if q and "first" in q.lower():
            return ("youtube_play", {"mode": "first"}, device)
        if q:
            return ("youtube_play", {"mode": "search", "query": q}, device)
    return None


def clause_to_tool(clause, target="auto"):
    """Map one clause -> (tool, args, device)."""
    c = (clause or "").strip()
    device = _resolve_device(c, target)
    core = _strip_device_phrase(c)
    core = core.strip()
    low_core = core.lower()

    collapsed = collapse_whole(core, target)
    if collapsed is not None:
        return collapsed

    m = re.match(r"^\s*(?:use|switch(?:\s+to)?)\s+project\s+(\S+)\s*$", core, re.I)
    if m:
        return ("project_use", {"slug": m.group(1).strip()}, device)
    if re.match(r"^\s*list\s+projects\s*$", core, re.I):
        return ("project_list", {}, device)
    m = re.match(r"^\s*(?:run\s+project|code this)\s*(.*)$", core, re.I)
    if m:
        return ("project_run", {"goal": (m.group(1) or core).strip()}, device)
    if re.match(r"^\s*stop\s+project\s*$", core, re.I):
        return ("project_stop", {}, device)

    m = re.match(
        r"^\s*(?:touch|tell|ping|message)\s+(.+?)\s+(?:about|re|regarding)\s+(.+)$",
        core,
        re.I,
    )
    if m:
        return (
            "chat_touch",
            {
                "to": (m.group(1) or "").strip(),
                "topic": (m.group(2) or "").strip(),
                "channel": "whatsapp",
                "package": _wa_package(core),
            },
            device,
        )
    if re.search(r"\b(?:new\s+)?notifications?\b", low_core) or "what are the new notification" in low_core:
        return ("notifications_list", {}, device)
    m = re.match(
        r"^\s*(?:what\s+should\s+i\s+reply\s+(?:to\s+)?|suggest\s+(?:a\s+)?reply\s+(?:to\s+)?|reply\s+to\s+)(.+)$",
        core,
        re.I,
    )
    if m:
        return ("suggest_reply", {"to": (m.group(1) or "").strip()}, device)
    if "what should i reply" in low_core or "suggest reply" in low_core:
        who = ""
        m2 = re.search(r"(?:reply\s+to|to)\s+(.+)$", core, re.I)
        if m2:
            who = (m2.group(1) or "").strip()
        return ("suggest_reply", {"to": who}, device)

    m = re.match(r"^\s*text\s+(.+?)\s+(marc\s+test)\s*$", core, re.I)
    if m:
        to = (m.group(1) or "").strip().strip(" ,;.:")
        rest = (m.group(2) or "").strip()
        return ("whatsapp_send", {"to": to, "text": rest, "package": _wa_package(core)}, device)
    m = re.match(r"^\s*text\s+(\S+)\s*(.*)\s*$", core, re.I)
    if m:
        to = (m.group(1) or "").strip().strip(" ,;.:")
        rest = (m.group(2) or "").strip().strip(" ,;.")
        return ("whatsapp_send", {"to": to, "text": rest, "package": _wa_package(core)}, device)

    m = re.match(r"^\s*whats?app\s+(.*)$", core, re.I)
    if m:
        remainder = (m.group(1) or "").strip().strip(" ,;.")
        to = ""
        body = remainder
        m2 = re.match(r"^(?:to\s+)?(\S+)\s+(.*)$", remainder, re.I)
        if m2:
            to = (m2.group(1) or "").strip().strip(" ,;.:")
            body = (m2.group(2) or "").strip()
        elif remainder:
            if re.match(r"^\S+$", remainder):
                to = remainder.strip(" ,;.:")
                body = ""
        return ("whatsapp_send", {"to": to, "text": body, "package": _wa_package(core)}, device)

    if re.match(r"^\s*play\b", core, re.I):
        yt = _youtube_recipe(core, device)
        if yt is not None:
            return yt
        q = re.sub(r"^\s*play\s+", "", core, flags=re.I).strip()
        q = re.sub(r"\bon spotify\s*$", "", q, flags=re.I).strip()
        q = q.strip(" ,;.")
        if not q:
            q = core.strip(" ,;.")
        return ("play_music", {"query": q}, device)

    m = re.match(r"^\s*(email|mail)\b\s*(.*)$", core, re.I)
    if m:
        body = (m.group(2) or "").strip()
        to = "me" if re.search(r"\bmyself\b", core, re.I) else ""
        mto = re.search(r"\bto\s+(\S+)", body, re.I)
        if mto and not to:
            to = mto.group(1).strip(" ,;.")
        body = re.sub(r"\s+to\s+myself\s*$", "", body, flags=re.I).strip()
        body = re.sub(r"\s+myself\s*$", "", body, flags=re.I).strip()
        body = re.sub(r"^to\s+\S+\s*", "", body, flags=re.I).strip()
        body = body.strip(" ,;.")
        if not to:
            to = "me" if re.search(r"\bmyself\b", low_core) else body.split(" ")[0] if body else ""
        return ("mail_send", {"to": to or "me", "text": body}, device)
    if re.search(r"\b(email|mail)\b", core, re.I) and re.search(r"\bmyself\b", core, re.I):
        body = re.sub(r"^.*?\b(email|mail)\b\s*", "", core, flags=re.I).strip()
        body = re.sub(r"\s+to\s+myself\s*$", "", body, flags=re.I).strip()
        body = re.sub(r"\s+myself\s*$", "", body, flags=re.I).strip()
        body = body.strip(" ,;.")
        return ("mail_send", {"to": "me", "text": body}, device)

    m = re.match(r"^\s*(call|dial)\s+(.+)$", core, re.I)
    if m:
        contact = (m.group(2) or "").strip().strip(" ,;.")
        return ("dial", {"to": contact, "contact": contact}, device)

    m = re.match(r"^\s*open\s+(.+)$", core, re.I)
    if m:
        label = (m.group(1) or "").strip().strip(" ,;.")
        play = re.match(r"^spotify\s+(?:and\s+)?play\s+(.+)$", label, re.I)
        if play:
            return ("play_music", {"query": play.group(1).strip()}, device)
        # 'open Spotify play X' must not be open_app: detect play in label.
        if re.search(r"\bspotify\b", label, re.I) and re.search(r"\bplay\b", label, re.I):
            mp = re.search(r"play\s+(.+)$", label, re.I)
            if mp:
                q = (mp.group(1) or "").strip().strip(" ,;.")
                if q:
                    return ("play_music", {"query": q}, device)
            return ("play_music", {"query": label.strip()}, device)
        # open instagram ... scroll (no reels needed) => auto_scroll.
        if re.search(r"\b(instagram|insta)\b", label, re.I) and re.search(
            r"\b(scroll|auto\s*scroll)\b", label, re.I
        ):
            return ("auto_scroll", {"direction": "up"}, device)
        yt = _youtube_recipe("open " + label, device)
        if yt is not None:
            return yt
        return ("open_app", {"app": label, "label": label}, device)

    m = re.match(r"^\s*(?:auto\s*scroll|scroll|swipe)\b(.*)$", core, re.I)
    if m:
        rest = (m.group(1) or "").lower()
        if "reel" in rest or "auto" in low_core:
            return ("auto_scroll", {"direction": "up"}, device)
        direction = "up"
        if "down" in rest:
            direction = "down"
        elif "left" in rest:
            direction = "left"
        elif "right" in rest:
            direction = "right"
        return ("swipe", {"direction": direction}, device)

    m = re.match(r"^\s*(?:tap|click)\b\s*(.*)$", core, re.I)
    if m:
        return ("click_text", {"text": (m.group(1) or "").strip()}, device)

    if re.search(r"\b(auto\s*scroll|reels)\b", low_core):
        return ("auto_scroll", {"direction": "up"}, device)
    if re.search(r"\b(scroll|swipe)\b", low_core):
        return ("swipe", {"direction": "up"}, device)
    return ("type_into", {"text": c.strip()}, device)


def family(tool):
    """Map tool name -> family bucket."""
    try:
        t = str(tool or "").strip().lower()
    except Exception:
        t = ""
    if t in ("whatsapp_send", "whatsapp"):
        return "whatsapp"
    if t in ("play_music", "music", "spotify"):
        return "music"
    if t in ("youtube_play", "youtube_search"):
        return "phone"
    if t in ("mail_compose", "mail_send", "mail", "email"):
        return "mail"
    if t in ("dial", "call"):
        return "dial"
    if t in ("open_app", "open", "laptop"):
        return "laptop"
    if t in ("project_list", "project_use", "project_run", "project_stop"):
        return "office"
    return "phone"


def _short_reply(plan):
    if not plan:
        return "Say that again?"
    first = plan[0]
    tool = first.get("tool", "")
    args = first.get("args") or {}
    if tool == "whatsapp_send":
        return "Texting %s." % (args.get("to") or "them")
    if tool == "dial":
        return "Calling %s." % (args.get("to") or args.get("contact") or "them")
    if tool in ("mail_send", "mail_compose"):
        return "Emailing %s." % (args.get("to") or "them")
    if tool == "play_music":
        q = args.get("query") or "it"
        return "Playing %s." % q
    if tool == "auto_scroll":
        return "Scrolling Reels."
    if tool in ("youtube_play", "youtube_search"):
        return "Opening YouTube."
    if tool == "open_app":
        return "Opening %s." % (args.get("app") or args.get("label") or "it")
    if len(plan) == 1:
        return "On it."
    return "On it \u2014 %d steps queued." % len(plan)


def local_plan(text, session_id="phone", target="auto", mode="sandbox", confirm_tools=None):
    """Build independent-step plan from compound text."""
    sid = session_id or "phone"
    try:
        sid = str(sid)
    except Exception:
        sid = "phone"
    if confirm_tools is None:
        ct = {"instagram_send", "sms_send", "calendar_create", "open_food_search"}
    else:
        try:
            ct = set(confirm_tools)
        except Exception:
            ct = {"instagram_send", "sms_send", "calendar_create", "open_food_search"}
    try:
        mode_norm = str(mode or "sandbox").strip().lower() or "sandbox"
    except Exception:
        mode_norm = "sandbox"

    collapsed = collapse_whole(text, target=target)
    if collapsed is not None:
        tool, args, device = collapsed
        args = dict(args or {})
        confirm = tool in ct and tool not in _NO_CONFIRM
        plan = [
            {
                "id": "s1",
                "after": [],
                "kind": "once",
                "device": device,
                "tool": tool,
                "args": args,
                "confirm": bool(confirm),
            }
        ]
        return {"reply": _short_reply(plan), "session_id": sid, "plan": plan}

    clauses = split_clauses(text)
    if not clauses:
        return {"reply": "Say that again?", "session_id": sid, "plan": []}

    plan = []
    for i, cl in enumerate(clauses):
        tool, args, device = clause_to_tool(cl, target=target)
        args = dict(args or {})
        if "contact" in args and "to" not in args:
            args["to"] = args.get("contact")
        if "to" in args and "contact" not in args and tool == "dial":
            args["contact"] = args.get("to")
        confirm = (tool in ct) and (tool not in _NO_CONFIRM)
        if mode_norm == "sandbox" and confirm:
            args["draft"] = True
        plan.append(
            {
                "id": "s%d" % (i + 1),
                "after": [],
                "kind": "once",
                "device": device,
                "tool": tool,
                "args": args,
                "confirm": bool(confirm),
            }
        )

    return {"reply": _short_reply(plan), "session_id": sid, "plan": plan}
