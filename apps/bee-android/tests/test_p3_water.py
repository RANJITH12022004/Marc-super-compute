"""P3 hydration / water hero stage — stdlib unittest, no network."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MOD_PATH = ROOT / "bee_hydration.py"


def _load():
    spec = importlib.util.spec_from_file_location("bee_hydration", str(MOD_PATH))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load()


class FakeWM:
    """Fake WindowManager with views=[]."""

    def __init__(self):
        self.views = []

    def add_view(self, view, params=None):
        self.views.append(view)
        return view

    # Android-style camelCase alias.
    def addView(self, view, params=None):  # noqa: N802
        return self.add_view(view, params=params)

    def __getattr__(self, name):
        # Tolerate extra WindowManager surface (display, params, etc.)
        # without hiding the real `views` list.
        def _noop(*args, **kwargs):
            return None

        return _noop


def _camera_snapshot():
    snap = {}
    for key in dir(H):
        if "CAMERA" in key.upper():
            try:
                snap[key] = copy.deepcopy(getattr(H, key))
            except Exception:
                pass
    return snap


def _show_hero(wm):
    # Canonical: show_hero_stage(None, wm) creates a view.
    try:
        return H.show_hero_stage(None, wm)
    except TypeError:
        # Fallback for single-arg (wm-only) variants.
        return H.show_hero_stage(wm)


def _play_water(wm):
    fn = H.play_water_now
    for args in ((None, wm), (wm,), ()):
        try:
            return fn(*args)
        except TypeError:
            continue
    # Re-raise with canonical single-wm call for a clear error.
    return fn(wm)


class P3WaterTests(unittest.TestCase):
    def test_camera_frozen(self):
        # Island camera is frozen (same as P0: 540, 68.6) — must not drift.
        self.assertTrue(
            any("CAMERA" in k.upper() for k in dir(H)),
            "bee_hydration must expose CAMERA",
        )
        before = _camera_snapshot()
        self.assertTrue(before, "expected at least one CAMERA attr")
        wm = FakeWM()
        _show_hero(wm)
        try:
            _play_water(FakeWM())
        except Exception:
            pass
        after = _camera_snapshot()
        self.assertEqual(before, after)

    def test_show_hero_stage_creates_view(self):
        wm = FakeWM()  # FakeWM with views=[]
        self.assertEqual(wm.views, [])
        H.show_hero_stage(None, wm)
        self.assertGreaterEqual(len(wm.views), 1)

    def test_show_hero_stage_helper_frozen_camera(self):
        before = _camera_snapshot()
        wm = FakeWM()
        _show_hero(wm)
        self.assertGreaterEqual(len(wm.views), 1)
        self.assertEqual(before, _camera_snapshot())

    def test_play_water_now_adds_view(self):
        wm = FakeWM()
        self.assertEqual(wm.views, [])
        _play_water(wm)
        self.assertGreaterEqual(len(wm.views), 1)

    def test_play_water_now_grows_views(self):
        wm = FakeWM()
        _show_hero(wm)
        n0 = len(wm.views)
        _play_water(wm)
        self.assertGreater(len(wm.views), n0)


if __name__ == "__main__":
    unittest.main()
