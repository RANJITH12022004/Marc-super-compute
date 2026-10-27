"""P4 bee palette and screens — stdlib unittest, no network."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _load(name: str):
    path = ROOT / ("%s.py" % name)
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load("bee_palette")


class P4UiTests(unittest.TestCase):
    def test_palette(self):
        self.assertEqual(P.PAGE, "#0B0B0C")
        self.assertEqual(P.SURFACE, "#161618")
        self.assertEqual(P.INK, "#F5F5F7")
        self.assertEqual(P.HONEY, "#E8B15A")
        self.assertEqual(P.OK, "#30D158")
        self.assertEqual(P.WAIT, "#FF9F0A")
        self.assertEqual(P.FAIL, "#FF453A")
        self.assertEqual(P.NAV, ("Island", "Chat", "Setup"))

    def test_colors_xml(self):
        text = (ROOT / "res" / "values" / "colors.xml").read_text(encoding="utf-8")
        for name in ("bee_page", "bee_surface", "bee_ink", "bee_honey", "bee_ok", "bee_wait", "bee_fail"):
            self.assertIn(name, text)

    def test_home_nav_and_water(self):
        text = (ROOT / "res" / "layout" / "activity_home.xml").read_text(encoding="utf-8")
        self.assertIn("Play water", text)
        self.assertIn("Island", text)
        self.assertIn("Chat", text)
        self.assertIn("Setup", text)
        self.assertIn("@color/bee_page", text)

    def test_setup_key_slot(self):
        text = (ROOT / "res" / "layout" / "activity_setup.xml").read_text(encoding="utf-8")
        self.assertIn("paste key", text)
        self.assertIn("muse-spark-1.3", text)
        self.assertIn("Turn on bee accessibility", text)


if __name__ == "__main__":
    unittest.main()
