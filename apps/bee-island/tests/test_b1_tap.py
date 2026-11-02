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

Also checks bee-island Java sources as text (no Android runtime):
  * IslandTouch.java: CAMERA_X 540 / CAMERA_Y 68.6, HOLD_MS 2000,
    onHold -> open_app, TAP_IGNORE_MS 300 (not 8000), hitBox uses HIT_SLOP_DP
  * IslandService.java: must NOT contain TYPE_ACCESSIBILITY_OVERLAY
  * IslandAccess.java: MUST contain TYPE_ACCESSIBILITY_OVERLAY and showPill
"""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

TOUCH = (
    Path(__file__).resolve().parents[3] / "apps" / "bee-android" / "island_touch.py"
)

ISLAND_ROOT = Path(__file__).resolve().parents[1]
ISLAND_TOUCH_JAVA = (
    ISLAND_ROOT / "src" / "com" / "bee" / "island" / "IslandTouch.java"
)
ISLAND_SERVICE_JAVA = (
    ISLAND_ROOT / "src" / "com" / "bee" / "island" / "IslandService.java"
)
ISLAND_ACCESS_JAVA = (
    ISLAND_ROOT / "src" / "com" / "bee" / "island" / "IslandAccess.java"
)


def load_touch():
    spec = importlib.util.spec_from_file_location("island_touch", TOUCH)
    assert spec is not None and spec.loader is not None, f"no spec for {TOUCH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_java(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


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


# --- bee-island Java text checks (no Android runtime) ---


def test_java_camera_still_present():
    src = _read_java(ISLAND_TOUCH_JAVA)
    assert re.search(r"\bCAMERA_X\b\s*=\s*540(\.0f?|f)?\b", src), (
        "IslandTouch.java must keep CAMERA_X 540"
    )
    assert re.search(r"\bCAMERA_Y\b\s*=\s*68\.6f?\b", src), (
        "IslandTouch.java must keep CAMERA_Y 68.6"
    )


def test_java_hold_ms_2000():
    src = _read_java(ISLAND_TOUCH_JAVA)
    assert re.search(r"\bHOLD_MS\b\s*=\s*2000\b", src), (
        "IslandTouch.java HOLD_MS must be 2000"
    )


def test_java_on_hold_open_app():
    src = _read_java(ISLAND_TOUCH_JAVA)
    assert re.search(r"\bonHold\s*\(", src), (
        "IslandTouch.java must define onHold method"
    )
    assert "open_app" in src, "IslandTouch.java must contain open_app"


def test_java_tap_ignore_300():
    src = _read_java(ISLAND_TOUCH_JAVA)
    assert re.search(r"\bTAP_IGNORE_MS\b\s*=\s*300\b", src), (
        "IslandTouch.java TAP_IGNORE_MS must be 300"
    )
    assert not re.search(r"\bTAP_IGNORE_MS\b\s*=\s*8000\b", src), (
        "IslandTouch.java TAP_IGNORE_MS must not be 8000"
    )
    # ignore window must be driven by TAP_IGNORE_MS
    assert re.search(r"\bonTap\b[\s\S]*\bTAP_IGNORE_MS\b", src), (
        "IslandTouch.java onTap must use TAP_IGNORE_MS as ignore window"
    )


def test_java_hitbox_uses_slop():
    src = _read_java(ISLAND_TOUCH_JAVA)
    assert re.search(r"\bhitBox\s*\(", src), (
        "IslandTouch.java must define hitBox"
    )
    assert "HIT_SLOP_DP" in src, "IslandTouch.java must contain HIT_SLOP_DP"
    idx = src.find("hitBox")
    assert idx != -1
    tail = src[idx : idx + 2000]
    assert "HIT_SLOP_DP" in tail, (
        "IslandTouch.java hitBox must use HIT_SLOP_DP"
    )


def test_java_service_no_a11y_overlay():
    src = _read_java(ISLAND_SERVICE_JAVA)
    assert "TYPE_ACCESSIBILITY_OVERLAY" not in src, (
        "IslandService.java must NOT contain TYPE_ACCESSIBILITY_OVERLAY"
    )


def test_java_access_has_overlay_showpill():
    src = _read_java(ISLAND_ACCESS_JAVA)
    assert "TYPE_ACCESSIBILITY_OVERLAY" in src, (
        "IslandAccess.java MUST contain TYPE_ACCESSIBILITY_OVERLAY"
    )
    assert "showPill" in src, "IslandAccess.java MUST contain showPill"


def test_visual_center_stays_on_camera():
    # Nothing (3a) Lite dumpsys: center (540, 68.6), density 2.625.
    # visualW=126dp*2.625=330.75, visualH=34dp*2.625=89.25, slop=24dp*2.625=63.
    cameraX = 540.0
    cameraY = 68.6
    visualW = 330.75
    visualH = 89.25
    slop = 63.0
    halfW = visualW / 2.0
    halfH = visualH / 2.0
    winX = max(0.0, cameraX - halfW - slop)
    above = cameraY - halfH
    winY = (cameraY - halfH - slop) if (above >= slop) else 0.0
    visualLeft = cameraX - winX - halfW
    visualTop = cameraY - winY - halfH
    assert abs(winY + visualTop + visualH / 2.0 - 68.6) < 0.02, (
        "visual center must stay on camera Y=68.6 even when winY clamps to 0"
    )
    # Java sources must implement the shared pillWindow math.
    touch_src = _read_java(ISLAND_TOUCH_JAVA)
    assert "pillWindow" in touch_src, "IslandTouch.java must contain pillWindow"
    assert re.search(r"\bCAMERA_X\b\s*=\s*540(\.0f?|f)?\b", touch_src), (
        "IslandTouch.java must keep CAMERA_X 540"
    )
    assert re.search(r"\bCAMERA_Y\b\s*=\s*68\.6f?\b", touch_src), (
        "IslandTouch.java must keep CAMERA_Y 68.6"
    )
    svc_src = _read_java(ISLAND_SERVICE_JAVA)
    assert "pillWindow" in svc_src, "IslandService.java must contain pillWindow"
    # Visual child must use Gravity.TOP (TOP|START), never Gravity.CENTER.
    assert re.search(r"visualLp\s*\.\s*gravity\s*=\s*Gravity\.TOP", svc_src), (
        "IslandService.java visual LayoutParams must use Gravity.TOP"
    )
    assert "visualLp.gravity = Gravity.CENTER" not in svc_src, (
        "IslandService.java must not Gravity.CENTER the visual child"
    )
    assert "visualLp.gravity=Gravity.CENTER" not in svc_src.replace(" ", ""), (
        "IslandService.java must not Gravity.CENTER the visual child"
    )


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

    def test_java_camera_still_present(self):
        test_java_camera_still_present()

    def test_java_hold_ms_2000(self):
        test_java_hold_ms_2000()

    def test_java_on_hold_open_app(self):
        test_java_on_hold_open_app()

    def test_java_tap_ignore_300(self):
        test_java_tap_ignore_300()

    def test_java_hitbox_uses_slop(self):
        test_java_hitbox_uses_slop()

    def test_java_service_no_a11y_overlay(self):
        test_java_service_no_a11y_overlay()

    def test_java_access_has_overlay_showpill(self):
        test_java_access_has_overlay_showpill()

    def test_visual_center_stays_on_camera(self):
        test_visual_center_stays_on_camera()


if __name__ == "__main__":
    unittest.main()
