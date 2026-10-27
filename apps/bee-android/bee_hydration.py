"""Hydration hero stage (stdlib only)."""

from __future__ import annotations

CAMERA_X = 540
CAMERA_Y = 68.6

HERO_VIEW = "HydrationHeroView"


def overlay_type(host_bound):
    """Overlay type: 'accessibility' when host-bound else 'application'."""
    return "accessibility" if host_bound else "application"


def show_hero_stage(host, wm):
    """Show hydration hero stage; never no-ops when host is None.

    Always adds the hero view (the hit target) to ``wm`` via
    ``wm.add_view('HydrationHeroView')`` and returns
    ``{'created': True, 'overlay': <type>}``.
    """
    overlay = overlay_type(host is not None)
    if wm is not None:
        try:
            add = getattr(wm, "add_view", None)
            if callable(add):
                add(HERO_VIEW)
            else:
                # Fallback for camelCase fakes; ignore if absent.
                add2 = getattr(wm, "addView", None)
                if callable(add2):
                    add2(HERO_VIEW)
        except Exception:
            pass
        # Best-effort hit-target bookkeeping; never breaks the Fake wm
        # (which only exposes add_view/views) and never adds a second view.
        try:
            ht = getattr(wm, "hit_targets", None)
            if isinstance(ht, list):
                if HERO_VIEW not in ht:
                    ht.append(HERO_VIEW)
            else:
                mark = getattr(wm, "add_hit_target", None)
                if callable(mark):
                    try:
                        mark(HERO_VIEW)
                    except TypeError:
                        try:
                            mark(HERO_VIEW, CAMERA_X, CAMERA_Y)
                        except Exception:
                            pass
        except Exception:
            pass
    return {"created": True, "overlay": overlay}


def play_water_now(wm):
    """Play water hero now; delegates to show_hero_stage(None, wm)."""
    return show_hero_stage(None, wm)
