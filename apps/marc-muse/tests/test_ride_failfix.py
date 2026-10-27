"""Ride fail-fix tests H1-H4 — stdlib unittest, no network.

Run:
  python -m unittest discover -s apps/marc-muse/tests -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


FAST = _load("fast_path", APP_ROOT / "fast_path.py")
ISLAND = _load("island", APP_ROOT / "island.py")
PLANNER = _load("planner", APP_ROOT / "planner.py")
EXECUTOR = _load("executor", APP_ROOT / "executor.py")


def _music(i):
    return {
        "id": "s%d" % i,
        "after": [],
        "kind": "once",
        "device": "phone",
        "tool": "play_music",
        "args": {"query": "track %d" % i},
        "confirm": False,
    }


class RideFailFixTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(os.environ)
        self._tmp = tempfile.TemporaryDirectory()
        mind = str(Path(self._tmp.name) / "mind")
        os.environ["MARC_MODE"] = "sandbox"
        os.environ["MODE"] = "sandbox"
        os.environ["MARC_MIND_DIR"] = mind
        os.environ["MIND_DIR"] = mind
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("MARC_SPARK_URL", None)
        os.environ.pop("MODEL_API_URL", None)
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("network must not be used in ride fail-fix tests")

        urllib.request.urlopen = _no_network  # type: ignore[assignment]
        try:
            PLANNER.clear_stopped()
        except Exception:
            pass
        try:
            ISLAND.reset()
        except Exception:
            pass

    def tearDown(self):
        try:
            urllib.request.urlopen = self._real_urlopen  # type: ignore[assignment]
        except Exception:
            pass
        try:
            PLANNER.clear_stopped()
        except Exception:
            pass
        os.environ.clear()
        os.environ.update(self._saved)
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    def test_H1_stop_aborts_waves(self):
        try:
            PLANNER.set_stopped()
            out = EXECUTOR.execute_plan([_music(1), _music(2)])
            self.assertTrue(out.get("stopped") or (out.get("remaining") or []))
        finally:
            PLANNER.clear_stopped()

    def test_H2_regex_skips_muse(self):
        self.assertTrue(FAST.skip_muse("open Spotify"))
        self.assertFalse(FAST.skip_muse("email myself the recap"))
        self.assertTrue(FAST.skip_muse("type hello"))
        self.assertTrue(FAST.skip_muse("youtube cats"))

    def test_H3_budget_island_local_still_skips(self):
        os.environ["MARC_CREDIT_DAILY_CAP"] = "0"
        res = PLANNER.plan("remember the grocery list")
        reply = str(res.get("reply") or "").lower()
        self.assertTrue("budget" in reply or "paused" in reply)
        line = FAST.island_budget_line()
        ISLAND.set_state("fail", line=line)
        snap = ISLAND.snapshot()
        self.assertLessEqual(len(snap.get("line") or ""), 40)
        self.assertIn("budget", (snap.get("line") or "").lower())
        self.assertTrue(FAST.skip_muse("open Spotify"))

    def test_H4_hop_budget_caps_results(self):
        os.environ["MARC_MAX_HOPS"] = "6"
        os.environ["MARC_PLAN_MAX_HOPS"] = "6"
        os.environ["MARC_HARD_HOPS"] = "6"
        os.environ["MARC_PLAN_HARD_HOPS"] = "6"
        steps = [_music(i) for i in range(1, 13)]
        out = EXECUTOR.execute_plan(steps)
        self.assertLessEqual(len(out.get("results") or []), 6)
        self.assertTrue(FAST.hop_cap_exceeded(6, 6))


if __name__ == "__main__":
    unittest.main()
