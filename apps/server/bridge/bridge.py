"""marc bridge — door pull -> loopback muse -> door result.

Loop forever:
  GET  {DOOR_URL}/v1/pull       (Bearer MARC_TOKEN, timeout 30s)
  POST {MARC_MUSE_URL}/utterance JSON {text, session_id, target:auto} (timeout 90s)
  POST {DOOR_URL}/v1/result      JSON {id, ok, spoken, phone_steps, reply}

Env:
  DOOR_URL      https origin, no trailing slash (e.g. https://door.example.com)
  MARC_TOKEN    bearer token for DOOR (and loopback muse when set)
  MARC_MUSE_URL default http://127.0.0.1:8096

Safety:
  - Never binds :8096 (client only, no listen sockets).
  - Never talks to anything except DOOR_URL (https) and 127.0.0.1 muse.
"""

import json
import os
import sys
import time
import urllib.request
from urllib.parse import urlparse


PULL_TIMEOUT = 30
MUSE_TIMEOUT = 90
RESULT_TIMEOUT = 30

OFFLINE_SPOKEN = "Can't reach Marc"
MUSE_DOWN_SPOKEN = "laptop offline"


def _eprint(msg):
    try:
        sys.stderr.write("%s\n" % msg)
        sys.stderr.flush()
    except Exception:
        pass


def _door_base():
    raw = (os.environ.get("DOOR_URL") or "").strip()
    if not raw:
        return ""
    base = raw.rstrip("/")
    try:
        parts = urlparse(base)
        host = (parts.hostname or "").lower()
        scheme = (parts.scheme or "").lower()
    except Exception:
        return ""
    if not host:
        return ""
    if scheme == "https":
        return base
    # Loopback HTTP mailbox only — never a LAN/public http door.
    if scheme == "http" and host in ("127.0.0.1", "localhost", "::1"):
        return base
    return ""


def _muse_base():
    raw = (os.environ.get("MARC_MUSE_URL") or "http://127.0.0.1:8096").strip() or "http://127.0.0.1:8096"
    base = raw.rstrip("/")
    try:
        parts = urlparse(base)
        host = (parts.hostname or "").lower()
        scheme = (parts.scheme or "").lower()
    except Exception:
        return ""
    if scheme not in ("http", "https"):
        return ""
    # Loopback only — never talk to a non-loopback muse.
    if host not in ("127.0.0.1", "localhost", "::1"):
        return ""
    return base


def _auth_headers(token):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def _http_get_json(url, token, timeout):
    req = urllib.request.Request(url, method="GET", headers=_auth_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _http_post_json(url, payload, token, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=_auth_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _pull_job(door_base, token):
    try:
        data = _http_get_json(door_base + "/v1/pull", token, PULL_TIMEOUT)
    except Exception as exc:
        _eprint("bridge: pull failed: %s" % exc)
        return None
    if not isinstance(data, dict):
        return None
    # Some doors wrap the job: {"job": {...}} or return the job directly.
    if isinstance(data.get("job"), dict):
        return data["job"]
    return data


def _post_result(door_base, token, payload):
    try:
        _http_post_json(door_base + "/v1/result", payload, token, RESULT_TIMEOUT)
    except Exception as exc:
        _eprint("bridge: result post failed: %s" % exc)


def _handle_job(door_base, token, muse_base, job):
    job_id = job.get("id")
    text = job.get("text")
    if not job_id or not (isinstance(text, str) and text.strip()):
        return
    phone = job.get("phone") or job.get("session_id") or "phone"
    session_id = str(phone) if str(phone).strip() else "phone"
    # Mind proxy jobs from door (session_id whoami|mind|note).
    if session_id in ("whoami", "mind", "note"):
        try:
            if session_id == "whoami":
                muse_resp = _http_get_json(muse_base + "/whoami", token, MUSE_TIMEOUT)
            elif session_id == "mind":
                from urllib.parse import quote

                muse_resp = _http_get_json(
                    muse_base + "/mind?q=" + quote(str(text), safe=""),
                    token,
                    MUSE_TIMEOUT,
                )
            else:
                try:
                    note_payload = json.loads(text) if text.strip().startswith("{") else {"body": text}
                except Exception:
                    note_payload = {"body": text}
                if not isinstance(note_payload, dict):
                    note_payload = {"body": text}
                muse_resp = _http_post_json(muse_base + "/note", note_payload, token, MUSE_TIMEOUT)
        except Exception as exc:
            _eprint("bridge: mind proxy failed: %s" % exc)
            _post_result(door_base, token, {
                "id": job_id,
                "ok": False,
                "spoken": OFFLINE_SPOKEN,
                "reply": OFFLINE_SPOKEN,
                "text": OFFLINE_SPOKEN,
            })
            return
        if not isinstance(muse_resp, dict):
            muse_resp = {"ok": False, "text": MUSE_DOWN_SPOKEN}
        out = dict(muse_resp)
        out["id"] = job_id
        out.setdefault("ok", True)
        spoken = out.get("spoken") or out.get("text") or out.get("reply") or ""
        out.setdefault("spoken", spoken)
        out.setdefault("reply", spoken)
        _post_result(door_base, token, out)
        return
    muse_payload = {"text": text, "session_id": session_id, "target": "auto"}
    try:
        muse_resp = _http_post_json(muse_base + "/utterance", muse_payload, token, MUSE_TIMEOUT)
    except Exception as exc:
        _eprint("bridge: muse unreachable: %s" % exc)
        _post_result(door_base, token, {
            "id": job_id,
            "ok": False,
            "spoken": OFFLINE_SPOKEN,
            "reply": OFFLINE_SPOKEN,
            "phone_steps": [],
        })
        return
    if not isinstance(muse_resp, dict):
        _post_result(door_base, token, {
            "id": job_id,
            "ok": False,
            "spoken": MUSE_DOWN_SPOKEN,
            "reply": MUSE_DOWN_SPOKEN,
            "phone_steps": [],
        })
        return
    try:
        ok = muse_resp.get("ok", True)
        ok = bool(ok)
        reply = muse_resp.get("reply", "") or ""
        spoken = muse_resp.get("spoken", "") or reply or ""
        phone_steps = muse_resp.get("phone_steps", []) or []
        if not isinstance(phone_steps, list):
            phone_steps = []
        if not ok and not spoken:
            spoken = MUSE_DOWN_SPOKEN
        if not ok and not reply:
            reply = spoken
        _post_result(door_base, token, {
            "id": job_id,
            "ok": ok,
            "spoken": spoken,
            "phone_steps": phone_steps,
            "reply": reply,
        })
    except Exception as exc:
        _eprint("bridge: result build failed: %s" % exc)
        _post_result(door_base, token, {
            "id": job_id,
            "ok": False,
            "spoken": MUSE_DOWN_SPOKEN,
            "reply": MUSE_DOWN_SPOKEN,
            "phone_steps": [],
        })


def main():
    while True:
        token = (os.environ.get("MARC_TOKEN") or "").strip()
        door_base = _door_base()
        muse_base = _muse_base()
        if not door_base:
            _eprint("bridge: missing/invalid DOOR_URL (want https origin, no trailing slash)")
            time.sleep(5)
            continue
        if not muse_base:
            _eprint("bridge: missing/invalid MARC_MUSE_URL (want loopback http://127.0.0.1:8096)")
            time.sleep(5)
            continue
        if not token:
            _eprint("bridge: missing MARC_TOKEN")
            time.sleep(5)
            continue
        job = _pull_job(door_base, token)
        if job is None:
            time.sleep(2)
            continue
        if not isinstance(job, dict) or not job.get("id") or not job.get("text"):
            # No work right now (empty pull / heartbeat). Repull.
            # Small pause keeps us from hot-spinning on instant empty polls.
            time.sleep(1)
            continue
        _handle_job(door_base, token, muse_base, job)


if __name__ == "__main__":
    main()
