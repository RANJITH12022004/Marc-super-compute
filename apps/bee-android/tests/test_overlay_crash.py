"""Overlay crash-contract — stdlib unittest, no network.

Crash-contract for bee_overlay.py (stdlib only, no Android imports):
- hit_overlay_type(False) == overlay_type(False) == "application"
- hit + overlay are "accessibility" when True
- play_on_open is False
- next_delay_ms unseen is 3600000 (hourly), not 8000
- add_view_safe on a wm whose add_view raises returns False, does not raise
- CAMERA frozen at 540, 68.6
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MOD_PATH = ROOT / "bee_overlay.py"


def _load():
    spec = importlib.util.spec_from_file_location("bee_overlay", str(MOD_PATH))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load()


def _play_on_open_value():
    """Resolve play_on_open / PLAY_ON_OPEN value (call if callable)."""
    if hasattr(B, "play_on_open"):
        v = getattr(B, "play_on_open")
    elif hasattr(B, "PLAY_ON_OPEN"):
        v = getattr(B, "PLAY_ON_OPEN")
    else:
        raise AssertionError("bee_overlay must expose play_on_open / PLAY_ON_OPEN")
    if callable(v):
        # No-arg canonical; fall back to common single-arg forms.
        try:
            return v()
        except TypeError:
            pass
        for args in ((False,), (None,), (True,)):
            try:
                return v(*args)
            except TypeError:
                continue
        # If callable needs kwargs, try empty kwargs explicitly.
        return v()
    return v


def _next_delay_unseen():
    """Call next_delay_ms with an 'unseen' first arg."""
    fn = getattr(B, "next_delay_ms", None)
    if fn is None or not callable(fn):
        raise AssertionError("bee_overlay must expose next_delay_ms callable")
    # Canonical unseen forms first: None means never-seen.
    arg_sets = (
        (False, 0, 0),
        (None, 0, 0),
        (None,),
        (None, 0),
        (None, 1000),
        (False,),
        (False, 0),
    )
    last_err = None
    for args in arg_sets:
        try:
            return fn(*args)
        except TypeError as e:
            last_err = e
            continue
    # Keyword forms.
    kw_sets = (
        {"last_seen_ms": None},
        {"last_seen": None},
        {"seen": False},
    )
    for kw in kw_sets:
        try:
            return fn(**kw)
        except TypeError as e:
            last_err = e
            continue
    raise AssertionError("next_delay_ms has no unseen-compatible signature: %r" % (last_err,))


def _add_view_safe_call(wm, view="TestView"):
    """Call add_view_safe with common arities; propagate return."""
    fn = getattr(B, "add_view_safe", None)
    if fn is None or not callable(fn):
        raise AssertionError("bee_overlay must expose add_view_safe callable")
    last_err = None
    for args in ((wm, view), (wm, view, None), (wm,)):
        try:
            return fn(*args)
        except TypeError as e:
            last_err = e
            continue
    raise AssertionError("add_view_safe has no compatible signature: %r" % (last_err,))


class RaisingWM:
    """WindowManager fake whose add_view always raises."""

    def __init__(self):
        self.calls = 0

    def add_view(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("boom")

    # Android-style camelCase alias also raises.
    def addView(self, *args, **kwargs):  # noqa: N802
        self.calls += 1
        raise RuntimeError("boom")


class OverlayCrashTests(unittest.TestCase):
    def test_hit_overlay_type_false_is_application(self):
        self.assertEqual(B.hit_overlay_type(False), "application")

    def test_overlay_type_false_is_application(self):
        self.assertEqual(B.overlay_type(False), "application")

    def test_hit_equals_overlay_when_false(self):
        self.assertEqual(B.hit_overlay_type(False), B.overlay_type(False))
        self.assertEqual(B.hit_overlay_type(False), "application")
        self.assertEqual(B.overlay_type(False), "application")

    def test_hit_overlay_type_true_is_accessibility(self):
        self.assertEqual(B.hit_overlay_type(True), "accessibility")

    def test_overlay_type_true_is_accessibility(self):
        self.assertEqual(B.overlay_type(True), "accessibility")

    def test_play_on_open_false(self):
        value = _play_on_open_value()
        self.assertIs(value, False)
        self.assertEqual(value, False)

    def test_next_delay_ms_unseen_is_hourly_not_8s(self):
        delay = _next_delay_unseen()
        self.assertEqual(delay, 3600000)
        self.assertNotEqual(delay, 8000)

    def test_add_view_safe_raising_wm_returns_false_no_raise(self):
        wm = RaisingWM()
        try:
            result = _add_view_safe_call(wm)
        except Exception as e:
            self.fail("add_view_safe must not raise, raised %r" % (e,))
        self.assertIs(result, False)
        self.assertEqual(result, False)

    def test_camera_frozen(self):
        self.assertEqual(B.CAMERA_X, 540)
        self.assertAlmostEqual(float(B.CAMERA_Y), 68.6)


if __name__ == "__main__":
    unittest.main()
