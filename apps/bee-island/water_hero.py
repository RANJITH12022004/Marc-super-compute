"""Water hero stage contract (stdlib only)."""
CAMERA_X = 540
CAMERA_Y = 68.6
HERO_VIEW = 'WaterHeroView'
HOUR_MS = 3600000
PLAY_ON_OPEN = False
FALLBACK = 'water_courier'

JOINT_LIMITS = {
    'shoulder': (-50, 50),
    'elbow': (15, 145),
    'hip': (-25, 35),
    'knee': (5, 140),
}

__all__ = [
    'CAMERA_X',
    'CAMERA_Y',
    'HERO_VIEW',
    'HOUR_MS',
    'PLAY_ON_OPEN',
    'FALLBACK',
    'JOINT_LIMITS',
    'overlay_type',
    'hit_overlay_type',
    'clamp_joint',
    'bezier_web',
    'show_hero_stage',
    'play_water_now',
    'next_delay_ms',
    'play_on_open',
]


def overlay_type(host_bound):
    return 'accessibility' if host_bound else 'application'


def hit_overlay_type(host_bound):
    return overlay_type(host_bound)


def clamp_joint(name, angle):
    try:
        limits = JOINT_LIMITS.get(name)
    except Exception:
        return angle
    if limits is None:
        return angle
    try:
        lo, hi = limits
    except Exception:
        return angle
    try:
        v = float(angle)
    except Exception:
        return angle
    try:
        lo_f = float(lo)
        hi_f = float(hi)
    except Exception:
        return angle
    if v < lo_f:
        v = lo_f
    elif v > hi_f:
        v = hi_f
    try:
        if isinstance(angle, bool):
            return int(v)
        if isinstance(angle, int) and float(int(v)) == v:
            return int(v)
    except Exception:
        pass
    return v


def _to_xy(p):
    try:
        return (float(p[0]), float(p[1]))
    except Exception:
        pass
    try:
        return (float(getattr(p, 'x')), float(getattr(p, 'y')))
    except Exception:
        return (0.0, 0.0)


def _bez(t, a, b, c):
    u = 1.0 - t
    x = u * u * a[0] + 2.0 * u * t * b[0] + t * t * c[0]
    y = u * u * a[1] + 2.0 * u * t * b[1] + t * t * c[1]
    return (x, y)


def bezier_web(p0, p1, p2):
    a = _to_xy(p0)
    b = _to_xy(p1)
    c = _to_xy(p2)
    return (_bez(0.25, a, b, c), _bez(0.5, a, b, c), _bez(0.75, a, b, c))


def show_hero_stage(host, wm):
    try:
        overlay = overlay_type(host is not None)
    except Exception:
        try:
            overlay = 'accessibility' if (host is not None) else 'application'
        except Exception:
            overlay = 'application'
    try:
        if wm is not None:
            try:
                fn = getattr(wm, 'add_view', None)
            except Exception:
                fn = None
            if callable(fn):
                try:
                    fn(HERO_VIEW)
                except Exception:
                    pass
    except Exception:
        pass
    return {'created': True, 'overlay': overlay}


def play_water_now(wm):
    return show_hero_stage(None, wm)


def next_delay_ms(seen=False, last_ms=0, now_ms=0):
    try:
        if not seen:
            return HOUR_MS
        try:
            last = int(last_ms)
        except Exception:
            return HOUR_MS
        try:
            now = int(now_ms)
        except Exception:
            return HOUR_MS
        remaining = (last + HOUR_MS) - now
        if remaining <= 0:
            return 0
        return remaining
    except Exception:
        return HOUR_MS


def play_on_open():
    return False
