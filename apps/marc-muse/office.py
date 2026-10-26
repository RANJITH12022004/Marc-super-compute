"""Office Muse runner — file-backed task hops (stdlib only).

- start_task(goal, workdir='./var/office') writes the office md under
  *workdir* and mirrors it into mind sessions (office md).
- continue_task(task_id, note) appends a hop, respecting the hop cap.
- stop_task(task_id) marks the task stopped via planner.set_stopped().
- Uses meta_client.complete with muse-spark when MODEL_API_KEY is set,
  otherwise records a sandbox plan file (no network, nothing sent).
- Hop cap from MARC_PLAN_MAX_HOPS (fallback MARC_MAX_HOPS / MAX_HOPS).
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import planner  # type: ignore
except Exception:
    planner = None  # type: ignore

try:
    import meta_client  # type: ignore
except Exception:
    meta_client = None  # type: ignore

try:
    import sessions as _sessions  # type: ignore
except Exception:
    _sessions = None  # type: ignore

DEFAULT_WORKDIR = "./var/office"
DEFAULT_MODEL = "muse-spark"

_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def write_file(path, text: str) -> Path:
    """Atomically write *text* to *path* (tmp + os.replace)."""
    target = Path(path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / ("%s.%d.tmp" % (target.name, os.getpid()))
    counter = 0
    candidate = tmp
    while candidate.exists():
        counter += 1
        candidate = parent / ("%s.%d.%d.tmp" % (target.name, os.getpid(), counter))
    tmp = candidate
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, target)
    return target


def _hop_cap() -> int:
    """Return hop cap from MARC_PLAN_MAX_HOPS (fallback MARC_MAX_HOPS)."""
    for name in ("MARC_PLAN_MAX_HOPS", "MARC_MAX_HOPS", "MAX_HOPS"):
        raw = os.environ.get(name)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            value = int(str(raw).strip())
        except ValueError:
            continue
        if value < 0:
            value = 0
        return value
    return 8


def _mind_dir() -> Path:
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path((raw or "").strip() or "./var/mind")


def _now_iso() -> str:
    try:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _safe_id(raw: str) -> str:
    cleaned = _SAFE_RE.sub("_", str(raw or "").strip()).strip("_")
    if not cleaned:
        cleaned = "task"
    return cleaned[:120]


def _new_task_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return "office-%s-%s" % (stamp, suffix)


def _workdir_path(workdir) -> Path:
    base = str(workdir or DEFAULT_WORKDIR).strip() or DEFAULT_WORKDIR
    return Path(base)


def _task_path(task_id: str, workdir) -> Path:
    return _workdir_path(workdir) / ("%s.md" % _safe_id(task_id))


def _model_key() -> tuple[str, str]:
    key = (os.environ.get("MODEL_API_KEY") or "").strip()
    model = (os.environ.get("MARC_SPARK_MODEL") or "").strip() or DEFAULT_MODEL
    if "muse-spark" not in model:
        model = DEFAULT_MODEL
    return key, model


def _spark_text(prompt: str):
    """Call meta_client.complete with muse-spark. Returns text or None."""
    key, model = _model_key()
    if not key or key == "LLM_...":
        return None
    mod = globals().get("meta_client")
    if mod is None:
        return None
    complete = getattr(mod, "complete", None)
    if not callable(complete):
        return None
    instructions = (
        "Office task runner. Produce a short stepwise plan for the goal. "
        "Never send mail or messages; drafts only."
    )
    try:
        result = complete(key, model, instructions, str(prompt or ""))
    except TypeError:
        try:
            result = complete(key=key, model=model, instructions=instructions, input=str(prompt or ""))
        except Exception:
            return None
    except Exception:
        return None
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None
    if isinstance(result, str) and result.strip():
        return result.strip()
    return None


def _parse_hops(text: str) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("- [hop"):
            out.append(s)
    return out


def _parse_field(text: str, field: str) -> str:
    for line in (text or "").splitlines():
        s = line.strip()
        prefix = field + ":"
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return ""


def _render_task(task_id: str, goal: str, status: str, hops: list[str], cap: int, mode: str) -> str:
    now = _now_iso()
    lines = ["# Office task %s" % task_id, ""]
    lines.append("Goal: %s" % _one_line(goal)[:500])
    lines.append("Status: %s" % _one_line(status))
    lines.append("Hops: %d / %d" % (len(hops), cap))
    lines.append("Mode: %s" % _one_line(mode))
    lines.append("Id: %s" % task_id)
    lines.append("Updated: %s" % now)
    lines.append("")
    lines.append("## Hops")
    lines.append("")
    if hops:
        for h in hops:
            lines.append(h)
    else:
        lines.append("- (no hops yet)")
    lines.append("")
    return "\n".join(lines)


def _record_mind_session(task_id: str, goal: str, status: str, hops: list[str], mode: str) -> None:
    sid = "office-%s" % _safe_id(task_id)
    payload = {
        "id": sid,
        "office_task": task_id,
        "goal": _one_line(goal)[:500],
        "status": status,
        "mode": mode,
        "hops": list(hops),
        "reply": _one_line(goal)[:300] if goal else "office task",
        "updated": _now_iso(),
    }
    mod = globals().get("_sessions")
    if mod is not None:
        save = getattr(mod, "save_session", None)
        if callable(save):
            try:
                save(sid, payload)
                return
            except Exception:
                pass
    try:
        base = _mind_dir()
        path = base / "sessions" / ("%s.md" % _safe_id(sid))
        lines = ["# Session %s" % sid, ""]
        lines.append("- Updated: %s" % _now_iso())
        lines.append("- ID: %s" % sid)
        lines.append("- Office: %s" % _one_line(goal)[:300])
        lines.append("- Status: %s" % _one_line(status))
        lines.append("")
        lines.append("## Hops")
        lines.append("")
        for h in hops:
            lines.append(h if h.startswith("-") else "- %s" % h)
        if not hops:
            lines.append("- (no hops yet)")
        lines.append("")
        write_file(path, "\n".join(lines))
    except Exception:
        pass


def _find_task_file(task_id, workdir):
    sid = _safe_id(task_id)
    candidates: list[Path] = []
    for base in (_workdir_path(workdir), Path(DEFAULT_WORKDIR)):
        candidates.append(base / ("%s.md" % sid))
        if not sid.startswith("office-"):
            candidates.append(base / ("office-%s.md" % sid))
    # Mind sessions mirror as a last resort.
    try:
        candidates.append(_mind_dir() / "sessions" / ("office-%s.md" % sid))
        candidates.append(_mind_dir() / "sessions" / ("%s.md" % sid))
    except Exception:
        pass
    for path in candidates:
        try:
            if path.is_file():
                return path
        except Exception:
            continue
    return candidates[0] if candidates else _task_path(task_id, workdir)


def start_task(goal, workdir=DEFAULT_WORKDIR) -> dict:
    """Start an office task; write office md + mind sessions office md."""
    cap = _hop_cap()
    goal_text = _one_line(goal)
    task_id = _new_task_id()
    key = (os.environ.get("MODEL_API_KEY") or "").strip()
    hops: list[str] = []
    if key and key != "LLM_...":
        mode = "spark"
        spark = _spark_text(goal_text or "office task")
        if spark:
            hops.append("- [hop 0 %s] spark: %s" % (_now_iso(), _one_line(spark)[:500]))
        else:
            hops.append("- [hop 0 %s] goal: %s" % (_now_iso(), goal_text[:500] or "office task"))
    else:
        mode = "sandbox"
        hops.append(
            "- [hop 0 %s] sandbox plan for: %s (no MODEL_API_KEY — nothing sent)"
            % (_now_iso(), goal_text[:400] or "office task")
        )
    # Enforce hop cap on the initial write as well.
    hops = hops[: max(cap, 0)] if cap == 0 else hops[:cap] if len(hops) > cap else hops
    if cap == 0:
        hops = []
    text = _render_task(task_id, goal_text, "open", hops, cap, mode)
    path = _task_path(task_id, workdir)
    write_file(path, text)
    try:
        _record_mind_session(task_id, goal_text, "open", hops, mode)
    except Exception:
        pass
    return {
        "ok": True,
        "id": task_id,
        "goal": goal_text,
        "path": str(path),
        "mode": mode,
        "status": "open",
        "hops": list(hops),
        "max_hops": cap,
    }


def continue_task(task_id, note, workdir=DEFAULT_WORKDIR) -> dict:
    """Append *note* as the next hop unless MARC_PLAN_MAX_HOPS is reached."""
    cap = _hop_cap()
    sid = str(task_id or "").strip()
    note_text = _one_line(note)
    path = _find_task_file(sid, workdir)
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        existing = ""
    hops = _parse_hops(existing)
    goal = _parse_field(existing, "Goal") or sid
    status = _parse_field(existing, "Status") or "open"
    mode = _parse_field(existing, "Mode") or "sandbox"
    if status.strip().lower() == "stopped":
        return {"ok": False, "id": sid, "error": "stopped", "path": str(path), "hops": hops}
    if len(hops) >= cap:
        return {
            "ok": False,
            "id": sid,
            "error": "hop cap reached",
            "path": str(path),
            "hops": hops,
            "max_hops": cap,
        }
    key = (os.environ.get("MODEL_API_KEY") or "").strip()
    if key and key != "LLM_...":
        mode = "spark"
        spark = _spark_text("task %s goal %s note %s" % (sid, goal, note_text))
        body = _one_line(spark)[:500] if spark else note_text
        hops.append("- [hop %d %s] spark: %s" % (len(hops), _now_iso(), body or note_text or "continue"))
    else:
        mode = "sandbox" if mode != "spark" else mode
        hops.append("- [hop %d %s] %s" % (len(hops), _now_iso(), note_text or "continue"))
    text = _render_task(sid, goal, status or "open", hops, cap, mode)
    write_file(path, text)
    try:
        _record_mind_session(sid, goal, status or "open", hops, mode)
    except Exception:
        pass
    return {
        "ok": True,
        "id": sid,
        "note": note_text,
        "path": str(path),
        "mode": mode,
        "status": status or "open",
        "hops": list(hops),
        "max_hops": cap,
    }


def stop_task(task_id, workdir=DEFAULT_WORKDIR) -> dict:
    """Mark the task stopped and signal the planner via set_stopped."""
    try:
        mod = globals().get("planner")
        setter = getattr(mod, "set_stopped", None) if mod is not None else None
        if callable(setter):
            setter()
    except Exception:
        pass
    sid = str(task_id or "").strip()
    cap = _hop_cap()
    path = _find_task_file(sid, workdir)
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        existing = ""
    hops = _parse_hops(existing)
    goal = _parse_field(existing, "Goal") or sid
    mode = _parse_field(existing, "Mode") or "sandbox"
    hops.append("- [hop %d %s] stopped" % (len(hops), _now_iso()))
    text = _render_task(sid, goal, "stopped", hops, cap, mode)
    try:
        write_file(path, text)
    except Exception:
        pass
    try:
        _record_mind_session(sid, goal, "stopped", hops, mode)
    except Exception:
        pass
    return {"ok": True, "id": sid, "stopped": True, "path": str(path), "status": "stopped"}


__all__ = ["write_file", "start_task", "continue_task", "stop_task", "DEFAULT_WORKDIR"]
