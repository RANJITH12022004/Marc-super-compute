"""Bee overlay contract (stdlib only, no Android imports).

Mirrors apps/bee-android/src/com/marc/island/BeeOverlay.java.

Fixes the hero/hit crash: hit overlay type MUST equal hero overlay type.
Hourly cadence: unseen pills wait a full hour (never 8000ms).
"""

CAMERA_X = 540
CAMERA_Y = 68.6

HOUR_MS = 3600000

PLAY_ON_OPEN = False


def overlay_type(host_bound):
    """Return 'accessibility' when host-bound else 'application'."""
    return "accessibility" if host_bound else "application"


def hit_overlay_type(host_bound):
    """Hit overlay type; MUST equal overlay_type (crash fix)."""
    return overlay_type(host_bound)


def add_view_safe(wm, name):
    """Call wm.add_view(name) safely; never raises.

    Returns True on success, False on any failure (including None wm,
    missing method, or callee raising).
    """
    try:
        if wm is None:
            return False
        fn = getattr(wm, "add_view", None)
        if fn is None:
            fn = getattr(wm, "addView", None)
        if fn is None:
            return False
        try:
            fn(name)
        except TypeError:
            try:
                fn()
            except BaseException:
                return False
        return True
    except BaseException:
        return False


def next_delay_ms(seen, last_ms, now_ms):
    """Hourly delay helper.

    - if not seen: return HOUR_MS (never 8000)
    - if now-last < HOUR_MS: return remaining ms
    - else: return 0 meaning due
    """
    if not seen:
        return HOUR_MS
    try:
        last = int(last_ms)
        now = int(now_ms)
    except (TypeError, ValueError):
        return 0
    elapsed = now - last
    if elapsed < 0:
        return HOUR_MS
    if elapsed < HOUR_MS:
        return HOUR_MS - elapsed
    return 0


def play_on_open():
    """Whether to play on open; always False."""
    return False


__all__ = [
    "CAMERA_X",
    "CAMERA_Y",
    "HOUR_MS",
    "PLAY_ON_OPEN",
    "overlay_type",
    "hit_overlay_type",
    "add_view_safe",
    "next_delay_ms",
    "play_on_open",
]
