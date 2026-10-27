"""P0 island tap contract — stdlib unittest, no network."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MOD_PATH = ROOT / "island_touch.py"


def _load():
    spec = importlib.util.spec_from_file_location("island_touch", str(MOD_PATH))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = _load()


class P0TapTests(unittest.TestCase):
    def test_camera_frozen(self):
        self.assertEqual(T.CAMERA_X, 540)
        self.assertAlmostEqual(float(T.CAMERA_Y), 68.6)

    def test_overlay_type(self):
        self.assertEqual(T.overlay_type(True), "accessibility")
        self.assertEqual(T.overlay_type(False), "application")

    def test_always_touchable(self):
        self.assertTrue(T.window_flags_touchable(True))
        self.assertTrue(T.window_flags_touchable(False))

    def test_on_tap_confirm_cancels(self):
        self.assertEqual(T.on_tap(False, True, 0), "cancel")

    def test_on_tap_listening_fresh_ignores(self):
        self.assertEqual(T.on_tap(True, False, 1000), "ignore")

    def test_on_tap_listening_stale_restarts(self):
        self.assertEqual(T.on_tap(True, False, 8000), "restart_listen")

    def test_on_tap_idle_starts(self):
        self.assertEqual(T.on_tap(False, False, 0), "start_listen")

    def test_on_down_always_true(self):
        self.assertTrue(T.on_down())


if __name__ == "__main__":
    unittest.main()
