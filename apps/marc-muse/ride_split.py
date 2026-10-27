"""ride_split — compound parser for Marc Ride demo (stdlib re only)."""
import re

_KEYWORDS = r"(?:text|whatsapp|play|email|mail|call|dial|open)"

_HARD_RE = re.compile(
    r"\s*;\s*|\s*\bafter that\b\s*|\s*\band then\b\s*|\s*\bthen\b\s*",
    re.I,
)

_COND_RE = re.compile(
    r",\s*(?:and\s+)?(?=" + _KEYWORDS + r"\b)|\s+and\s+(?=" + _KEYWORDS + r"\b)",
    re.I,
)


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
        # conditional splits within each hard chunk
        subs = _COND_RE.split(part)
        for sub in subs:
            if sub is None:
                continue
            c = sub.strip()
            c = c.strip(" ,;.")
            c = c.strip()
            if not c:
                continue
            # drop a stray leading 'and ' left over from splitting
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


def clause_to_tool(clause, target="auto"):
    """Map one clause -> (tool, args, device)."""
    c = (clause or "").strip()
    device = _resolve_device(c, target)
    core = _strip_device_phrase(c)
    core = core.strip()
    low_core = core.lower()

    # text NAME rest -> whatsapp_send
    m = re.match(r"^\s*text\s+(\S+)\s*(.*)\s*$", core, re.I)
    if m:
        to = (m.group(1) or "").strip().strip(" ,;.:")
        rest = (m.group(2) or "").strip().strip(" ,;.")
        return ("whatsapp_send", {"to": to, "text": rest}, device)

    # whatsapp ... -> whatsapp_send
    m = re.match(r"^\s*whats?app\s+(.*)$", core, re.I)
    if m:
        remainder = (m.group(1) or "").strip().strip(" ,;.")
        to = ""
        body = remainder
        m2 = re.match(r"^(?:to\s+)?(\S+)\s+(.*)$", remainder, re.I)
        if m2:
            to = (m2.group(1) or "").strip().strip(" ,;.:")
            body = (m2.group(2) or "").strip()
            # 'saying/that/message/text' joiners: keep body as-is
        elif remainder:
            # single token -> treat as contact with empty text
            if re.match(r"^\S+$", remainder):
                to = remainder.strip(" ,;.:")
                body = ""
        return ("whatsapp_send", {"to": to, "text": body}, device)

    # play ... -> play_music
    if re.match(r"^\s*play\b", core, re.I):
        q = re.sub(r"^\s*play\s+", "", core, flags=re.I).strip()
        q = q.strip(" ,;.")
        if not q:
            q = core.strip(" ,;.")
        return ("play_music", {"query": q}, device)

    # email/mail ... myself -> mail_compose
    m = re.match(r"^\s*(email|mail)\b\s*(.*)$", core, re.I)
    if m:
        body = (m.group(2) or "").strip()
        body = re.sub(r"\s+to\s+myself\s*$", "", body, flags=re.I).strip()
        body = re.sub(r"\s+myself\s*$", "", body, flags=re.I).strip()
        body = body.strip(" ,;.")
        return ("mail_compose", {"to": "me", "text": body}, device)
    if re.search(r"\b(email|mail)\b", core, re.I) and re.search(
        r"\bmyself\b", core, re.I
    ):
        body = re.sub(r"^.*?\b(email|mail)\b\s*", "", core, flags=re.I).strip()
        body = re.sub(r"\s+to\s+myself\s*$", "", body, flags=re.I).strip()
        body = re.sub(r"\s+myself\s*$", "", body, flags=re.I).strip()
        body = body.strip(" ,;.")
        return ("mail_compose", {"to": "me", "text": body}, device)

    # call/dial NAME -> dial
    m = re.match(r"^\s*(call|dial)\s+(.+)$", core, re.I)
    if m:
        contact = (m.group(2) or "").strip().strip(" ,;.")
        return ("dial", {"contact": contact}, device)

    # open LABEL -> open_app
    m = re.match(r"^\s*open\s+(.+)$", core, re.I)
    if m:
        label = (m.group(1) or "").strip().strip(" ,;.")
        return ("open_app", {"label": label}, device)

    # fallback
    _ = low_core
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
    if t in ("mail_compose", "mail_send", "mail", "email"):
        return "mail"
    if t in ("dial", "call"):
        return "dial"
    if t in ("open_app", "open", "laptop"):
        return "laptop"
    return "phone"


def local_plan(text, session_id="phone", target="auto", mode="sandbox", confirm_tools=None):
    """Build independent-step plan from compound text."""
    sid = session_id or "phone"
    try:
        sid = str(sid)
    except Exception:
        sid = "phone"
    if confirm_tools is None:
        ct = {"mail_compose", "whatsapp_send", "dial"}
    else:
        try:
            ct = set(confirm_tools)
        except Exception:
            ct = {"mail_compose", "whatsapp_send", "dial"}
    try:
        mode_norm = str(mode or "sandbox").strip().lower() or "sandbox"
    except Exception:
        mode_norm = "sandbox"

    clauses = split_clauses(text)
    if not clauses:
        return {"reply": "Say that again?", "session_id": sid, "plan": []}

    plan = []
    for i, cl in enumerate(clauses):
        tool, args, device = clause_to_tool(cl, target=target)
        args = dict(args or {})
        if tool == "play_music":
            confirm = False
        else:
            confirm = tool in ct
        if mode_norm == "sandbox" and tool in ct:
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

    if len(plan) == 1:
        base = "On it."
    else:
        base = "On it \u2014 %d steps queued." % len(plan)
    try:
        if any((s.get("args") or {}).get("draft") for s in plan):
            base += " Saved as draft \u2014 nothing sent."
    except Exception:
        pass
    return {"reply": base, "session_id": sid, "plan": plan}
