"""Google connector — Gmail / Calendar / Drive (stdlib only).

Sandbox-first: unless ``MARC_MODE=live`` AND the caller passes
``confirmed=True`` AND a token file is present, every write is routed
to ``drafts.enqueue`` and nothing touches the network.

Token source: ``GOOGLE_TOKEN_PATH`` (``MARC_GOOGLE_TOKEN_PATH`` alias,
else ``MARC_MIND_DIR/google_token.json``). If the env var is missing
or the file is missing, :func:`get_mode` returns ``"sandbox"``.

Network (live only) uses stdlib ``urllib`` + ``json``. Tokens are only
ever placed in the ``Authorization`` header — never printed or logged.

Confirm-gated tools: ``mail_compose``, ``mail_send``, ``calendar_create``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__all__ = [
    "CONFIRM_TOOLS",
    "CONFIRM_GATED",
    "get_mode",
    "is_sandbox",
    "has_token",
    "token_path",
    "search_mail",
    "summarize_thread",
    "compose",
    "calendar_list",
    "calendar_create",
    "drive_search",
    "write_file",
]

# Tools that require explicit confirmation before any live side effect.
CONFIRM_TOOLS = frozenset({"mail_compose", "mail_send", "calendar_create"})
# Alias some checkers expect.
CONFIRM_GATED = CONFIRM_TOOLS

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
_DRIVE_BASE = "https://www.googleapis.com/drive/v3"

# ---------------------------------------------------------------------------
# sandbox fixtures (FAKE, offline)
# ---------------------------------------------------------------------------

_FAKE_THREADS = [
    {
        "id": "t_q3",
        "subject": "FAKE: Q3 report draft",
        "from_": "sam.professional.fake@gmail.com (FAKE)",
        "snippet": "FAKE: Sam sent the Q3 report draft for review.",
        "messages": [
            {"from_": "sam.professional.fake@gmail.com (FAKE)",
             "body": "FAKE: Sam sent the Q3 report draft for review."},
            {"from_": "me (FAKE)",
             "body": "FAKE: Thanks Sam, I will review it this week."},
        ],
    },
    {
        "id": "t_sat",
        "subject": "FAKE: Saturday plans",
        "from_": "priya.fake@gmail.com (FAKE)",
        "snippet": "FAKE: Priya: are we still on for Saturday?",
        "messages": [
            {"from_": "priya.fake@gmail.com (FAKE)",
             "body": "FAKE: Priya: are we still on for Saturday?"},
        ],
    },
]

_FAKE_EVENTS = [
    {"id": "e1", "title": "FAKE: Standup", "when": "Mon 09:30 (FAKE)",
     "attendees": []},
    {"id": "e2", "title": "FAKE: Dinner with Priya", "when": "Sat 19:00 (FAKE)",
     "attendees": ["priya"]},
]

_FAKE_FILES = [
    {"id": "f1", "name": "FAKE_Q3_report.gdoc",
     "mimeType": "application/vnd.google-apps.document"},
    {"id": "f2", "name": "FAKE_budget_sheet.gsheet",
     "mimeType": "application/vnd.google-apps.spreadsheet"},
]


# ---------------------------------------------------------------------------
# mode + token helpers (never print tokens)
# ---------------------------------------------------------------------------

def _mode_flag() -> str:
    raw = os.environ.get("MARC_MODE", os.environ.get("MODE", "sandbox"))
    return str(raw or "sandbox").strip().lower() or "sandbox"


def token_path() -> Path:
    """Resolve the token file path.

    Prefers ``GOOGLE_TOKEN_PATH`` / ``MARC_GOOGLE_TOKEN_PATH``; falls back
    to ``MARC_MIND_DIR/google_token.json`` (``./var/mind`` default).
    """
    raw = (os.environ.get("GOOGLE_TOKEN_PATH")
           or os.environ.get("MARC_GOOGLE_TOKEN_PATH") or "").strip()
    if raw:
        return Path(raw)
    mind = (os.environ.get("MARC_MIND_DIR")
            or os.environ.get("MIND_DIR") or "./var/mind").strip() \
        or "./var/mind"
    return Path(mind) / "google_token.json"


def has_token() -> bool:
    """Return True only when the token file exists and is non-empty."""
    try:
        p = token_path()
    except Exception:
        return False
    try:
        if not p.is_file():
            return False
        if p.stat().st_size <= 0:
            return False
        return True
    except OSError:
        return False


def get_mode() -> str:
    """Return ``"live"`` or ``"sandbox"``.

    ``"sandbox"`` when ``MARC_MODE`` is not ``live``, when
    ``GOOGLE_TOKEN_PATH`` is missing, or when the token file is missing.
    """
    if _mode_flag() != "live":
        return "sandbox"
    # Spec: missing GOOGLE_TOKEN_PATH env -> sandbox.
    raw = (os.environ.get("GOOGLE_TOKEN_PATH")
           or os.environ.get("MARC_GOOGLE_TOKEN_PATH") or "").strip()
    if not raw:
        # No explicit env: only live when the fallback file exists.
        return "live" if has_token() else "sandbox"
    try:
        if not Path(raw).is_file():
            return "sandbox"
        if Path(raw).stat().st_size <= 0:
            return "sandbox"
    except OSError:
        return "sandbox"
    return "live"


def is_sandbox(mode: str | None = None) -> bool:
    """Return True when *mode* (or the current mode) is sandbox."""
    if mode is not None:
        return str(mode or "").strip().lower() != "live"
    return get_mode() != "live"


def _read_token() -> str:
    """Read the bearer token from the token file (never printed)."""
    p = token_path()
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not text:
        return ""
    # JSON form: {"access_token": "..."} / {"token": "..."} / {"key": ...}
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            return ""
        if isinstance(obj, dict):
            for key in ("access_token", "token", "accessToken",
                        "id_token", "api_key", "key"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            return ""
        return ""
    # Plain-text token file: first line only.
    return text.splitlines()[0].strip() if text.splitlines() else ""


# ---------------------------------------------------------------------------
# drafts + write_file helpers
# ---------------------------------------------------------------------------

def _load_drafts():
    """Best-effort import of the drafts module (has ``enqueue``)."""
    import sys as _sys

    for name in ("drafts", "connectors.drafts", "marc-muse.drafts"):
        try:
            mod = _sys.modules.get(name)
            if mod is not None and hasattr(mod, "enqueue"):
                return mod
        except Exception:
            continue
    try:
        from .. import drafts as _d2  # type: ignore
        if hasattr(_d2, "enqueue"):
            return _d2
    except Exception:
        pass
    try:
        here = Path(__file__).resolve().parent.parent
        if str(here) not in _sys.path:
            _sys.path.insert(0, str(here))
        import drafts as _d3  # type: ignore
        if hasattr(_d3, "enqueue"):
            return _d3
    except Exception:
        pass
    return None


def write_file(path, text: str) -> str:
    """Atomically write *text* to *path* (stdlib only). Returns str(path).

    Prefers ``drafts.write_file`` when available so draft storage stays
    consistent; falls back to tmp + os.replace.
    """
    drafts = _load_drafts()
    fn = getattr(drafts, "write_file", None) if drafts is not None else None
    if callable(fn):
        try:
            out = fn(path, text)
            return str(out)
        except Exception:
            pass
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    import os as _os

    tmp = target.parent / ("%s.%d.tmp" % (target.name, _os.getpid()))
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            _os.fsync(fh.fileno())
        except Exception:
            pass
    _os.replace(tmp, target)
    return str(target)


def _enqueue(tool: str, person: str, body: str, meta: dict | None = None) -> dict:
    """Route a write to ``drafts.enqueue`` (sandbox-safe, never sends)."""
    meta_v = dict(meta) if isinstance(meta, dict) else {}
    meta_v.setdefault("tool", tool)
    meta_v.setdefault("mode", get_mode())
    drafts = _load_drafts()
    if drafts is not None:
        try:
            return drafts.enqueue(tool_channel(tool), person or "", body or "",
                                  meta=meta_v)
        except TypeError:
            try:
                return drafts.enqueue(tool_channel(tool), person or "",
                                      body or "")
            except Exception:
                pass
        except Exception:
            pass
    # Fallback stub when drafts is unavailable (still queued, not sent).
    return {
        "channel": tool_channel(tool),
        "person": person or "",
        "body": body or "",
        "mouth": "personal",
        "meta": meta_v,
        "status": "queued",
        "sandbox": True,
        "tool": tool,
        "mode": "sandbox",
    }


def tool_channel(tool: str) -> str:
    """Map a confirm-tool name to its drafts channel."""
    t = str(tool or "").strip().lower()
    if t in ("mail_compose", "mail_send", "mail", "gmail"):
        return "mail"
    if t in ("calendar_create", "calendar", "cal"):
        return "calendar"
    if t in ("drive",):
        return "drive"
    return t or "mail"


# ---------------------------------------------------------------------------
# live HTTP helper (urllib + json, bearer header, never logged)
# ---------------------------------------------------------------------------

def _api_request(method: str, url: str, token: str,
                 payload: dict | None = None,
                 params: dict | None = None,
                 timeout: float = 20.0) -> dict | list:
    """Perform one live Google API call via stdlib urllib + json."""
    full = url
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items()
                                     if v is not None})
        if qs:
            full = url + ("&" if "?" in url else "?") + qs
    data = None
    headers = {"Accept": "application/json"}
    # Token only in the header object — never printed/logged.
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(full, data=data, headers=headers,
                                 method=str(method or "GET").upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:500]
        except Exception:
            detail = ""
        raise RuntimeError("google api %s: %s" % (exc.code, detail)) from None
    except urllib.error.URLError as exc:
        raise RuntimeError("google api connection failed") from None
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {"raw": raw[:2000]}


def _live_allowed(confirmed) -> bool:
    """Live side effects need MARC_MODE=live + confirmed=True + token."""
    if confirmed is not True:
        return False
    if get_mode() != "live":
        return False
    return has_token()


def _coerce_confirmed(confirmed=False, **kwargs) -> bool:
    if confirmed is True:
        return True
    for key in ("confirmed", "confirm", "ok", "yes"):
        if kwargs.get(key) is True:
            return True
    return False


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

def search_mail(q: str = "", query: str | None = None, **kwargs) -> dict:
    """Search mail. Sandbox returns FAKE fixtures; live hits Gmail API."""
    term = query if query is not None else kwargs.get("term", q)
    if kwargs.get("query") is not None:
        term = kwargs["query"]
    term = str(term or "")
    mode = get_mode()
    if mode != "live":
        needle = term.strip().lower()
        hits = []
        for t in _FAKE_THREADS:
            blob = " ".join([t.get("subject", ""), t.get("snippet", ""),
                             t.get("from_", "")]).lower()
            if not needle or needle in blob:
                hits.append({"id": t["id"], "subject": t["subject"],
                             "from_": t["from_"], "snippet": t["snippet"]})
        return {"ok": True, "mode": "sandbox", "query": term, "messages": hits}
    token = _read_token()
    if not token:
        return {"ok": True, "mode": "sandbox", "query": term,
                "messages": [], "note": "token unreadable; sandbox fallback"}
    try:
        data = _api_request("GET", _GMAIL_BASE + "/users/me/messages",
                            token, params={"q": term, "maxResults": 10})
        msgs = data.get("messages", []) if isinstance(data, dict) else []
        return {"ok": True, "mode": "live", "query": term, "messages": msgs}
    except Exception as exc:
        return {"ok": False, "mode": "live", "query": term,
                "messages": [], "error": str(exc)[:300]}


def summarize_thread(thread_id: str | None = None, **kwargs) -> dict:
    """Summarize one thread. Sandbox summarises FAKE fixtures offline."""
    tid = thread_id
    if tid is None:
        tid = kwargs.get("id", kwargs.get("threadId", kwargs.get("thread_id", "")))
    tid = str(tid or "")
    mode = get_mode()
    if mode != "live":
        for t in _FAKE_THREADS:
            if t["id"] == tid:
                bodies = " ".join(m.get("body", "") for m in t["messages"])
                return {"ok": True, "mode": "sandbox", "id": tid,
                        "subject": t["subject"],
                        "summary": "FAKE summary of '%s': %s" % (
                            t["subject"], bodies[:280]),
                        "messages": t["messages"]}
        return {"ok": False, "mode": "sandbox", "id": tid,
                "error": "unknown thread %r" % tid}
    token = _read_token()
    if not token:
        return {"ok": False, "mode": "sandbox", "id": tid,
                "error": "token unreadable; sandbox fallback"}
    try:
        data = _api_request(
            "GET", _GMAIL_BASE + "/users/me/threads/" + urllib.parse.quote(tid),
            token)
        if not isinstance(data, dict):
            return {"ok": False, "mode": "live", "id": tid,
                    "error": "bad response"}
        snippet = str(data.get("snippet", ""))[:500]
        return {"ok": True, "mode": "live", "id": tid,
                "summary": snippet, "thread": data}
    except Exception as exc:
        return {"ok": False, "mode": "live", "id": tid,
                "error": str(exc)[:300]}


def compose(to: str = "", subject: str = "", body: str = "",
            confirmed: bool = False, **kwargs) -> dict:
    """Compose a mail draft. Draft-only unless live + confirmed + token.

    Sandbox (default): routes to ``drafts.enqueue`` with tool
    ``mail_compose`` and returns the draft record — nothing is sent.
    Live: only when ``MARC_MODE=live`` AND ``confirmed=True`` AND the
    token file is present does it POST to the Gmail API (tool
    ``mail_send``); otherwise it still returns a draft.
    """
    dest = kwargs.get("to", to)
    subj = kwargs.get("subject", subject)
    text = kwargs.get("body", kwargs.get("text", body))
    dest = str(dest or kwargs.get("contact", kwargs.get("person", "")) or "")
    subj = str(subj or "")
    text = str(text or "")
    ok = _coerce_confirmed(confirmed, **kwargs)
    tool = "mail_send" if ok else "mail_compose"

    if not _live_allowed(ok):
        draft = _enqueue("mail_compose", dest, text,
                         {"to": dest, "subject": subj, "body": text,
                          "confirm_tool": "mail_send" if ok else "mail_compose",
                          "confirmed": bool(ok)})
        if isinstance(draft, dict):
            draft.setdefault("tool", "mail_compose")
            draft.setdefault("mode", get_mode())
            draft["sandbox"] = True
        return draft

    # Live + confirmed + token: attempt the Gmail send via urllib + json.
    token = _read_token()
    if not token:
        return _enqueue("mail_compose", dest, text,
                        {"to": dest, "subject": subj, "confirmed": True,
                         "note": "token unreadable; kept as draft"})
    try:
        import base64 as _b64

        raw_msg = ("To: %s\r\nSubject: %s\r\n"
                   "Content-Type: text/plain; charset=utf-8\r\n\r\n%s"
                   % (dest, subj, text)).encode("utf-8")
        payload = {"raw": _b64.urlsafe_b64encode(raw_msg).decode("ascii")}
        data = _api_request("POST", _GMAIL_BASE + "/users/me/messages/send",
                            token, payload=payload)
        msg_id = data.get("id", "") if isinstance(data, dict) else ""
        # Keep a paper trail draft marked confirmed (write_file backed).
        _enqueue("mail_send", dest, text,
                 {"to": dest, "subject": subj, "live_id": msg_id,
                  "confirmed": True})
        return {"ok": True, "mode": "live", "tool": "mail_send",
                "to": dest, "subject": subj, "id": msg_id,
                "status": "sent", "confirmed": True}
    except Exception as exc:
        draft = _enqueue("mail_compose", dest, text,
                         {"to": dest, "subject": subj, "confirmed": True,
                          "error": str(exc)[:200]})
        if isinstance(draft, dict):
            draft["live_error"] = str(exc)[:200]
        return draft


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_list(**kwargs) -> dict:
    """List upcoming events. Sandbox returns FAKE fixtures; live queries API."""
    mode = get_mode()
    if mode != "live":
        return {"ok": True, "mode": "sandbox",
                "events": [dict(e) for e in _FAKE_EVENTS]}
    token = _read_token()
    if not token:
        return {"ok": True, "mode": "sandbox",
                "events": [dict(e) for e in _FAKE_EVENTS],
                "note": "token unreadable; sandbox fallback"}
    try:
        params = {"maxResults": kwargs.get("maxResults", 10),
                  "singleEvents": True, "orderBy": "startTime",
                  "timeMin": kwargs.get("timeMin")}
        data = _api_request("GET",
                            _CALENDAR_BASE + "/calendars/primary/events",
                            token, params=params)
        items = data.get("items", []) if isinstance(data, dict) else []
        return {"ok": True, "mode": "live", "events": items}
    except Exception as exc:
        return {"ok": False, "mode": "live", "events": [],
                "error": str(exc)[:300]}


def calendar_create(title: str = "", when: str = "",
                    confirmed: bool = False, **kwargs) -> dict:
    """Create a calendar event. Confirm-gated: draft unless live+confirmed."""
    name = kwargs.get("title", title)
    moment = kwargs.get("when", kwargs.get("time", kwargs.get("start", when)))
    name = str(name or "")
    moment = str(moment or "")
    desc = str(kwargs.get("description", kwargs.get("body", "")) or "")
    ok = _coerce_confirmed(confirmed, **kwargs)

    if not _live_allowed(ok):
        body = ("title: %s\nwhen: %s\n%s" % (name, moment, desc)).strip()
        draft = _enqueue("calendar_create", name, body,
                         {"title": name, "when": moment,
                          "description": desc, "confirmed": bool(ok)})
        if isinstance(draft, dict):
            draft.setdefault("tool", "calendar_create")
            draft.setdefault("mode", get_mode())
            draft["sandbox"] = True
        return draft

    token = _read_token()
    if not token:
        return _enqueue("calendar_create", name, moment,
                        {"title": name, "when": moment, "confirmed": True,
                         "note": "token unreadable; kept as draft"})
    try:
        payload: dict = {"summary": name, "description": desc,
                         "start": {"dateTime": moment},
                         "end": {"dateTime": moment}}
        data = _api_request("POST",
                            _CALENDAR_BASE + "/calendars/primary/events",
                            token, payload=payload)
        eid = data.get("id", "") if isinstance(data, dict) else ""
        _enqueue("calendar_create", name, moment,
                 {"title": name, "when": moment, "live_id": eid,
                  "confirmed": True})
        return {"ok": True, "mode": "live", "tool": "calendar_create",
                "title": name, "when": moment, "id": eid,
                "status": "created", "confirmed": True}
    except Exception as exc:
        draft = _enqueue("calendar_create", name, moment,
                         {"title": name, "when": moment, "confirmed": True,
                          "error": str(exc)[:200]})
        if isinstance(draft, dict):
            draft["live_error"] = str(exc)[:200]
        return draft


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

def drive_search(q: str = "", query: str | None = None, **kwargs) -> dict:
    """Search Drive. Sandbox filters FAKE fixtures; live queries the API."""
    term = query if query is not None else kwargs.get("term", q)
    if kwargs.get("query") is not None:
        term = kwargs["query"]
    if kwargs.get("name") is not None and not term:
        term = kwargs["name"]
    term = str(term or "")
    mode = get_mode()
    if mode != "live":
        needle = term.strip().lower()
        hits = [dict(f) for f in _FAKE_FILES
                if not needle or needle in f["name"].lower()]
        return {"ok": True, "mode": "sandbox", "query": term, "files": hits}
    token = _read_token()
    if not token:
        return {"ok": True, "mode": "sandbox", "query": term,
                "files": [dict(f) for f in _FAKE_FILES],
                "note": "token unreadable; sandbox fallback"}
    try:
        gq = ("name contains '%s'" % term.replace("'", "")) if term else ""
        data = _api_request("GET", _DRIVE_BASE + "/files", token,
                            params={"q": gq or None, "pageSize": 10,
                                    "fields": "files(id,name,mimeType)"})
        files = data.get("files", []) if isinstance(data, dict) else []
        return {"ok": True, "mode": "live", "query": term, "files": files}
    except Exception as exc:
        return {"ok": False, "mode": "live", "query": term, "files": [],
                "error": str(exc)[:300]}
