"""Ephemeral DAG agent wrappers (stdlib only, no network).

Maps plan tools to lightweight agent names and exposes helpers to
visualise / continue parallel waves.

Agent mapping:
  mail_compose/mail_send/mail_search/mail_summarize -> mail
  whatsapp_send/whatsapp_prefill                   -> whatsapp
  dial                                              -> dial
  play_music/media_key                              -> music
  open_app/close_app/type_into/google_search/
    youtube_search (+ any other tool)               -> laptop if device==laptop else phone
"""

from __future__ import annotations

__all__ = [
    "agent_name",
    "agent_for",
    "spawn",
    "waves",
    "wave_line",
    "fail_independent",
]

_MAIL_TOOLS = frozenset(
    {"mail_compose", "mail_send", "mail_search", "mail_summarize"}
)
_WHATSAPP_TOOLS = frozenset({"whatsapp_send", "whatsapp_prefill"})
_DIAL_TOOLS = frozenset({"dial"})
_MUSIC_TOOLS = frozenset({"play_music", "media_key"})

_MIDDLE_DOT = " \u00b7 "


def _norm_tool(tool) -> str:
    try:
        return str(tool or "").strip().lower()
    except Exception:
        return ""


def _norm_device(device) -> str:
    try:
        return str(device or "").strip().lower()
    except Exception:
        return ""


def agent_name(tool, device=None) -> str:
    """Return the ephemeral agent name for a tool/device pair."""
    t = _norm_tool(tool)
    if t in _MAIL_TOOLS:
        return "mail"
    if t in _WHATSAPP_TOOLS:
        return "whatsapp"
    if t in _DIAL_TOOLS:
        return "dial"
    if t in _MUSIC_TOOLS:
        return "music"
    if _norm_device(device) == "laptop":
        return "laptop"
    return "phone"


def agent_for(tool, device=None) -> str:
    """Alias for :func:`agent_name`."""
    return agent_name(tool, device)


def spawn(plan) -> list:
    """Expand a plan into ephemeral agents.

    Returns a list of {id, name, device, tool, confirm, after}.
    """
    if not isinstance(plan, list):
        return []
    out: list = []
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        sid = step.get("id")
        if not isinstance(sid, str) or not sid:
            sid = "s%d" % (i + 1)
        tool = step.get("tool")
        if not isinstance(tool, str):
            try:
                tool = str(tool) if tool is not None else ""
            except Exception:
                tool = ""
        device = step.get("device")
        if not isinstance(device, str) or not device.strip():
            device = "phone"
        after = step.get("after")
        if isinstance(after, list):
            after_copy = [a for a in after if isinstance(a, str) and a]
        else:
            after_copy = []
        out.append(
            {
                "id": sid,
                "name": agent_name(tool, device),
                "device": device,
                "tool": tool,
                "confirm": bool(step.get("confirm", False)),
                "after": after_copy,
            }
        )
    return out


def _fallback_waves(plan) -> list:
    """Local Kahn walk: empty-after steps first, dependents later."""
    ids: list = []
    deps: dict = {}
    for step in plan:
        if not isinstance(step, dict):
            continue
        sid = step.get("id")
        if not isinstance(sid, str) or not sid:
            continue
        if sid in deps:
            continue
        ids.append(sid)
        after = step.get("after") or []
        if not isinstance(after, list):
            after = []
        deps[sid] = [d for d in after if isinstance(d, str)]
    if not ids:
        return []
    known = set(ids)
    # Unknown deps are treated as already satisfied (never deadlock).
    normed = {
        sid: [d for d in (deps.get(sid) or []) if d in known] for sid in ids
    }
    waves_out: list = []
    done: set = set()
    remaining = set(ids)
    order = list(ids)
    while remaining:
        wave = [
            sid
            for sid in order
            if sid in remaining and all(d in done for d in normed[sid])
        ]
        if not wave:
            # Cycle or unresolvable: flush remainder as one wave to avoid loss.
            wave = [sid for sid in order if sid in remaining]
            waves_out.append(wave)
            break
        waves_out.append(wave)
        done.update(wave)
        remaining.difference_update(wave)
    return waves_out


def waves(plan) -> list:
    """Group plan step ids into parallel waves.

    Uses dag.topological_waves when importable, else falls back to a
    local grouping with empty-after steps as wave 0 and dependents later.
    """
    if not isinstance(plan, list) or not plan:
        return []
    try:
        import dag as _dag  # type: ignore

        fn = getattr(_dag, "topological_waves", None)
        if callable(fn):
            result = fn(plan)
            if isinstance(result, list):
                return [list(w) for w in result if isinstance(w, list)]
    except Exception:
        pass
    try:
        return _fallback_waves(plan)
    except Exception:
        return []


def _coerce_name(value) -> str:
    if isinstance(value, dict):
        for key in ("name", "agent", "tool", "id"):
            try:
                v = value.get(key)
            except Exception:
                v = None
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    try:
        s = str(value) if value is not None else ""
    except Exception:
        return ""
    return s.strip()


def wave_line(names) -> str:
    """Join agent names with a middle-dot, capped at 40 chars."""
    if isinstance(names, str):
        s = names.strip()
        if len(s) <= 40:
            return s
        return s[:37] + "..."
    if not isinstance(names, (list, tuple)):
        return ""
    parts = []
    for item in names:
        s = _coerce_name(item)
        if s:
            parts.append(s)
    if not parts:
        return ""
    joined = _MIDDLE_DOT.join(parts)
    if len(joined) <= 40:
        return joined
    return joined[:37] + "..."


def fail_independent(plan, failed_id) -> list:
    """Return steps that can continue despite *failed_id* failing.

    Keeps every step whose id != failed_id and whose after[] does not
    directly include failed_id.
    """
    if not isinstance(plan, list):
        return []
    out: list = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        sid = step.get("id")
        if sid == failed_id:
            continue
        after = step.get("after") or []
        if not isinstance(after, list):
            # Non-list after cannot name the failed dep; keep the step.
            out.append(step)
            continue
        if failed_id in after:
            continue
        out.append(step)
    return out
