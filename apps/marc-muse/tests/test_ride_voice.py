"""Ride voice tests A (wake) and F (confirm/refuse) — stdlib unittest, no network.

Run:
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

# APP_ROOT is parent of tests/ (i.e. apps/marc-muse), like test_ride_env.py.
APP_ROOT = Path(__file__).resolve().parent.parent

# Ensure sibling imports (config, credit) resolve for context/planner.
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules like test_ride_env.py (dataclasses-safe).
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


VOICE_GATE = _load("voice_gate_under_test", APP_ROOT / "voice_gate.py")
CONTEXT = _load("context_under_test", APP_ROOT / "context.py")
PLANNER = _load("planner_under_test", APP_ROOT / "planner.py")

# Also register under short names for modules that probe them.
sys.modules.setdefault("voice_gate", VOICE_GATE)
sys.modules.setdefault("context", CONTEXT)
sys.modules.setdefault("planner", PLANNER)


class RideVoiceBase(unittest.TestCase):
    def setUp(self):
        self._saved_env = dict(os.environ)
        self._tmp = tempfile.TemporaryDirectory()
        mind = str(Path(self._tmp.name) / "mind")
        os.environ["MARC_MODE"] = "sandbox"
        os.environ["MODE"] = "sandbox"
        os.environ["MARC_MIND_DIR"] = mind
        os.environ["MIND_DIR"] = mind
        # Never hit Muse spark / network.
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("MARC_SPARK_URL", None)
        os.environ.pop("MODEL_API_URL", None)
        os.environ.pop("MARC_CREDIT_PAUSED", None)
        os.environ.pop("MARC_BUDGET_PAUSED", None)
        os.environ.pop("MARC_SPARK_PAUSED", None)
        os.environ.pop("MARC_CREDIT_REMAINING", None)
        # Belt-and-braces: disable the network for every test.
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("network must not be used in ride voice tests")

        urllib.request.urlopen = _no_network  # type: ignore[assignment]
        try:
            PLANNER.clear_stopped()
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
        os.environ.update(self._saved_env)
        try:
            self._tmp.cleanup()
        except Exception:
            pass


class WakeTests(RideVoiceBase):
    def test_A1_hey_marc_wake(self):
        r = VOICE_GATE.classify("hey marc")
        self.assertEqual(r["intent"], "wake")

    def test_A1_hey_jarvis_wake(self):
        r = VOICE_GATE.classify("hey jarvis")
        self.assertEqual(r["intent"], "wake")

    def test_A1_remark_wake(self):
        r = VOICE_GATE.classify("remark")
        self.assertEqual(r["intent"], "wake")

    def test_A1_all_wake(self):
        for text in ("hey marc", "hey jarvis", "remark"):
            with self.subTest(text=text):
                self.assertEqual(VOICE_GATE.classify(text)["intent"], "wake")

    def test_A2_hey_mark_my_calendar_ignore(self):
        r = VOICE_GATE.classify("hey mark my calendar")
        self.assertEqual(r["intent"], "ignore")

    def test_A3_hey_marc_driving_wake(self):
        r = VOICE_GATE.classify("hey marc", context="driving")
        self.assertEqual(r["intent"], "wake")
        self.assertEqual(r.get("context"), "driving")

    def test_A4_sleep_goodbye_stop_marc(self):
        for text in ("sleep", "goodbye", "stop Marc"):
            with self.subTest(text=text):
                r = VOICE_GATE.classify(text)
                self.assertEqual(r["intent"], "sleep")

    def test_A4_stop_marc_calls_stop(self):
        try:
            PLANNER.clear_stopped()
            res = PLANNER.plan("stop Marc")
            self.assertIsInstance(res, dict)
            # Wire voice-gate stop to planner stop.
            PLANNER.set_stopped()
            self.assertTrue(PLANNER.is_stopped())
        finally:
            PLANNER.clear_stopped()
        self.assertFalse(PLANNER.is_stopped())

    def test_pending_confirm_yes_confirmed(self):
        r = VOICE_GATE.classify("yes", pending_confirm=True)
        self.assertEqual(r["intent"], "confirm")
        confirmed = r["intent"] == "confirm"
        self.assertTrue(confirmed)

    def test_pending_confirm_cancel_cancelled(self):
        r = VOICE_GATE.classify("cancel", pending_confirm=True)
        self.assertEqual(r["intent"], "cancel")
        cancelled = r["intent"] == "cancel"
        self.assertTrue(cancelled)


class ConfirmRefuseTests(RideVoiceBase):
    def test_F1_open_spotify_driving_short(self):
        res = PLANNER.plan("open Spotify", context="driving")
        reply = str(res.get("reply") or "")
        # At most one '.' sentence and len<=80 (driving voice budget).
        self.assertLessEqual(len(reply), 80)
        self.assertLessEqual(reply.count("."), 1)
        sentences = [s for s in reply.split(".") if s.strip()]
        self.assertLessEqual(len(sentences), 1)

    def test_F2_driving_voice_confirm_no_chip(self):
        prof = CONTEXT.profile("driving")
        self.assertEqual(prof["confirm_via"], "voice")
        self.assertIs(prof["chip_allowed"], False)
        prompt = CONTEXT.confirm_prompt("mail_send")
        self.assertIsInstance(prompt, str)
        self.assertLessEqual(len(prompt), 40)
        low = prompt.lower()
        self.assertTrue("yes" in low or "cancel" in low)

    def test_F3_hop_cap_driving_6_desk_8(self):
        self.assertEqual(CONTEXT.profile("driving")["hop_cap"], 6)
        self.assertEqual(CONTEXT.profile("desk")["hop_cap"], 8)

    def test_F4_bt_fixture_utterance(self):
        r = VOICE_GATE.classify("play the driving playlist")
        self.assertEqual(r["intent"], "utterance")
        # Same for source-less BT fixture across contexts.
        a = VOICE_GATE.classify("play the driving playlist", context="desk")
        b = VOICE_GATE.classify("play the driving playlist", context="driving")
        self.assertEqual(a["intent"], "utterance")
        self.assertEqual(b["intent"], "utterance")
        self.assertEqual(a["intent"], b["intent"])

    def test_F5_reboot_refused_driving(self):
        try:
            res = PLANNER.plan("reboot the laptop", context="driving")
            self.assertEqual(res.get("plan"), [])
            reply = str(res.get("reply") or "").lower()
            self.assertTrue(
                "can't" in reply or "cannot" in reply or "refuse" in reply or "can't do" in reply,
                "refuse reply expected, got %r" % res.get("reply"),
            )
        finally:
            PLANNER.clear_stopped()


if __name__ == "__main__":
    unittest.main()
