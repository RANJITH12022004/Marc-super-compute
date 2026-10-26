"""Meta Cloud connector — WhatsApp Cloud API + Instagram Graph (stdlib only).

Sandbox-first: unless ``MARC_MODE=live`` AND ``META_WA_ACCESS_TOKEN`` is set,
``send_whatsapp`` / ``send_instagram`` NEVER touch the network. They route to
``drafts.enqueue`` with ``mouth="business"`` and return the draft record.

Live (opt-in only): ``MARC_MODE=live`` plus a non-empty token performs one
stdlib ``urllib`` POST with the token in the ``Authorization`` header only.
Tokens are never printed, never logged, never embedded in errors.

Environment:

- ``META_WA_ACCESS_TOKEN`` (aliases ``META_WA_TOKEN`` / ``WHATSAPP_TOKEN`` /
  ``MARC_WA_TOKEN``): WhatsApp Cloud API bearer token. Empty -> sandbox.
- ``META_IG_ACCESS_TOKEN`` (aliases ``META_IG_TOKEN`` / ``INSTAGRAM_TOKEN``):
  Instagram Graph bearer token. Falls back to the WhatsApp token when unset.
- ``META_APP_SECRET`` (aliases ``MARC_APP_SECRET`` / ``APP_SECRET``): app
  secret used to verify webhook signatures (HMAC SHA256). Unset -> sandbox
  accept (verify returns True without checking).
- ``MARC_MODE`` / ``MODE``: ``"live"`` opts into network; anything else is
  sandbox (default).
- ``META_WA_PHONE_NUMBER_ID`` (aliases ``META_PHONE_NUMBER_ID`` /
  ``MARC_PHONE_NUMBER_ID``): WhatsApp sender phone-number-id for live sends.
- ``META_VERIFY_TOKEN`` (alias ``MARC_VERIFY_TOKEN``): hub challenge token.

FAKE test fixtures (never contact real users; offline only):

- WhatsApp (FAKE): ``+1-555-0102`` (Priya), ``+1-555-0104`` (Ravi).
- Instagram (FAKE): ``@priya.fake.ig`` (Priya), ``@alex.fake.stranger`` (Alex).
- Mail-adjacent FAKE: ``sam.professional.fake@gmail.com`` (used elsewhere).
- All sandbox example bodies are prefixed ``FAKE:`` and stay offline.

Webhook:

- ``verify_signature(raw_body, signature)`` checks ``X-Hub-Signature-256``
  (``sha256=<hex>`` HMAC SHA256 of the raw body with ``META_APP_SECRET``).
  When no secret is configured it accepts sandbox traffic (returns True).
- ``parse_webhook(payload)`` accepts a dict, JSON str, or bytes and extracts
  WhatsApp + Instagram inbound messages into a list of
  ``{channel, from_, body, id, ...}`` dicts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__all__ = [
    "GRAPH_VERSION",
    "GRAPH_BASE",
    "FAKE_NUMBERS",
    "FAKE_CONTACTS",
    "get_mode",
    "is_sandbox",
    "has_token",
    "has_wa_token",
    "send_whatsapp",
    "send_instagram",
    "verify_signature",
    "verify_webhook",
    "verify_webhook_signature",
    "verify_challenge",
    "parse_webhook",
    "parse_webhook_messages",
    "write_file",
]

GRAPH_VERSION = "v21.0"
GRAPH_BASE = "https://graph.facebook.com/%s" % GRAPH_VERSION

# FAKE test numbers/handles (offline fixtures, documented for tests).
FAKE_NUMBERS = (
    "+1-555-0102 (FAKE)",
    "+1-555-0104 (FAKE)",
)
FAKE_CONTACTS = {
    "whatsapp": ["+1-555-0102 (FAKE)", "+1-555-0104 (FAKE)"],
    "instagram": ["@priya.fake.ig (FAKE)", "@alex.fake.stranger (FAKE)"],
}


# ---------------------------------------------------------------------------
# env / mode helpers (tokens never printed)
# ---------------------------------------------------------------------------

def _mode_flag() -> str:
    raw = os.environ.get("MARC_MODE", os.environ.get("MODE", "sandbox"))
    return str(raw or "sandbox").strip().lower() or "sandbox"


def _env_first(*names: str) -> str:
    for name in names:
        try:
            val = os.environ.get(name)
        except Exception:
            continue
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return ""


def _wa_token() -> str:
    return _env_first(
        "META_WA_ACCESS_TOKEN",
        "META_WA_TOKEN",
        "MARC_WA_TOKEN",
        "WHATSAPP_TOKEN",
        "META_WHATSAPP_TOKEN",
    )


def _ig_token() -> str:
    tok = _env_first(
        "META_IG_ACCESS_TOKEN",
        "META_IG_TOKEN",
        "MARC_IG_TOKEN",
        "INSTAGRAM_TOKEN",
        "META_INSTAGRAM_TOKEN",
    )
    if tok:
        return tok
    return _wa_token()


def _app_secret() -> str:
    return _env_first("META_APP_SECRET", "MARC_APP_SECRET", "APP_SECRET")


def _phone_number_id() -> str:
    return _env_first(
        "META_WA_PHONE_NUMBER_ID",
        "META_PHONE_NUMBER_ID",
        "MARC_PHONE_NUMBER_ID",
        "PHONE_NUMBER_ID",
    )


def _verify_token() -> str:
    return _env_first("META_VERIFY_TOKEN", "MARC_VERIFY_TOKEN", "VERIFY_TOKEN")


def has_token() -> bool:
    """Return True only when a WhatsApp/Graph bearer token is configured."""
    return bool(_wa_token())


def has_wa_token() -> bool:
    """Alias for :func:`has_token`."""
    return bool(_wa_token())


def get_mode() -> str:
    """Return ``"live"`` or ``"sandbox"``.

    ``"sandbox"`` when ``MARC_MODE`` is not ``live`` or when
    ``META_WA_ACCESS_TOKEN`` is empty. ``"live"`` only when both are set.
    """
    if _mode_flag() != "live":
        return "sandbox"
    if not _wa_token():
        return "sandbox"
    return "live"


def is_sandbox(mode: str | None = None) -> bool:
    """Return True when *mode* (or the current mode) is sandbox."""
    if mode is not None:
        return str(mode or "").strip().lower() != "live"
    return get_mode() != "live"


# ---------------------------------------------------------------------------
# drafts helper (sandbox-safe, never sends)
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
    """Atomically write *text* to *path* (stdlib only). Returns str(path)."""
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


def _enqueue_business(channel: str, person: str, body: str,
                      meta: dict | None = None) -> dict:
    """Enqueue a draft with ``mouth="business"`` (sandbox path)."""
    meta_v = dict(meta) if isinstance(meta, dict) else {}
    meta_v.setdefault("mode", "sandbox")
    drafts = _load_drafts()
    if drafts is not None:
        try:
            return drafts.enqueue(channel, person or "", body or "",
                                  mouth="business", meta=meta_v)
        except TypeError:
            try:
                return drafts.enqueue(channel, person or "", body or "",
                                      "business")
            except Exception:
                pass
        except Exception:
            pass
    return {
        "channel": channel,
        "person": person or "",
        "body": body or "",
        "mouth": "business",
        "meta": meta_v,
        "status": "queued",
        "sandbox": True,
        "mode": "sandbox",
    }


# ---------------------------------------------------------------------------
# live HTTP helper (urllib + json, bearer header only)
# ---------------------------------------------------------------------------

def _api_post(url: str, token: str, payload: dict,
              timeout: float = 20.0) -> dict | list:
    """POST JSON via stdlib urllib with bearer auth."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:500]
        except Exception:
            detail = ""
        raise RuntimeError("meta api %s" % (detail or exc.code,)) from None
    except urllib.error.URLError as exc:
        raise RuntimeError("meta api connection failed") from None
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {"raw": raw[:2000]}


def _coerce_to_body(to: str = "", body: str = "", **kwargs) -> tuple[str, str]:
    dest = to
    text = body
    for key in ("to", "to_", "recipient", "recipient_id", "contact", "person",
                "phone", "to_number"):
        val = kwargs.get(key)
        if val is not None and str(val).strip() != "" and not dest:
            dest = str(val)
    if not dest and isinstance(to, str):
        dest = to
    for key in ("body", "text", "message", "msg"):
        val = kwargs.get(key)
        if isinstance(val, str) and val != "" and not text:
            text = val
    return str(dest or "").strip(), str(text or "")


# ---------------------------------------------------------------------------
# senders — sandbox enqueues business drafts, never HTTP
# ---------------------------------------------------------------------------

def send_whatsapp(to: str = "", body: str = "", **kwargs) -> dict:
    """Send a WhatsApp message via the Cloud API (sandbox-safe).

    Sandbox (default: ``META_WA_ACCESS_TOKEN`` empty or ``MARC_MODE`` not
    ``live``): enqueues a draft with ``mouth="business"`` and never performs
    HTTP. Live (``MARC_MODE=live`` + token): POSTs to
    ``https://graph.facebook.com/<v>/`` ``<phone-number-id>/messages``.

    FAKE test numbers (offline): ``+1-555-0102`` / ``+1-555-0104``.
    """
    dest, text = _coerce_to_body(to, body, **kwargs)
    if get_mode() != "live" or not _wa_token():
        draft = _enqueue_business(
            "whatsapp", dest, text,
            {"tool": "send_whatsapp", "to": dest,
             "phone_number_id": _phone_number_id() or "",
             "sandbox": True})
        if isinstance(draft, dict):
            draft.setdefault("tool", "send_whatsapp")
            draft.setdefault("mode", "sandbox")
            draft["sandbox"] = True
            try:
                if draft.get("mouth") != "business":
                    draft["mouth"] = "business"
            except Exception:
                pass
        return draft
    token = _wa_token()
    if not token:
        return _enqueue_business("whatsapp", dest, text,
                                 {"tool": "send_whatsapp", "to": dest})
    phone_id = _phone_number_id()
    if not phone_id:
        draft = _enqueue_business(
            "whatsapp", dest, text,
            {"tool": "send_whatsapp", "to": dest,
             "note": "missing phone-number-id; kept as draft"})
        if isinstance(draft, dict):
            draft["live_error"] = "missing phone-number-id"
        return draft
    url = "%s/%s/messages" % (GRAPH_BASE, urllib.parse.quote(phone_id))
    payload = {"messaging_product": "whatsapp", "to": dest,
               "type": "text", "text": {"body": text}}
    try:
        data = _api_post(url, token, payload)
        mid = ""
        if isinstance(data, dict):
            msgs = data.get("messages")
            if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                mid = str(msgs[0].get("id", ""))
        return {"ok": True, "mode": "live", "tool": "send_whatsapp",
                "channel": "whatsapp", "to": dest, "id": mid,
                "status": "sent", "mouth": "business",
                "response": data}
    except Exception as exc:
        draft = _enqueue_business(
            "whatsapp", dest, text,
            {"tool": "send_whatsapp", "to": dest,
             "error": str(exc)[:200]})
        if isinstance(draft, dict):
            draft["live_error"] = str(exc)[:200]
        return draft


def send_instagram(to: str = "", body: str = "", **kwargs) -> dict:
    """Send an Instagram message via the Graph API (sandbox-safe).

    Sandbox (default: ``META_WA_ACCESS_TOKEN`` empty or ``MARC_MODE`` not
    ``live``): enqueues a draft with ``mouth="business"`` and never performs
    HTTP. Live (``MARC_MODE=live`` + token): POSTs to
    ``https://graph.facebook.com/<v>/me/messages``.

    FAKE test handles (offline): ``@priya.fake.ig`` /
    ``@alex.fake.stranger``.
    """
    dest, text = _coerce_to_body(to, body, **kwargs)
    if get_mode() != "live" or not _wa_token():
        draft = _enqueue_business(
            "instagram", dest, text,
            {"tool": "send_instagram", "to": dest, "sandbox": True})
        if isinstance(draft, dict):
            draft.setdefault("tool", "send_instagram")
            draft.setdefault("mode", "sandbox")
            draft["sandbox"] = True
            try:
                if draft.get("mouth") != "business":
                    draft["mouth"] = "business"
            except Exception:
                pass
        return draft
    token = _ig_token()
    if not token:
        return _enqueue_business("instagram", dest, text,
                                 {"tool": "send_instagram", "to": dest})
    url = "%s/me/messages" % GRAPH_BASE
    payload = {"recipient": {"id": dest}, "messaging_type": "RESPONSE",
               "message": {"text": text}}
    try:
        data = _api_post(url, token, payload)
        mid = str(data.get("message_id", "")) if isinstance(data, dict) else ""
        return {"ok": True, "mode": "live", "tool": "send_instagram",
                "channel": "instagram", "to": dest, "id": mid,
                "status": "sent", "mouth": "business",
                "response": data}
    except Exception as exc:
        draft = _enqueue_business(
            "instagram", dest, text,
            {"tool": "send_instagram", "to": dest,
             "error": str(exc)[:200]})
        if isinstance(draft, dict):
            draft["live_error"] = str(exc)[:200]
        return draft


# ---------------------------------------------------------------------------
# webhook verification — HMAC SHA256 of META_APP_SECRET
# ---------------------------------------------------------------------------

def _raw_bytes(raw) -> bytes:
    if raw is None:
        return b""
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, str):
        return raw.encode("utf-8")
    if isinstance(raw, dict):
        try:
            return json.dumps(raw, separators=(",", ":"),
                              sort_keys=True).encode("utf-8")
        except Exception:
            return str(raw).encode("utf-8")
    return str(raw).encode("utf-8")


def verify_signature(raw_body, signature: str | None = None, **kwargs) -> bool:
    """Verify a Meta webhook signature (HMAC SHA256).

    ``signature`` is the ``X-Hub-Signature-256`` header value
    (``"sha256=<hex>"`` or bare ``"<hex>"``). The HMAC key is
    ``META_APP_SECRET``. When no secret is configured, sandbox traffic is
    accepted (returns True). Uses ``hmac.compare_digest``.
    """
    sig = signature
    if sig is None:
        for key in ("signature", "sig", "hub_signature",
                    "x_hub_signature_256", "X-Hub-Signature-256",
                    "X-Hub-Signature"):
            if kwargs.get(key) not in (None, ""):
                sig = kwargs[key]
                break
    if isinstance(raw_body, dict) and sig is None:
        # Allow verify_signature({"body": ..., "signature": ...}) forms.
        for key in ("signature", "sig", "hub_signature",
                    "x_hub_signature_256"):
            if raw_body.get(key) not in (None, ""):
                sig = raw_body.get(key)
                break
        raw_body = raw_body.get("body", raw_body.get("raw", raw_body.get("payload", "")))
    secret = _app_secret()
    if not secret:
        # No secret configured -> accept sandbox traffic.
        return True
    if sig is None or str(sig).strip() == "":
        return False
    s = str(sig).strip()
    if "=" in s:
        s = s.split("=", 1)[1].strip()
    s = s.lower()
    digest = hmac.new(secret.encode("utf-8"), _raw_bytes(raw_body),
                      hashlib.sha256).hexdigest().lower()
    try:
        return hmac.compare_digest(digest, s)
    except Exception:
        return False


def verify_webhook(raw_body=None, signature: str | None = None,
                   **kwargs) -> bool:
    """Alias for :func:`verify_signature` (webhook HMAC check)."""
    if raw_body is None:
        for key in ("raw", "body", "payload", "data"):
            if kwargs.get(key) is not None:
                raw_body = kwargs[key]
                break
    if signature is None:
        for key in ("signature", "sig", "hub_signature",
                    "x_hub_signature_256", "X-Hub-Signature-256"):
            if kwargs.get(key) not in (None, ""):
                signature = kwargs[key]
                break
    if raw_body is None:
        raw_body = kwargs.get("payload", "")
    return verify_signature(raw_body if raw_body is not None else "",
                            signature, **kwargs)


def verify_webhook_signature(raw_body=None, signature: str | None = None,
                             **kwargs) -> bool:
    """Alias for :func:`verify_signature`."""
    return verify_webhook(raw_body, signature, **kwargs)


def verify_challenge(params: dict | None = None, **kwargs) -> str | None:
    """Verify a Meta webhook hub-challenge (GET verification).

    Returns the ``hub.challenge`` string when ``hub.mode == "subscribe"``
    and ``hub.verify_token`` matches ``META_VERIFY_TOKEN``; otherwise None.
    When no verify token is configured, accepts sandbox challenges.
    """
    data: dict = {}
    if isinstance(params, dict):
        data.update(params)
    for k, v in kwargs.items():
        data.setdefault(k, v)
        data.setdefault(k.replace("_", ".", 1) if "_" in k else k, v)
    mode = str(data.get("hub.mode", data.get("hub_mode",
                data.get("mode", "")) or "")).strip()
    token = str(data.get("hub.verify_token", data.get("hub_verify_token",
                data.get("verify_token", data.get("token", ""))) or ""))
    challenge = data.get("hub.challenge", data.get("hub_challenge",
                  data.get("challenge", "")))
    if mode != "subscribe" or str(challenge or "") == "":
        return None
    expected = _verify_token()
    if not expected:
        return str(challenge)
    try:
        if hmac.compare_digest(str(token), str(expected)):
            return str(challenge)
    except Exception:
        if str(token) == str(expected):
            return str(challenge)
    return None


# ---------------------------------------------------------------------------
# webhook parsing — extract inbound messages
# ---------------------------------------------------------------------------

class ParsedWebhook(list):
    """List of parsed inbound messages with dict-style helpers.

    Iterating / indexing yields message dicts; ``result["messages"]`` or
    ``result.get("messages")`` returns the plain list; ``result.get("ok")``
    reports parse status. This keeps ``parse_webhook`` compatible with both
    list-style (``msgs[0]["body"]``) and dict-style
    (``res["messages"]``) callers.
    """

    def __init__(self, messages=None, meta: dict | None = None):
        super().__init__(messages or [])
        self._meta: dict = dict(meta) if isinstance(meta, dict) else {}
        self._meta.setdefault("ok", True)
        self._meta.setdefault("count", len(self))

    def get(self, key, default=None):  # type: ignore[override]
        if key == "messages":
            return list(self)
        if isinstance(key, str) and key in self._meta:
            return self._meta[key]
        return default

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, str):
            if key == "messages":
                return list(self)
            return self._meta[key]
        return super().__getitem__(key)

    def __contains__(self, key):  # type: ignore[override]
        if isinstance(key, str):
            return key in self._meta or key == "messages"
        return super().__contains__(key)

    def keys(self):  # type: ignore[override]
        return ["messages", *[k for k in self._meta if k != "messages"]]

    def __iter__(self):  # type: ignore[override]
        return super().__iter__()

    @property
    def messages(self) -> list:
        return list(self)

    @property
    def ok(self) -> bool:
        return bool(self._meta.get("ok", True))


def _wa_text(msg: dict) -> str:
    if not isinstance(msg, dict):
        return ""
    mtype = str(msg.get("type", "") or "")
    if mtype == "text":
        txt = msg.get("text")
        if isinstance(txt, dict):
            return str(txt.get("body", "") or "")
        if isinstance(txt, str):
            return txt
    for key in ("text", "body", "caption"):
        val = msg.get(key)
        if isinstance(val, dict) and isinstance(val.get("body"), str):
            return str(val["body"])
        if isinstance(val, str) and val:
            return val
    button = msg.get("button")
    if isinstance(button, dict) and isinstance(button.get("text"), str):
        return str(button["text"])
    interactive = msg.get("interactive")
    if isinstance(interactive, dict):
        for sub in ("button_reply", "list_reply"):
            node = interactive.get(sub)
            if isinstance(node, dict) and node.get("title"):
                return str(node["title"])
    return ""


def _parse_whatsapp_value(value: dict, out: list) -> None:
    if not isinstance(value, dict):
        return
    messages = value.get("messages")
    contacts = value.get("contacts") if isinstance(value.get("contacts"), list) else []
    contact_name = ""
    if contacts and isinstance(contacts[0], dict):
        prof = contacts[0].get("profile") if isinstance(contacts[0].get("profile"), dict) else {}
        contact_name = str(contacts[0].get("name", prof.get("name", "")) or "")
    if not isinstance(messages, list):
        return
    for m in messages:
        if not isinstance(m, dict):
            continue
        body = _wa_text(m)
        if not body:
            # Skip non-text statuses but keep reaction-less empties out.
            continue
        out.append({
            "channel": "whatsapp",
            "from_": str(m.get("from", "") or ""),
            "to": str(value.get("messaging_product", "whatsapp") or "whatsapp"),
            "body": body,
            "id": str(m.get("id", "") or ""),
            "type": str(m.get("type", "text") or "text"),
            "timestamp": str(m.get("timestamp", "") or ""),
            "contact": contact_name,
            "direction": "in",
        })


def _parse_messaging_item(item: dict, out: list) -> None:
    if not isinstance(item, dict):
        return
    sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
    recipient = item.get("recipient") if isinstance(item.get("recipient"), dict) else {}
    message = item.get("message")
    text = ""
    mid = ""
    ts = str(item.get("timestamp", "") or "")
    if isinstance(message, dict):
        mid = str(message.get("mid", "") or "")
        if isinstance(message.get("text"), str):
            text = message["text"]
        elif isinstance(message.get("text"), dict):
            text = str(message["text"].get("body", "") or "")
        if not text and isinstance(message.get("quick_reply"), dict):
            text = str(message["quick_reply"].get("payload", "") or "")
        if not text and message.get("is_echo"):
            return
        if not text and message.get("sticker_id"):
            text = ""
    elif isinstance(message, str):
        text = message
    postback = item.get("postback")
    if not text and isinstance(postback, dict):
        text = str(postback.get("title", postback.get("payload", "")) or "")
    if not text:
        return
    out.append({
        "channel": "instagram",
        "from_": str(sender.get("id", "") or ""),
        "to": str(recipient.get("id", "") or ""),
        "body": text,
        "id": mid,
        "type": "text",
        "timestamp": ts,
        "direction": "in",
    })


def _coerce_payload(payload) -> dict | list:
    if isinstance(payload, (dict, list)):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = bytes(payload).decode("utf-8")
        except Exception:
            return {}
    if isinstance(payload, str):
        s = payload.strip()
        if not s:
            return {}
        try:
            return json.loads(s)
        except (ValueError, json.JSONDecodeError):
            return {"messages": [{"body": payload}]}
    return {}


def parse_webhook(payload=None, **kwargs) -> ParsedWebhook:
    """Extract inbound messages from a Meta webhook payload.

    Accepts WhatsApp Cloud API payloads (``entry[].changes[].value.messages``)
    and Instagram Graph payloads (``entry[].messaging``), plus JSON strings
    or bytes. Returns a :class:`ParsedWebhook` list of
    ``{channel, from_, body, id, ...}`` dicts — ``result["messages"]`` also
    works for dict-style callers. Unknown / empty payloads yield ``[]``.
    """
    if payload is None:
        for key in ("payload", "body", "data", "event", "webhook"):
            if kwargs.get(key) is not None:
                payload = kwargs[key]
                break
    data = _coerce_payload(payload if payload is not None else {})
    messages: list[dict] = []
    obj = ""
    try:
        if isinstance(data, dict):
            obj = str(data.get("object", "") or "")
            entries = data.get("entry")
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    changes = entry.get("changes")
                    if isinstance(changes, list):
                        for change in changes:
                            if not isinstance(change, dict):
                                continue
                            value = change.get("value", {})
                            if isinstance(value, dict) and isinstance(
                                    value.get("messages"), list):
                                _parse_whatsapp_value(value, messages)
                            # Some IG payloads arrive under changes.value.
                            if isinstance(value, dict) and isinstance(
                                    value.get("messaging"), list):
                                for item in value["messaging"]:
                                    _parse_messaging_item(item, messages)
                    messaging = entry.get("messaging")
                    if isinstance(messaging, list):
                        for item in messaging:
                            _parse_messaging_item(item, messages)
                    # Direct messages array (simplified test fixtures).
                    direct = entry.get("messages")
                    if isinstance(direct, list) and not changes and not messaging:
                        for m in direct:
                            if isinstance(m, dict):
                                body = str(m.get("body", m.get("text", "")) or "")
                                if body:
                                    messages.append({
                                        "channel": str(m.get("channel", "whatsapp") or "whatsapp"),
                                        "from_": str(m.get("from_", m.get("from", "")) or ""),
                                        "body": body,
                                        "id": str(m.get("id", "") or ""),
                                        "direction": "in",
                                    })
            # Top-level simplified fixture: {"messages": [...]}.
            if not messages and isinstance(data.get("messages"), list):
                for m in data["messages"]:
                    if isinstance(m, dict):
                        body = str(m.get("body", m.get("text", "")) or "")
                        if body:
                            messages.append({
                                "channel": str(m.get("channel",
                                               "instagram" if obj == "instagram" else "whatsapp")
                                               or "whatsapp"),
                                "from_": str(m.get("from_", m.get("from", "")) or ""),
                                "body": body,
                                "id": str(m.get("id", "") or ""),
                                "direction": "in",
                            })
                    elif isinstance(m, str) and m.strip():
                        messages.append({"channel": "whatsapp", "from_": "",
                                         "body": m, "direction": "in"})
        elif isinstance(data, list):
            for m in data:
                if isinstance(m, dict):
                    body = str(m.get("body", m.get("text", "")) or "")
                    if body:
                        messages.append({"channel": str(m.get("channel", "whatsapp") or "whatsapp"),
                                         "from_": str(m.get("from_", m.get("from", "")) or ""),
                                         "body": body,
                                         "id": str(m.get("id", "") or ""),
                                         "direction": "in"})
    except Exception:
        messages = []
    meta = {"ok": True, "object": obj, "count": len(messages)}
    return ParsedWebhook(messages, meta)


def parse_webhook_messages(payload=None, **kwargs) -> list[dict]:
    """Return parsed webhook messages as a plain list."""
    return list(parse_webhook(payload, **kwargs))
