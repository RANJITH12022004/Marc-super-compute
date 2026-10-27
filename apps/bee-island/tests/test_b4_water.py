"""B4 water hero unittest (importlib-loaded, stdlib only, no network, no Android)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERO_PATH = ROOT / "water_hero.py"


def load_hero():
    spec = importlib.util.spec_from_file_location("water_hero", HERO_PATH)
    assert spec is not None and spec.loader is not None, f"no spec for {HERO_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeWM:
    """Minimal window-manager stand-in.

    show_hero_stage is expected to call add_view(name) which appends to views.
    """

    def __init__(self):
        self.views = []

    def add_view(self, name, *args, **kwargs):
        self.views.append(name)
        return name


def test_hero_module_loads_via_importlib():
    assert HERO_PATH.is_file(), f"missing {HERO_PATH}"
    mod = load_hero()
    for name in (
        "CAMERA_X",
        "CAMERA_Y",
        "overlay_type",
        "hit_overlay_type",
        "show_hero_stage",
        "play_on_open",
        "next_delay_ms",
        "clamp_joint",
        "FALLBACK",
    ):
        # play_on_open may be lower-case per contract; allow UPPER fallback
        if name == "play_on_open":
            assert hasattr(mod, "play_on_open") or hasattr(mod, "PLAY_ON_OPEN"), (
                "water_hero missing play_on_open"
            )
            continue
        assert hasattr(mod, name), f"water_hero missing {name}"


def test_camera_origin():
    mod = load_hero()
    assert float(mod.CAMERA_X) == 540.0, f"CAMERA_X={mod.CAMERA_X!r}"
    assert float(mod.CAMERA_Y) == 68.6, f"CAMERA_Y={mod.CAMERA_Y!r}"


def test_overlay_types():
    mod = load_hero()
    assert mod.overlay_type(False) == "application"
    assert mod.overlay_type(True) == "accessibility"
    assert mod.hit_overlay_type(False) == mod.overlay_type(False) == "application"
    assert mod.hit_overlay_type(True) == mod.overlay_type(True) == "accessibility"


def test_show_hero_stage():
    mod = load_hero()
    fake = FakeWM()
    before = len(fake.views)
    result = mod.show_hero_stage(None, fake)
    assert len(fake.views) > before, "show_hero_stage did not add a view"
    # created True: support bool / (view, created) tuple / dict conventions
    if isinstance(result, (tuple, list)):
        assert len(result) >= 1, f"unexpected result {result!r}"
        if len(result) >= 2:
            # conventional (view, created)
            created = result[1]
            # tolerate swapped order (created, view)
            if created is not True and result[0] is True:
                created = result[0]
            assert created is True, f"created flag not True: {result!r}"
        else:
            assert result[0] is True, f"created flag not True: {result!r}"
    elif isinstance(result, dict):
        assert result.get("created") is True, f"created flag not True: {result!r}"
    else:
        assert result is True, f"show_hero_stage created not True: {result!r}"


def test_play_on_open_false():
    mod = load_hero()
    if hasattr(mod, "play_on_open") and callable(mod.play_on_open):
        assert mod.play_on_open() is False, f"play_on_open()={mod.play_on_open()!r}"
    elif hasattr(mod, "play_on_open"):
        assert mod.play_on_open is False, f"play_on_open={mod.play_on_open!r}"
    else:
        assert mod.PLAY_ON_OPEN is False, f"PLAY_ON_OPEN={mod.PLAY_ON_OPEN!r}"


def _next_delay_unseen(mod):
    # Primary contract: next_delay_ms(False) is unseen -> 3600000.
    # Fall back to keyword / count-based signatures if needed.
    try:
        return mod.next_delay_ms(False)
    except TypeError:
        pass
    try:
        return mod.next_delay_ms(seen=False)
    except TypeError:
        pass
    try:
        return mod.next_delay_ms(0)
    except TypeError:
        pass
    try:
        return mod.next_delay_ms(None)
    except TypeError:
        pass
    return mod.next_delay_ms()


def test_next_delay_unseen():
    mod = load_hero()
    val = _next_delay_unseen(mod)
    assert val == 3600000, f"next_delay_ms unseen={val!r}, expected 3600000"
    assert val != 8000, f"next_delay_ms unseen must not be 8000, got {val!r}"


def test_clamp_joint_elbow():
    mod = load_hero()
    low = mod.clamp_joint("elbow", 0)
    high = mod.clamp_joint("elbow", 200)
    assert float(low) >= 15.0, f"clamp_joint elbow low={low!r} < 15"
    assert float(high) <= 145.0, f"clamp_joint elbow high={high!r} > 145"


def test_fallback():
    mod = load_hero()
    assert mod.FALLBACK == "water_courier", f"FALLBACK={mod.FALLBACK!r}"


def test_art_exists():
    parent = HERO_PATH.parent
    art = parent / "art"
    assert art.is_dir(), f"missing art dir {art}"
    candidates = ("character-sheet.svg", "motion-sheet.svg", "README", "README.md")
    found = [c for c in candidates if (art / c).is_file()]
    assert found, f"art dir {art} missing one of {candidates}"


class B4WaterTests(unittest.TestCase):
    def test_hero_module_loads_via_importlib(self):
        test_hero_module_loads_via_importlib()

    def test_camera_origin(self):
        test_camera_origin()

    def test_overlay_types(self):
        test_overlay_types()

    def test_show_hero_stage(self):
        test_show_hero_stage()

    def test_play_on_open_false(self):
        test_play_on_open_false()

    def test_next_delay_unseen(self):
        test_next_delay_unseen()

    def test_clamp_joint_elbow(self):
        test_clamp_joint_elbow()

    def test_fallback(self):
        test_fallback()

    def test_art_exists(self):
        test_art_exists()


if __name__ == "__main__":
    unittest.main()
