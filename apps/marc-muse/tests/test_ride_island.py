"""Ride island wave tests B1-B4 — stdlib unittest, no network.

Run:
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
import urllib.request
from pathlib import Path

# APP_ROOT is parent of tests/ (i.e. apps/marc-muse).
APP_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules (dataclasses-safe pattern).
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ISLAND = _load("island_under_test", APP_ROOT / "island.py")
AGENTS = _load("agents_under_test", APP_ROOT / "agents.py")

# Also register under short names for modules that probe them.
sys.modules.setdefault("island", ISLAND)
sys.modules.setdefault("agents", AGENTS)


class RideIslandBase(unittest.TestCase):
    def setUp(self):
        try:
            ISLAND.reset()
        except Exception:
            pass
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("network must not be used in ride island tests")

        urllib.request.urlopen = _no_network  # type: ignore[assignment]

    def tearDown(self):
        try:
            urllib.request.urlopen = self._real_urlopen  # type: ignore[assignment]
        except Exception:
            pass
        try:
            ISLAND.reset()
        except Exception:
            pass


class IslandWaveTests(RideIslandBase):
    def test_B1_state_cycle(self):
        ISLAND.reset()
        snap = ISLAND.snapshot()
        self.assertEqual(snap["state"], "idle")
        for state in ("listen", "plan", "wave", "confirm", "done"):
            ISLAND.set_state(state)
            snap = ISLAND.snapshot()
            self.assertEqual(snap["state"], state)

    def test_B2_line_clamped_to_40(self):
        ISLAND.reset()
        ISLAND.set_state("plan", line="x" * 80)
        snap = ISLAND.snapshot()
        self.assertEqual(snap["state"], "plan")
        self.assertLessEqual(len(snap["line"]), 40)

    def test_B3_three_independent_steps_same_first_wave(self):
        plan = [
            {"id": "s1", "after": [], "tool": "whatsapp_send", "device": "phone"},
            {"id": "s2", "after": [], "tool": "play_music", "device": "phone"},
            {"id": "s3", "after": [], "tool": "mail_compose", "device": "phone"},
        ]
        result = AGENTS.waves(plan)
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)
        first = result[0]
        self.assertIsInstance(first, list)
        for sid in ("s1", "s2", "s3"):
            self.assertIn(sid, first)
        # Derive agent names then build the wave line.
        try:
            spawned = AGENTS.spawn(plan)
            names = [s.get("name", "") for s in spawned if isinstance(s, dict)]
        except Exception:
            names = [AGENTS.agent_name(s.get("tool"), s.get("device")) for s in plan]
        if not names or not any(names):
            names = ["whatsapp", "music", "mail"]
        line = AGENTS.wave_line(names)
        self.assertIsInstance(line, str)
        self.assertLessEqual(len(line), 40)
        low = line.lower()
        hits = sum(1 for token in ("whatsapp", "music", "mail") if token in low)
        self.assertGreaterEqual(hits, 2)

    def test_B4_fail_independent_keeps_other_agent(self):
        plan = [
            {"id": "s1", "after": [], "tool": "whatsapp_send", "device": "phone"},
            {"id": "s2", "after": [], "tool": "play_music", "device": "phone"},
        ]
        remaining = AGENTS.fail_independent(plan, "s1")
        self.assertIsInstance(remaining, list)
        ids = [s.get("id") for s in remaining if isinstance(s, dict)]
        self.assertIn("s2", ids)
        self.assertNotIn("s1", ids)
        # Island: independent fail keeps the other agent listed.
        ISLAND.reset()
        try:
            spawned = AGENTS.spawn(plan)
            names = [s.get("name", "") for s in spawned if isinstance(s, dict) and s.get("name")]
        except Exception:
            names = []
        if len(names) < 2:
            names = ["whatsapp", "music"]
        first, other = names[0], names[1]
        ISLAND.set_state("wave", agents=names)
        ISLAND.mark_fail(first)
        snap = ISLAND.snapshot()
        self.assertEqual(snap["state"], "fail")
        self.assertIn(other, snap["agents"])


if __name__ == "__main__":
    unittest.main()
