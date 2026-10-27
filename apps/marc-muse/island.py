"""Dynamic Island status bus — thread-safe snapshot (stdlib only)."""
from __future__ import annotations

import threading
import time

STATES = ("idle", "listen", "plan", "wave", "confirm", "done", "fail")

_MAX_LINE = 40

_lock = threading.RLock()
_state: str = "idle"
_line: str = ""
_agents: list[str] = []
_updated: float = time.time()


def _clamp_line(value) -> str:
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    # No newlines: collapse all whitespace (covers \n, \r, \t) + strip.
    s = " ".join(s.split())
    if len(s) > _MAX_LINE:
        s = s[:_MAX_LINE]
    return s


def line_for(state: str, agents=None) -> str:
    """Default one-liner for a state (always <= 40 chars)."""
    if state not in STATES:
        raise ValueError("unknown island state: %r" % (state,))
    if state == "idle":
        return ""
    if state == "listen":
        return "Listening…"
    if state == "plan":
        return "Planning…"
    if state == "wave":
        if not agents:
            return ""
        if isinstance(agents, str):
            seq = [agents]
        else:
            try:
                seq = list(agents)
            except TypeError:
                seq = [agents]
        parts = [str(a).strip() for a in seq]
        parts = [p for p in parts if p]
        if not parts:
            return ""
        return _clamp_line(" · ".join(parts))
    if state == "confirm":
        return "Say yes or cancel."
    if state == "done":
        return "Done."
    if state == "fail":
        return "Failed."
    return ""


def _coerce_agents(agents) -> list[str]:
    if isinstance(agents, str):
        return [agents.strip()] if agents.strip() else []
    out: list[str] = []
    for a in list(agents):
        s = a if isinstance(a, str) else str(a)
        s = s.strip()
        if s:
            out.append(s)
    return out


def reset() -> dict:
    """Reset bus to idle. Returns snapshot."""
    global _state, _line, _agents, _updated
    with _lock:
        _state = "idle"
        _line = ""
        _agents = []
        _updated = time.time()
        return {"state": _state, "line": _line, "agents": list(_agents), "updated": _updated}


def set_state(state: str, line=None, agents=None) -> dict:
    """Set island state. Clamps line to <=40 chars (strip, no newlines)."""
    global _state, _line, _agents, _updated
    if state not in STATES:
        raise ValueError("unknown island state: %r" % (state,))
    with _lock:
        if agents is not None:
            _agents = _coerce_agents(agents)
        if line is None:
            # Default line reflects effective agents for wave, statics otherwise.
            try:
                computed = line_for(state, list(_agents))
            except Exception:
                computed = line_for(state)
            _line = computed
        else:
            _line = _clamp_line(line)
        _state = state
        _updated = time.time()
        return {"state": _state, "line": _line, "agents": list(_agents), "updated": _updated}


def snapshot() -> dict:
    """Thread-safe copy: {state, line, agents (list of str), updated}."""
    with _lock:
        return {"state": _state, "line": _line, "agents": list(_agents), "updated": _updated}


def mark_fail(agent=None, line=None) -> dict:
    """Independent fail: state=fail but keep agents list (do not clear)."""
    global _state, _line, _updated
    with _lock:
        if agent is not None:
            s = agent if isinstance(agent, str) else str(agent)
            s = s.strip()
            if s and s not in _agents:
                _agents.append(s)
        if line is None:
            _line = line_for("fail")
        else:
            _line = _clamp_line(line)
        _state = "fail"
        _updated = time.time()
        return {"state": _state, "line": _line, "agents": list(_agents), "updated": _updated}


def apply_cycle(states) -> dict:
    """Test helper: apply a sequence of states, return final snapshot.

    Each entry may be a state str, a (state, line?, agents?) tuple/list,
    or a {state, line, agents} dict.
    """
    with _lock:
        pass
    items = list(states) if states is not None else []
    for item in items:
        if isinstance(item, dict):
            set_state(item.get("state", "idle"), line=item.get("line"), agents=item.get("agents"))
        elif isinstance(item, (list, tuple)):
            if len(item) == 0:
                continue
            st = item[0]
            ln = item[1] if len(item) > 1 else None
            ag = item[2] if len(item) > 2 else None
            set_state(st, line=ln, agents=ag)
        else:
            set_state(str(item))
    return snapshot()


__all__ = ["STATES", "reset", "set_state", "snapshot", "line_for", "mark_fail", "apply_cycle"]
