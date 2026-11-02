"""B3 UI unittest (importlib-loaded, stdlib only, no network, no Android)."""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "bee_palette.py"
COLORS = ROOT / "res" / "values" / "colors.xml"
ACTIVITY_HOME = ROOT / "res" / "layout" / "activity_home.xml"
THEMES = ROOT / "res" / "values" / "themes.xml"


def load_palette():
    spec = importlib.util.spec_from_file_location("bee_palette", PALETTE_PATH)
    assert spec is not None and spec.loader is not None, f"no spec for {PALETTE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_palette_loads_via_importlib():
    assert PALETTE_PATH.is_file(), f"missing {PALETTE_PATH}"
    mod = load_palette()
    for name in ("PAGE", "SURFACE", "INK", "SEPARATOR", "ACCENT", "NAV"):
        assert hasattr(mod, name), f"bee_palette missing {name}"


def test_palette_colors():
    mod = load_palette()
    assert mod.PAGE == "#000000"
    assert mod.SURFACE == "#1C1C1E"
    assert mod.INK == "#F5F5F7"
    assert mod.SEPARATOR == "#38383A"
    assert mod.ACCENT == "#E8B15A"


def test_palette_nav():
    mod = load_palette()
    assert tuple(mod.NAV) == ("Island", "Chat", "Setup")


def test_colors_xml():
    assert COLORS.is_file(), f"missing {COLORS}"
    text = COLORS.read_text(encoding="utf-8")
    for name in ("bee_page", "bee_surface", "bee_ink", "bee_separator", "bee_honey"):
        assert name in text, f"colors.xml missing {name}"


def test_activity_home_contains():
    assert ACTIVITY_HOME.is_file(), f"missing {ACTIVITY_HOME}"
    text = ACTIVITY_HOME.read_text(encoding="utf-8")
    for needle in (
        "bee",
        "Island",
        "Chat",
        "Setup",
        "Play water",
        "paste key",
        "muse-spark-1.3",
        "Ask bee",
        "Yes",
        "Cancel",
        "@color/bee_page",
    ):
        assert needle in text, f"activity_home.xml missing {needle!r}"
    assert ("permission" in text.lower() or "Overlay" in text), (
        "activity_home.xml missing permission/Overlay"
    )


def test_activity_home_no_status_rings():
    assert ACTIVITY_HOME.is_file(), f"missing {ACTIVITY_HOME}"
    text = ACTIVITY_HOME.read_text(encoding="utf-8")
    assert "Status ring" not in text, "activity_home.xml must not contain Status rings"
    assert "id/status_ring" not in text, "activity_home.xml must not contain status_ring"


def _view_block(text: str, view_id: str) -> str:
    """Return the XML element string that declares @+id/<view_id>."""
    pattern = re.compile(
        r"<(?:Button|TextView|EditText|View|LinearLayout|FrameLayout)[^>]*@\+id/"
        + re.escape(view_id)
        + r'"[^>]*?(?:/>|>.*?</(?:Button|TextView|EditText|View|LinearLayout|FrameLayout)>)',
        re.DOTALL,
    )
    m = pattern.search(text)
    assert m, f"activity_home.xml missing id/{view_id}"
    return m.group(0)


def test_activity_home_honey_black_nav():
    """Honey-black nav: black ink (bee_nav_ink or #000000) near nav_island."""
    assert ACTIVITY_HOME.is_file(), f"missing {ACTIVITY_HOME}"
    text = ACTIVITY_HOME.read_text(encoding="utf-8")
    assert "nav_island" in text, "activity_home.xml missing nav_island"
    try:
        block = _view_block(text, "nav_island")
    except AssertionError:
        block = ""
    # Direct block check first (strict: ink on the nav button itself).
    block_low = block.lower()
    block_has_ink = ("bee_nav_ink" in block) or ("#000000" in block_low)
    if block_has_ink:
        return
    # Fallback: allow ink declared near nav_island (parent bar / adjacent nav).
    idx = text.find("nav_island")
    window = text[max(0, idx - 2000) : idx + 2000]
    window_low = window.lower()
    assert ("bee_nav_ink" in window) or ("#000000" in window_low), (
        "activity_home.xml must contain bee_nav_ink or #000000 near nav_island"
    )


def test_activity_home_nav_not_honey_on_honey():
    """nav_island must not set both backgroundTint honey AND textColor honey."""
    assert ACTIVITY_HOME.is_file(), f"missing {ACTIVITY_HOME}"
    text = ACTIVITY_HOME.read_text(encoding="utf-8")
    block = _view_block(text, "nav_island")
    low = block.lower()
    has_bg_honey = bool(
        re.search(r"backgroundtint\s*=\s*\"[^\"]*honey[^\"]*\"", low)
    )
    has_text_honey = bool(
        re.search(r"textcolor\s*=\s*\"[^\"]*honey[^\"]*\"", low)
    )
    assert not (has_bg_honey and has_text_honey), (
        "nav_island must not set both backgroundTint honey AND textColor honey"
    )


def test_activity_home_island_spoken_state():
    """Island spoken/state views must exist."""
    assert ACTIVITY_HOME.is_file(), f"missing {ACTIVITY_HOME}"
    text = ACTIVITY_HOME.read_text(encoding="utf-8")
    assert "island_spoken" in text, "activity_home.xml missing island_spoken"
    assert "island_state" in text, "activity_home.xml missing island_state"


def test_activity_home_confirm_actions():
    """confirm_yes must say Send and confirm_cancel must say Cancel."""
    assert ACTIVITY_HOME.is_file(), f"missing {ACTIVITY_HOME}"
    text = ACTIVITY_HOME.read_text(encoding="utf-8")
    yes_block = _view_block(text, "confirm_yes")
    assert "Send" in yes_block, "confirm_yes must say Send"
    assert 'android:text="Send"' in yes_block, 'confirm_yes must set android:text="Send"'
    cancel_block = _view_block(text, "confirm_cancel")
    assert "Cancel" in cancel_block, "confirm_cancel must say Cancel"
    assert 'android:text="Cancel"' in cancel_block, (
        'confirm_cancel must set android:text="Cancel"'
    )


def test_themes_xml():
    assert THEMES.is_file(), f"missing {THEMES}"
    text = THEMES.read_text(encoding="utf-8")
    assert "Theme.Bee" in text, "themes.xml missing Theme.Bee"
    assert "Theme.AppCompat.NoActionBar" in text, (
        "themes.xml missing Theme.AppCompat.NoActionBar"
    )


class B3UiTests(unittest.TestCase):
    def test_palette_loads_via_importlib(self):
        test_palette_loads_via_importlib()

    def test_palette_colors(self):
        test_palette_colors()

    def test_palette_nav(self):
        test_palette_nav()

    def test_colors_xml(self):
        test_colors_xml()

    def test_activity_home_contains(self):
        test_activity_home_contains()

    def test_activity_home_no_status_rings(self):
        test_activity_home_no_status_rings()

    def test_activity_home_honey_black_nav(self):
        test_activity_home_honey_black_nav()

    def test_activity_home_nav_not_honey_on_honey(self):
        test_activity_home_nav_not_honey_on_honey()

    def test_activity_home_island_spoken_state(self):
        test_activity_home_island_spoken_state()

    def test_activity_home_confirm_actions(self):
        test_activity_home_confirm_actions()

    def test_themes_xml(self):
        test_themes_xml()


if __name__ == "__main__":
    unittest.main()
