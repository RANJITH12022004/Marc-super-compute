"""B1 tap contract reuse for bee-island (importlib-loaded).

Reuses the canonical pure touch contract in apps/bee-android/island_touch.py
via importlib without rewriting it. Mirrors
apps/bee-android/src/com/marc/island/IslandTouch.java.

Checks:
  * CAMERA origin is 540 / 68.6
  * on_down always true
  * overlay_type bound -> accessibility else application
  * on_tap confirming -> cancel
  * on_tap stale listening (age >= LISTEN_TIMEOUT_MS) -> restart_listen
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

TOUCH = (
    Path(__file__).resolve().parents[3] / "apps" / "bee-android" / "island_touch.py"
)


def load_touch():
    spec = importlib.util.spec_from_file_location("island_touch", TOUCH)
    assert spec is not None and spec.loader is not None, f"no spec for {TOUCH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_touch_module_loads_via_importlib():
    assert TOUCH.is_file(), f"missing {TOUCH}"
    mod = load_touch()
    for name in (
        "CAMERA_X",
        "CAMERA_Y",
        "HIT_SLOP_DP",
        "LISTEN_TIMEOUT_MS",
        "overlay_type",
        "on_down",
        "on_tap",
    ):
        assert hasattr(mod, name), f"island_touch missing {name}"


def test_camera_origin():
    mod = load_touch()
    assert float(mod.CAMERA_X) == 540.0, f"CAMERA_X={mod.CAMERA_X!r}"
    assert float(mod.CAMERA_Y) == 68.6, f"CAMERA_Y={mod.CAMERA_Y!r}"


def test_on_down_true():
    mod = load_touch()
    assert mod.on_down() is True
    assert mod.on_down(None, None) is True
    assert bool(mod.on_down(object())) is True


def test_overlay_type():
    mod = load_touch()
    assert mod.overlay_type(True) == "accessibility"
    assert mod.overlay_type(False) == "application"
    assert mod.overlay_type(1) == "accessibility"
    assert mod.overlay_type(0) == "application"
    assert mod.overlay_type(None) == "application"


def test_on_tap_confirm_cancel():
    mod = load_touch()
    assert mod.on_tap(False, True) == "cancel"
    assert mod.on_tap(True, True) == "cancel"
    assert mod.on_tap(True, True, listening_age_ms=0) == "cancel"
    assert mod.on_tap(False, True, listening_age_ms=999999) == "cancel"


def test_on_tap_stale_listen_restart():
    mod = load_touch()
    timeout = float(mod.LISTEN_TIMEOUT_MS)
    assert mod.on_tap(True, False, listening_age_ms=timeout) == "restart_listen"
    assert (
        mod.on_tap(True, False, listening_age_ms=timeout + 1) == "restart_listen"
    )
    assert (
        mod.on_tap(True, False, listening_age_ms=timeout + 8000)
        == "restart_listen"
    )


def test_on_tap_fresh_listen_ignore():
    mod = load_touch()
    assert mod.on_tap(True, False, listening_age_ms=0) == "ignore"
    assert mod.on_tap(True, False) == "ignore"


def test_on_tap_idle_start_listen():
    mod = load_touch()
    assert mod.on_tap(False, False) == "start_listen"
    assert mod.on_tap(False, False, listening_age_ms=999999) == "start_listen"


class B1TapTests(unittest.TestCase):
    def test_touch_module_loads_via_importlib(self):
        test_touch_module_loads_via_importlib()

    def test_camera_origin(self):
        test_camera_origin()

    def test_on_down_true(self):
        test_on_down_true()

    def test_overlay_type(self):
        test_overlay_type()

    def test_on_tap_confirm_cancel(self):
        test_on_tap_confirm_cancel()

    def test_on_tap_stale_listen_restart(self):
        test_on_tap_stale_listen_restart()

    def test_on_tap_fresh_listen_ignore(self):
        test_on_tap_fresh_listen_ignore()

    def test_on_tap_idle_start_listen(self):
        test_on_tap_idle_start_listen()


if __name__ == "__main__":
    unittest.main()
