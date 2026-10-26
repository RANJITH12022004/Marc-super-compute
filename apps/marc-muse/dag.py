"""DAG scheduler for muse plans (stdlib only, no network).

Plan step contract (see planner.py):
    {id, after, kind, device, tool, args, confirm}

Functions:
    validate_plan(plan) -> list of error strings
    ready_steps(plan, done_ids, failed_ids) -> runnable step dicts
    topological_waves(plan) -> parallel waves of step ids
    hop_budget(kind, args, max_hops=8, hard_hops=14) -> int
    should_stop(stopped_flag, hops_used, hard_hops) -> bool
"""

from __future__ import annotations

VALID_KINDS = ("once", "repeat", "followup", "iterate")
VALID_DEVICES = ("phone", "laptop", "server")

__all__ = [
    "VALID_KINDS",
    "VALID_DEVICES",
    "validate_plan",
    "ready_steps",
    "topological_waves",
    "hop_budget",
    "should_stop",
]


def validate_plan(plan) -> list:
    """Return a list of error strings; empty list means the plan is valid."""
    errors = []
    if not isinstance(plan, list):
        return ["plan must be a list"]
    valid_kinds = set(VALID_KINDS)
    valid_devices = set(VALID_DEVICES)

    seen = set()
    ids = set()
    # First pass: collect ids to allow forward references.
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        sid = step.get("id")
        if isinstance(sid, str) and sid.strip():
            ids.add(sid)

    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            errors.append("step %d: must be an object" % i)
            continue
        sid = step.get("id")
        label = sid if isinstance(sid, str) and sid else "#%d" % i

        # id
        if not isinstance(sid, str) or not sid.strip():
            errors.append("step %d: missing/invalid id" % i)
        elif sid in seen:
            errors.append("duplicate step id '%s'" % sid)
        else:
            seen.add(sid)

        # after
        if "after" not in step:
            errors.append("step '%s': missing after" % label)
        elif not isinstance(step.get("after"), list):
            errors.append("step '%s': after must be a list" % label)
        else:
            for dep in step["after"]:
                if not isinstance(dep, str) or not dep:
                    errors.append("step '%s': after entry must be a step id string" % label)
                elif dep == sid:
                    errors.append("step '%s': after must not reference itself" % label)
                elif dep not in ids:
                    errors.append("step '%s': unknown after dependency '%s'" % (label, dep))

        # kind
        kind = step.get("kind")
        if kind not in valid_kinds:
            errors.append(
                "step '%s': kind must be one of %s" % (label, "|".join(VALID_KINDS))
            )

        # device
        device = step.get("device")
        if device not in valid_devices:
            errors.append(
                "step '%s': device must be one of %s" % (label, "|".join(VALID_DEVICES))
            )

        # tool
        tool = step.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            errors.append("step '%s': tool must be a non-empty string" % label)

        # args
        if "args" not in step:
            errors.append("step '%s': missing args" % label)
        elif not isinstance(step.get("args"), dict):
            errors.append("step '%s': args must be a dict" % label)

        # confirm
        if "confirm" not in step:
            errors.append("step '%s': missing confirm" % label)
        elif not isinstance(step.get("confirm"), bool):
            errors.append("step '%s': confirm must be a bool" % label)

    # Cycle detection (only if ids are otherwise sane).
    if plan and all(isinstance(s, dict) for s in plan):
        try:
            topological_waves(plan)
        except ValueError as exc:
            msg = str(exc)
            if "cycle" in msg.lower():
                errors.append("plan contains a cycle: %s" % msg)

    return errors


def _as_set(value) -> set:
    if value is None:
        return set()
    if isinstance(value, (set, frozenset)):
        return set(value)
    if isinstance(value, dict):
        return set(value.keys())
    try:
        return set(value)
    except TypeError:
        return set()


def ready_steps(plan, done_ids=None, failed_ids=None) -> list:
    """Return step dicts whose deps are all done and none failed.

    A step is ready when:
      - its own id is not in done_ids nor failed_ids, and
      - every entry in after[] is in done_ids, and
      - no entry in after[] is in failed_ids.
    """
    if not isinstance(plan, list):
        return []
    done = _as_set(done_ids)
    failed = _as_set(failed_ids)
    out = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        sid = step.get("id")
        if sid in done or sid in failed:
            continue
        after = step.get("after") or []
        if not isinstance(after, list):
            continue
        if any(dep in failed for dep in after):
            continue
        if all(dep in done for dep in after):
            out.append(step)
    return out


def topological_waves(plan) -> list:
    """Group step ids into parallel waves (Kahn's algorithm, stable order).

    Raises ValueError on duplicate ids, unknown dependencies, or cycles.
    """
    if plan is None:
        return []
    if not isinstance(plan, list):
        raise ValueError("plan must be a list")
    if not plan:
        return []

    order = []
    steps = {}
    for step in plan:
        if not isinstance(step, dict):
            raise ValueError("each step must be an object")
        sid = step.get("id")
        if not isinstance(sid, str) or not sid:
            raise ValueError("each step needs a non-empty string id")
        if sid in steps:
            raise ValueError("duplicate step id '%s'" % sid)
        steps[sid] = step
        order.append(sid)

    deps = {}
    for sid in order:
        after = steps[sid].get("after") or []
        if not isinstance(after, list):
            raise ValueError("step '%s': after must be a list" % sid)
        for dep in after:
            if dep not in steps:
                raise ValueError(
                    "step '%s': unknown after dependency '%s'" % (sid, dep)
                )
        deps[sid] = list(after)

    waves = []
    done = set()
    remaining = set(order)
    while remaining:
        wave = [sid for sid in order if sid in remaining and all(
            d in done for d in deps[sid]
        )]
        if not wave:
            raise ValueError(
                "cycle detected among: %s" % sorted(remaining)
            )
        waves.append(wave)
        done.update(wave)
        remaining.difference_update(wave)
    return waves


def _to_int(value, fallback):
    try:
        if isinstance(value, bool):
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def hop_budget(kind, args=None, max_hops=8, hard_hops=14) -> int:
    """Return the hop budget for a step kind, clamped to hard_hops."""
    max_hops = _to_int(max_hops, 8)
    hard_hops = _to_int(hard_hops, 14)
    if hard_hops < 0:
        hard_hops = 0
    if max_hops < 0:
        max_hops = 0
    if max_hops > hard_hops:
        max_hops = hard_hops

    if not isinstance(args, dict):
        args = {}

    k = str(kind or "").strip().lower()
    if k == "repeat":
        n = None
        if "count" in args and args["count"] is not None:
            n = _to_int(args.get("count"), max_hops)
        elif "limit" in args and args["limit"] is not None:
            n = _to_int(args.get("limit"), max_hops)
        else:
            n = max_hops
        if n < 0:
            n = 0
        return min(n, hard_hops)
    if k == "iterate":
        if "max_iters" in args and args["max_iters"] is not None:
            n = _to_int(args.get("max_iters"), max_hops)
        else:
            n = max_hops
        if n < 0:
            n = 0
        return min(n, hard_hops)
    return min(max_hops, hard_hops)


def should_stop(stopped_flag=False, hops_used=0, hard_hops=14) -> bool:
    """Return True when execution must stop."""
    if bool(stopped_flag):
        return True
    try:
        used = int(hops_used)
    except (TypeError, ValueError):
        return False
    try:
        hard = int(hard_hops)
    except (TypeError, ValueError):
        return False
    if isinstance(hops_used, bool) or isinstance(hard_hops, bool):
        return False
    return used >= hard
