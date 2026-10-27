"""C0 capsule overlay + launcher icon (stdlib unittest, no network)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
TOUCH = REPO / "apps" / "bee-android" / "island_touch.py"
SERVICE = ROOT / "src" / "com" / "bee" / "island" / "IslandService.java"
MANIFEST = ROOT / "AndroidManifest.xml"
CAPSULE = ROOT / "res" / "drawable" / "island_capsule.xml"
PIPS = ROOT / "res" / "drawable" / "island_pips.xml"


def load_touch():
    spec = importlib.util.spec_from_file_location("island_touch", TOUCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class C0CapsuleTests(unittest.TestCase):
    def test_camera_frozen(self):
        t = load_touch()
        self.assertEqual(float(t.CAMERA_X), 540.0)
        self.assertEqual(float(t.CAMERA_Y), 68.6)
        src = SERVICE.read_text(encoding="utf-8")
        self.assertIn("CAMERA_X_PX", src)
        self.assertIn("540", src)
        self.assertIn("68.6", src)

    def test_capsule_not_rectangle(self):
        xml = CAPSULE.read_text(encoding="utf-8")
        self.assertIn("17dp", xml)
        self.assertIn("corners", xml)
        src = SERVICE.read_text(encoding="utf-8")
        self.assertIn("island_capsule", src)
        self.assertNotIn("setBackgroundColor(0xFF111111)", src)

    def test_pips_honey(self):
        xml = PIPS.read_text(encoding="utf-8")
        self.assertIn("E8B15A", xml)
        src = SERVICE.read_text(encoding="utf-8")
        self.assertIn("island_pips", src)

    def test_launcher_icon(self):
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("@mipmap/ic_launcher", text)
        self.assertIn("roundIcon", text)
        self.assertTrue((ROOT / "res" / "mipmap-anydpi-v26" / "ic_launcher.xml").is_file())


if __name__ == "__main__":
    unittest.main()
