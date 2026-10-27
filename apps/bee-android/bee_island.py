"""Island status lines for bee (stdlib only). Max 40 chars, no Needle."""

from __future__ import annotations

STATES = ("idle", "listen", "plan", "wave", "confirm", "done", "fail")
ISLAND_MAX = 40


def clamp_line(value) -> str:
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    s = " ".join(s.split())
    if len(s) > ISLAND_MAX:
        s = s[:ISLAND_MAX]
    return s


def line_for(state: str, agents=None) -> str:
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
        parts = [str(a).strip() for a in seq if str(a).strip()]
        if not parts:
            return ""
        return clamp_line(" · ".join(parts))
    if state == "confirm":
        return "Say yes or cancel."
    if state == "done":
        return "Done."
    if state == "fail":
        return "Failed."
    return ""
