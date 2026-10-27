"""Ride-env tests — context (desk/driving) + hop cap (stdlib only, no network).

Run:
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

# APP_ROOT is parent of tests/ (i.e. apps/marc-muse).
APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_ROOT / "config.py"


def _load_config():
    import sys
    spec = importlib.util.spec_from_file_location("marc_config", str(CONFIG_PATH))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load config.py from %s" % CONFIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses needs the module registered in sys.modules at exec time.
    sys.modules["marc_config"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod
CONFIG = _load_config()


class RideEnvTest(unittest.TestCase):
    def test_default_context_is_desk(self):
        settings = CONFIG.load_settings(env={})
        self.assertEqual(settings.context, "desk")

    def test_marc_context_driving(self):
        settings = CONFIG.load_settings(env={"MARC_CONTEXT": "driving"})
        self.assertEqual(settings.context, "driving")

    def test_context_alias_works(self):
        settings = CONFIG.load_settings(env={"CONTEXT": "driving"})
        self.assertEqual(settings.context, "driving")

    def test_marc_context_takes_precedence_over_alias(self):
        settings = CONFIG.load_settings(
            env={"MARC_CONTEXT": "driving", "CONTEXT": "desk"}
        )
        self.assertEqual(settings.context, "driving")

    def test_invalid_car_falls_back_to_desk(self):
        settings = CONFIG.load_settings(env={"MARC_CONTEXT": "car"})
        self.assertEqual(settings.context, "desk")
        alias = CONFIG.load_settings(env={"CONTEXT": "car"})
        self.assertEqual(alias.context, "desk")

    def test_context_normalized(self):
        settings = CONFIG.load_settings(env={"MARC_CONTEXT": "  DRIVING  "})
        self.assertEqual(settings.context, "driving")
        desk = CONFIG.load_settings(env={"MARC_CONTEXT": "  Desk "})
        self.assertEqual(desk.context, "desk")

    def test_marc_mode_default_sandbox(self):
        settings = CONFIG.load_settings(env={})
        self.assertEqual(settings.mode, "sandbox")

    def test_hop_cap_driving_is_6(self):
        self.assertEqual(CONFIG.hop_cap("driving"), 6)
        driving = CONFIG.load_settings(env={"MARC_CONTEXT": "driving"})
        self.assertEqual(CONFIG.hop_cap(driving.context), 6)
        self.assertEqual(CONFIG.hop_cap(driving), 6)

    def test_hop_cap_desk_is_8(self):
        self.assertEqual(CONFIG.hop_cap("desk"), 8)
        desk = CONFIG.load_settings(env={})
        self.assertEqual(desk.max_hops, 8)
        self.assertEqual(CONFIG.hop_cap(desk.context), 8)
        self.assertEqual(CONFIG.hop_cap(desk), desk.max_hops)

    def test_is_driving_true_only_for_driving(self):
        self.assertTrue(CONFIG.is_driving("driving"))
        self.assertFalse(CONFIG.is_driving("desk"))
        self.assertFalse(CONFIG.is_driving(""))
        driving = CONFIG.load_settings(env={"MARC_CONTEXT": "driving"})
        desk = CONFIG.load_settings(env={})
        self.assertTrue(CONFIG.is_driving(driving.context))
        self.assertFalse(CONFIG.is_driving(desk.context))
        self.assertTrue(CONFIG.is_driving(driving))
        self.assertFalse(CONFIG.is_driving(desk))


if __name__ == "__main__":
    unittest.main()
