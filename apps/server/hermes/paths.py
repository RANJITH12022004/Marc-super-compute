"""Hermes path + goal safety (loopback only, stdlib only).

- Marc is the only client. Loopback only.
- Never use a workdir containing mark-laptop or /home/rox/marc/android.
- Never allow `/` as a workdir.
"""

from __future__ import annotations

import re

BLOCKED_WORKDIR_SUBSTRINGS = ("mark-laptop", "/home/rox/marc/android")
BLOCKED_GOAL_SUBSTRINGS = ("reboot", "shutdown", "sudo")
_RM_WORD = re.compile(r"\brm\b", re.IGNORECASE)


def is_safe_workdir(path) -> bool:
    """Return False if empty, `/`, or containing blocked substrings."""
    if path is None:
        return False
    text = str(path).strip()
    if not text:
        return False
    if text == "/":
        return False
    # Normalise backslashes so Windows-style blocked paths are caught too.
    normalized = text.replace("\\", "/")
    if normalized == "/":
        return False
    # Trailing-slash root like "//" is also root.
    stripped = normalized.strip()
    if stripped in ("/", "//"):
        return False
    for blocked in BLOCKED_WORKDIR_SUBSTRINGS:
        if blocked in text:
            return False
        if blocked in normalized:
            return False
    return True


def workdir_error(path) -> str | None:
    if is_safe_workdir(path):
        return None
    if path is None or not str(path).strip():
        return "empty workdir refused"
    text = str(path).strip()
    if text in ("/", "//"):
        return "root workdir refused"
    for blocked in BLOCKED_WORKDIR_SUBSTRINGS:
        if blocked in text or blocked in text.replace("\\", "/"):
            return "blocked workdir refused: %s" % blocked
    return "unsafe workdir refused"


def is_safe_goal(goal) -> bool:
    """Return False if goal asks for reboot/shutdown/sudo/rm."""
    if goal is None:
        return False
    text = str(goal)
    if not text.strip():
        return False
    lowered = text.lower()
    for blocked in BLOCKED_GOAL_SUBSTRINGS:
        if blocked in lowered:
            return False
    if _RM_WORD.search(text):
        return False
    return True


def goal_error(goal) -> str | None:
    if is_safe_goal(goal):
        return None
    if goal is None or not str(goal).strip():
        return "empty goal refused"
    return "blocked goal refused (reboot/shutdown/sudo/rm)"


__all__ = [
    "is_safe_workdir",
    "is_safe_goal",
    "workdir_error",
    "goal_error",
    "BLOCKED_WORKDIR_SUBSTRINGS",
    "BLOCKED_GOAL_SUBSTRINGS",
]
