"""IslandTouch pure touch contract (stdlib only, no Android imports).

Mirrors apps/bee-android/src/com/marc/island/IslandTouch.java.
Visual pill origin is fixed at CAMERA_X/CAMERA_Y; hit area expands by
HIT_SLOP_DP on every side without moving the visual origin.
"""

CAMERA_X = 540.0
CAMERA_Y = 68.6
HIT_SLOP_DP = 24
LISTEN_TIMEOUT_MS = 8000


def overlay_type(a11y_bound):
    """Return 'accessibility' if bound else 'application'."""
    return "accessibility" if a11y_bound else "application"


def window_flags(screen_on=False):
    """Window flags for the pill; never includes not_touchable."""
    flags = {"touchable", "not_focusable", "layout_in_screen", "watch_outside_touch"}
    if screen_on:
        flags.add("keep_screen_on")
    return frozenset(flags)


def window_flags_touchable(screen_on=False):
    """Pill always receives taps; always True."""
    return True


def on_down(*args, **kwargs):
    """Gesture onDown: always True."""
    return True


def on_tap(listening, confirming, listening_age_ms=0):
    """Tap dispatch.

    - if confirming return 'cancel'
    - elif listening and age < LISTEN_TIMEOUT_MS return 'ignore'
    - elif listening and age >= LISTEN_TIMEOUT_MS return 'restart_listen'
    - else return 'start_listen'
    """
    if confirming:
        return "cancel"
    if listening:
        try:
            age = float(listening_age_ms)
        except (TypeError, ValueError):
            age = 0.0
        if age < float(LISTEN_TIMEOUT_MS):
            return "ignore"
        return "restart_listen"
    return "start_listen"


def hit_box(camera_x, camera_y, pill_w, pill_h):
    """Expanded hit box: (left, top, right, bottom).

    Expands by HIT_SLOP_DP on every side; visual origin unchanged.
    """
    slop = float(HIT_SLOP_DP)
    cx = float(camera_x)
    cy = float(camera_y)
    w = float(pill_w)
    h = float(pill_h)
    left = cx - slop
    top = cy - slop
    right = cx + w + slop
    bottom = cy + h + slop
    return (left, top, right, bottom)


__all__ = [
    "CAMERA_X",
    "CAMERA_Y",
    "HIT_SLOP_DP",
    "LISTEN_TIMEOUT_MS",
    "overlay_type",
    "window_flags",
    "window_flags_touchable",
    "on_down",
    "on_tap",
    "hit_box",
]
