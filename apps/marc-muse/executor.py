"""marc-muse executor — sandbox-safe DAG runner (stdlib only).

Never sends mail / WhatsApp / external messages. Send/confirm tools
become drafts. Walks ``dag.ready_steps`` when available, otherwise a
local ``after``-dependency walk. Respects hop caps and stop/pause
signals, then persists reply + remaining followups via ``sessions``
when available (always also writes a local session file).
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_FALLBACK_SEND_TOOLS = {
    "mail_send",
    "mail_compose",
    "whatsapp_send",
    "instagram_send",
    "sms_send",
    "calendar_create",
    "dial",
}


def _int_env(names, default):
    for name in names:
        raw = os.environ.get(name)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            return int(str(raw).strip())
        except ValueError:
            continue
    return default


def get_hop_limits():
    """Return (max_hops, hard_hops) from env with defaults 8/14."""
    max_hops = _int_env(
        ["MARC_PLAN_MAX_HOPS", "MARC_MAX_HOPS", "MAX_HOPS"], 8
    )
    hard_hops = _int_env(
        ["MARC_PLAN_HARD_HOPS", "MARC_HARD_HOPS", "HARD_HOPS"], 14
    )
    try:
        max_hops = int(max_hops)
    except Exception:
        max_hops = 8
    try:
        hard_hops = int(hard_hops)
    except Exception:
        hard_hops = 14
    if max_hops < 0:
        max_hops = 0
    if hard_hops < 0:
        hard_hops = 0
    return max_hops, hard_hops


def get_hops():
    mx, hd = get_hop_limits()
    return {"max_hops": mx, "hard_hops": hd}


def _mind_dir():
    try:
        import config as _cfg  # type: ignore

        if hasattr(_cfg, "load_settings"):
            try:
                return Path(_cfg.load_settings().mind_dir)
            except Exception:
                pass
    except Exception:
        pass
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path(raw)


def _mode():
    try:
        import planner as _planner  # type: ignore

        if hasattr(_planner, "get_mode"):
            try:
                return _planner.get_mode()
            except Exception:
                pass
    except Exception:
        pass
    return (os.environ.get("MARC_MODE") or "sandbox").strip().lower() or "sandbox"


def _is_stopped():
    try:
        import planner as _planner  # type: ignore

        if hasattr(_planner, "is_stopped"):
            try:
                return bool(_planner.is_stopped())
            except Exception:
                pass
    except Exception:
        pass
    return False


def _is_paused():
    try:
        import credit as _credit  # type: ignore

        if hasattr(_credit, "paused"):
            try:
                return bool(_credit.paused())
            except Exception:
                pass
    except Exception:
        pass
    try:
        import planner as _planner  # type: ignore

        if hasattr(_planner, "is_paused"):
            try:
                return bool(_planner.is_paused())
            except Exception:
                pass
    except Exception:
        pass
    return False


def _send_tools():
    try:
        import planner as _planner  # type: ignore

        st = getattr(_planner, "SEND_TOOLS", None)
        if isinstance(st, (set, list, tuple, frozenset)):
            return set(st)
    except Exception:
        pass
    return set(_FALLBACK_SEND_TOOLS)


def _confirm_tools():
    try:
        import planner as _planner  # type: ignore

        if hasattr(_planner, "get_confirm_tools"):
            try:
                ct = _planner.get_confirm_tools()
                if isinstance(ct, (set, list, tuple, frozenset)):
                    return set(ct)
            except Exception:
                pass
    except Exception:
        pass
    return set()


def _ready_local(pending_steps, done_ids):
    ready = []
    for step in pending_steps:
        after = step.get("after") or []
        if not isinstance(after, list):
            after = [after]
        ok = True
        for dep in after:
            if dep in done_ids:
                continue
            # Unknown dep ids are treated as satisfied so we never deadlock
            # on plans that reference already-completed history.
            still_pending = any(s.get("id") == dep for s in pending_steps)
            if still_pending and dep not in done_ids:
                ok = False
                break
        if ok:
            ready.append(step)
    return ready


def _ready_steps(pending_steps, done_ids):
    try:
        import dag as _dag  # type: ignore

        fn = getattr(_dag, "ready_steps", None)
        if callable(fn):
            try:
                out = fn(pending_steps, done_ids)
                if isinstance(out, list):
                    return out
            except TypeError:
                pass
            try:
                out = fn(pending_steps, list(done_ids))
                if isinstance(out, list):
                    return out
            except Exception:
                pass
            try:
                out = fn({"plan": pending_steps}, done_ids)
                if isinstance(out, list):
                    return out
            except Exception:
                pass
    except Exception:
        pass
    return _ready_local(pending_steps, done_ids)


def _save_draft_local(mind_dir, step_id, session_id, step):
    drafts_dir = Path(mind_dir) / "drafts"
    try:
        drafts_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    tool = (step.get("tool") or "")
    args = step.get("args") or {}
    body_lines = [
        "# draft %s" % step_id,
        "",
        "session: %s" % session_id,
        "tool: %s" % tool,
        "status: draft",
        "",
        "```json",
        json.dumps({"id": step_id, "tool": tool, "args": args}, indent=2),
        "```",
        "",
        "Nothing was sent. Confirm to release.",
    ]
    path = drafts_dir / ("%s.md" % step_id)
    try:
        path.write_text("\n".join(body_lines) + "\n", encoding="utf-8")
    except Exception:
        pass
    return str(path)


def _enqueue_draft(session_id, step, mind_dir):
    step_id = step.get("id") or "s1"
    # Prefer a real drafts module when present.
    try:
        import drafts as _drafts  # type: ignore

        fn = getattr(_drafts, "enqueue", None)
        if callable(fn):
            # Try most likely signatures.
            for attempt in (
                lambda: fn(session_id, step),
                lambda: fn(step, session_id),
                lambda: fn(step),
                lambda: fn(
                    {"id": step_id, "session_id": session_id,
                     "tool": step.get("tool"), "args": step.get("args") or {}}
                ),
            ):
                try:
                    res = attempt()
                    return res
                except TypeError:
                    continue
                except Exception:
                    break
    except Exception:
        pass
    # Fallback: local helper — record status='draft' + markdown file.
    # Also try sessions helper for writing if it exposes one.
    try:
        import sessions as _sessions  # type: ignore

        for attr in ("write_draft", "save_draft", "enqueue_draft"):
            fn2 = getattr(_sessions, attr, None)
            if callable(fn2):
                try:
                    fn2(session_id, step)
                    break
                except Exception:
                    continue
    except Exception:
        pass
    return _save_draft_local(mind_dir, step_id, session_id, step)


def _run_step(step, session_id, mind_dir, mode, send_tools, confirm_tools):
    sid = step.get("id") or "s1"
    tool = (step.get("tool") or "type_into")
    args = dict(step.get("args") or {})
    confirm = bool(step.get("confirm", False))
    is_send = tool in send_tools
    sandbox = (mode or "sandbox") == "sandbox"
    needs_draft = bool(is_send or args.get("draft") is True or (sandbox and (confirm or tool in confirm_tools)))
    # Never actually send mail/WA-family tools even in live mode.
    if tool in _FALLBACK_SEND_TOOLS:
        needs_draft = True
    if needs_draft:
        args = dict(args)
        args["draft"] = True
        try:
            _enqueue_draft(session_id, {**step, "args": args}, mind_dir)
        except Exception:
            pass
        label = args.get("to") or args.get("contact") or args.get("title") or ""
        out = "draft %s saved%s — nothing sent." % (
            tool, (" to %s" % label) if label else ""
        )
        return {"id": sid, "ok": True, "output": out, "status": "draft",
                "tool": tool, "draft": True}
    # Sandbox-safe simulated execution for everything else.
    try:
        if tool == "open_app" and args.get("label"):
            out = "Opened %s (simulated)." % args["label"]
        elif tool == "google_search":
            out = "Searched Google for '%s' (simulated)." % (args.get("query") or "")
        elif tool == "youtube_search":
            out = "Searched YouTube for '%s' (simulated)." % (args.get("query") or "")
        elif tool == "play_music":
            out = "Playing '%s' (simulated)." % (args.get("query") or "")
        elif tool in ("server_status", "service_status", "docker_list"):
            out = "%s checked (simulated)." % tool
        elif tool in ("service_restart", "docker_restart"):
            out = "%s queued (simulated, no-op in sandbox)." % tool
        elif tool == "type_into":
            out = "Typed '%s' (simulated)." % (args.get("text") or "")
        elif tool in ("mind_note", "mind_recall"):
            out = "%s recorded (simulated)." % tool
        elif tool in ("open_url", "close_app", "camera_action", "open_food_search"):
            out = "%s done (simulated)." % tool
        else:
            out = "%s done (simulated)." % tool
        return {"id": sid, "ok": True, "output": out, "status": "done", "tool": tool}
    except Exception as exc:
        return {"id": sid, "ok": False, "output": "error: %s" % exc,
                "status": "error", "tool": tool}


def _persist_session(session_id, reply, remaining, results=None):
    # Try real sessions module first (multiple signature attempts).
    try:
        import sessions as _sessions  # type: ignore

        set_last = getattr(_sessions, "set_last", None)
        if callable(set_last):
            for attempt in (
                lambda: set_last(session_id, reply),
                lambda: set_last(reply, session_id),
                lambda: set_last(reply),
            ):
                try:
                    attempt()
                    break
                except TypeError:
                    continue
                except Exception:
                    break
        save_fn = getattr(_sessions, "save_session", None)
        if callable(save_fn):
            followups = [s for s in (remaining or [])
                         if isinstance(s, dict) and s.get("kind") == "followup"]
            payload_followups = followups if followups else (remaining or [])
            for attempt in (
                lambda: save_fn(session_id, reply, payload_followups),
                lambda: save_fn(session_id, {"reply": reply,
                                             "followups": payload_followups,
                                             "results": results or []}),
                lambda: save_fn({"session_id": session_id, "reply": reply,
                                 "followups": payload_followups}),
            ):
                try:
                    attempt()
                    break
                except TypeError:
                    continue
                except Exception:
                    break
    except Exception:
        pass
    # Always keep a local session file so state survives without the module.
    try:
        mind = _mind_dir()
        sdir = Path(mind) / "sessions"
        sdir.mkdir(parents=True, exist_ok=True)
        followups = [s for s in (remaining or [])
                     if isinstance(s, dict) and s.get("kind") == "followup"]
        doc = {
            "session_id": session_id,
            "reply": reply,
            "followups": followups if followups else (remaining or []),
            "remaining": remaining or [],
            "results": results or [],
        }
        (sdir / ("%s.json" % session_id)).write_text(
            json.dumps(doc, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def execute_plan(plan, session_id=None):
    """Walk plan DAG, execute sandbox-safe, persist session. Returns dict."""
    if isinstance(plan, list):
        steps = list(plan)
        reply0 = ""
        sid = (session_id or "phone").strip() or "phone"
    elif isinstance(plan, dict):
        raw_steps = plan.get("plan") or []
        steps = list(raw_steps) if isinstance(raw_steps, list) else []
        reply0 = plan.get("reply") or ""
        sid = (plan.get("session_id") or session_id or "phone").strip() or "phone"
    else:
        steps = []
        reply0 = ""
        sid = (session_id or "phone").strip() or "phone"

    # Normalize steps: ensure ids.
    normed = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        c = dict(s)
        if not c.get("id"):
            c["id"] = "s%d" % (i + 1)
        if not isinstance(c.get("after"), list):
            c["after"] = list(c["after"]) if c.get("after") else []
        normed.append(c)
    steps = normed

    max_hops, hard_hops = get_hop_limits()
    limit = min(max_hops, hard_hops)

    mind = _mind_dir()
    mode = _mode()
    send_tools = _send_tools()
    confirm_tools = _confirm_tools()

    done = set()
    results = []
    stopped = False
    paused = False

    # Pre-check signals before any hop.
    if _is_stopped():
        stopped = True
    elif _is_paused():
        paused = True

    if not stopped and not paused and limit > 0:
        # Index for quick lookup; preserve order.
        while len(results) < limit:
            if _is_stopped():
                stopped = True
                break
            if _is_paused():
                paused = True
                break
            pending = [s for s in steps if s.get("id") not in done]
            if not pending:
                break
            ready = _ready_steps(pending, set(done))
            if not ready:
                break
            progressed = False
            for step in ready:
                if len(results) >= limit:
                    break
                if _is_stopped():
                    stopped = True
                    break
                if _is_paused():
                    paused = True
                    break
                res = _run_step(step, sid, mind, mode, send_tools, confirm_tools)
                results.append(res)
                done.add(step.get("id"))
                progressed = True
            if not progressed:
                break
    elif limit <= 0:
        # Hop cap of zero: nothing runs, but still persist below.
        pass

    remaining = [s for s in steps if s.get("id") not in done]
    if stopped:
        reply = "Muse isn't running."
    elif paused:
        reply = "Muse budget paused."
    elif reply0:
        reply = reply0
    elif results:
        drafts = sum(1 for r in results if r.get("status") == "draft")
        if drafts:
            reply = "Done — %d step(s), %d draft(s). Nothing sent." % (len(results), drafts)
        else:
            reply = "Done — %d step(s)." % len(results)
    else:
        reply = "Got it — nothing to do yet."

    try:
        _persist_session(sid, reply, remaining, results)
    except Exception:
        pass

    return {
        "ok": True,
        "session_id": sid,
        "reply": reply,
        "results": results,
        "remaining": remaining,
        "followups": [s for s in remaining
                      if isinstance(s, dict) and s.get("kind") == "followup"],
        "stopped": bool(stopped),
        "paused": bool(paused),
        "max_hops": max_hops,
        "hard_hops": hard_hops,
    }


# Alias for convenience.
execute = execute_plan


__all__ = ["execute_plan", "execute", "get_hop_limits", "get_hops"]
