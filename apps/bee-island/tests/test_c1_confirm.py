"""C1 confirm unittest (importlib-loaded, stdlib only, no network, no Android)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEE_CONTROL_PATH = ROOT / "bee_control.py"

COMPOUND = "Text Amma I am leaving now, play A.R. Rahman on Spotify, and email the office I am on the way"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bee_control = _load_module(BEE_CONTROL_PATH, "bee_control")


class C1ConfirmTests(unittest.TestCase):
    def test_skip_muse_open_spotify_prompt(self):
        self.assertTrue(bee_control.skip_muse("open Spotify") is True)
        steps = bee_control.split_utterance("open Spotify")
        prompt = bee_control.this_or_that(steps)
        self.assertTrue(isinstance(prompt, str))
        self.assertTrue(len(prompt.strip()) > 0)
        self.assertNotEqual(prompt, "execute")
        self.assertNotEqual(prompt.strip().lower(), "execute")

    def test_compound_three_tools_ask_not_run(self):
        steps = bee_control.split_utterance(COMPOUND)
        self.assertEqual(len(steps), 3)
        prompt = bee_control.this_or_that(steps)
        self.assertTrue(isinstance(prompt, str))
        self.assertTrue(len(prompt.strip()) > 0)
        decision = bee_control.decide("ask", steps)
        self.assertEqual(decision.get("action"), "ask")
        self.assertNotEqual(decision.get("action"), "run")

    def test_plan_ask_reboot_refuse(self):
        plan = bee_control.plan_ask("please reboot the phone")
        self.assertEqual(plan.get("steps"), [])
        decision = bee_control.decide(plan.get("kind"), plan.get("steps"))
        self.assertEqual(decision.get("action"), "refuse")
        # direct kind check as well
        self.assertEqual(bee_control.decide("refuse", []).get("action"), "refuse")

    def test_decide_confirm_empty_ack(self):
        decision = bee_control.decide("confirm", [])
        self.assertEqual(decision.get("action"), "ack")

    def test_decide_confirm_one_run(self):
        one = [{"id": "s1", "tool": "open_app", "args": {"app": "Spotify"}, "device": "phone", "after": []}]
        decision = bee_control.decide("confirm", one)
        self.assertEqual(decision.get("action"), "run")

    def test_decide_ask_empty_ack(self):
        decision = bee_control.decide("ask", [])
        self.assertEqual(decision.get("action"), "ack")


if __name__ == "__main__":
    unittest.main()
