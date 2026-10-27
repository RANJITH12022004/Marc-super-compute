"""B3 UI unittest (importlib-loaded, stdlib only, no network, no Android)."""
from __future__ import annotations

import importlib.util
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

    def test_themes_xml(self):
        test_themes_xml()


if __name__ == "__main__":
    unittest.main()
