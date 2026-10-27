"""P2 ask DAG — skip_muse, compound tools, refuse, island lines."""

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


A = _load("bee_ask")
I = _load("bee_island")

COMPOUND = (
    "Text Amma I am leaving now, play A.R. Rahman on Spotify, "
    "and email the office I am on the way"
)


class P2AskTests(unittest.TestCase):
    def test_skip_muse_open_spotify(self):
        self.assertTrue(A.skip_muse("open Spotify"))

    def test_skip_muse_compound_demo_false(self):
        self.assertFalse(A.skip_muse(COMPOUND))
        self.assertFalse(A.skip_muse("open Spotify then demo youtube"))

    def test_compound_three_tools_music_independent(self):
        steps = A.split_utterance(COMPOUND)
        tools = [s["tool"] for s in steps]
        self.assertEqual(len(tools), 3)
        self.assertEqual(tools[0], "whatsapp_send")
        self.assertIn(tools[1], ("music_play", "play_music"))
        self.assertEqual(tools[2], "mail_compose")
        music = [s for s in steps if s["tool"] in ("music_play", "play_music")][0]
        self.assertEqual(music["after"], [])

    def test_then_chain_links_after(self):
        steps = A.split_utterance("text Amma hi then play Rahman")
        self.assertGreaterEqual(len(steps), 2)
        self.assertIn(steps[0]["id"], steps[1]["after"])

    def test_refuse_reboot_empty(self):
        plan = A.plan_ask("please reboot the phone")
        self.assertEqual(plan["steps"], [])
        self.assertEqual(A.classify_voice("reboot now")["kind"], "refuse")

    def test_island_listen_budget(self):
        line = I.line_for("listen")
        self.assertLessEqual(len(line), 40)
        self.assertTrue(line.startswith("Listen"))


if __name__ == "__main__":
    unittest.main()
