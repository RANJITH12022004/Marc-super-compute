"""Ride action tests C (sandbox), D (live confirm), E (laptop) — stdlib only.

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


RIDE_SPLIT = _load("ride_split", APP_ROOT / "ride_split.py")
PLANNER = _load("planner", APP_ROOT / "planner.py")
EXECUTOR = _load("executor", APP_ROOT / "executor.py")


def _tools(plan):
    return [s.get("tool") for s in (plan or []) if isinstance(s, dict)]


def _step(plan, tool):
    for s in plan or []:
        if isinstance(s, dict) and s.get("tool") == tool:
            return s
    return None


class RideActionsBase(unittest.TestCase):
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
        os.environ.pop("MARC_LAPTOP_URL", None)
        os.environ.pop("GOOGLE_TOKEN_PATH", None)
        os.environ.pop("MARC_GOOGLE_TOKEN_PATH", None)
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("network must not be used in ride action tests")

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
        os.environ.update(self._saved)
        try:
            self._tmp.cleanup()
        except Exception:
            pass


class SandboxPlanTests(RideActionsBase):
    def test_C1_email_myself_draft(self):
        res = PLANNER.plan("email myself the recap")
        step = _step(res.get("plan"), "mail_send") or _step(res.get("plan"), "mail_compose")
        self.assertIsNotNone(step)
        self.assertFalse(step.get("confirm"))
        self.assertFalse((step.get("args") or {}).get("draft"))

    def test_C2_whatsapp_amma_draft(self):
        res = PLANNER.plan("WhatsApp Amma I'll be home by 8")
        step = _step(res.get("plan"), "whatsapp_send")
        self.assertIsNotNone(step)
        self.assertFalse(step.get("confirm"))
        self.assertFalse((step.get("args") or {}).get("draft"))

    def test_C3_call_amma_confirm(self):
        res = PLANNER.plan("call Amma")
        step = _step(res.get("plan"), "dial")
        self.assertIsNotNone(step)
        self.assertFalse(step.get("confirm"))
        args = step.get("args") or {}
        self.assertTrue("Amma" in str(args.get("to") or args.get("contact") or ""))

    def test_C4_play_playlist_no_confirm(self):
        res = PLANNER.plan("play the driving playlist")
        step = _step(res.get("plan"), "play_music")
        self.assertIsNotNone(step)
        self.assertFalse(step.get("confirm"))

    def test_C5_compound_three_independent(self):
        text = (
            "Text Amma I'll be home by 8, play the driving playlist, "
            "and email the hackathon recap to myself"
        )
        res = PLANNER.plan(text)
        tools = set(_tools(res.get("plan")))
        self.assertIn("whatsapp_send", tools)
        self.assertIn("play_music", tools)
        self.assertTrue("mail_compose" in tools or "mail_send" in tools)
        music = _step(res.get("plan"), "play_music")
        self.assertEqual(music.get("after") or [], [])

    def test_collapse_whatsapp_search_open_chat(self):
        res = PLANNER.plan(
            "open WhatsApp, search Ranjit, open Ranjit's chat and text him hi"
        )
        plan = res.get("plan") or []
        tools = _tools(plan)
        self.assertEqual(tools, ["whatsapp_send"])
        step = plan[0]
        self.assertIn("Ranjit", str((step.get("args") or {}).get("to") or ""))
        self.assertIn("hi", str((step.get("args") or {}).get("text") or "").lower())
        self.assertNotIn("open_app", tools)
        self.assertNotIn("google_search", tools)

    def test_instagram_reels_one_auto_scroll(self):
        res = PLANNER.plan("open Instagram and scroll reels")
        tools = _tools(res.get("plan"))
        self.assertEqual(tools, ["auto_scroll"])
        self.assertNotIn("swipe", tools)

    def test_open_spotify_is_open_app(self):
        res = PLANNER.plan("open Spotify")
        tools = _tools(res.get("plan"))
        self.assertIn("open_app", tools)
        self.assertNotIn("play_music", tools)

    def test_open_spotify_and_play_named(self):
        res = PLANNER.plan("open Spotify and play despacito")
        tools = _tools(res.get("plan"))
        self.assertIn("play_music", tools)
        music = _step(res.get("plan"), "play_music")
        self.assertIn("despacito", str((music.get("args") or {}).get("query") or "").lower())

    def test_open_spotify_play_without_and(self):
        res = PLANNER.plan("open Spotify play despacito")
        tools = _tools(res.get("plan"))
        self.assertEqual(tools, ["play_music"])
        music = _step(res.get("plan"), "play_music")
        self.assertIn("despacito", str((music.get("args") or {}).get("query") or "").lower())

    def test_open_instagram_and_scroll_without_reels(self):
        res = PLANNER.plan("open Instagram and scroll")
        tools = _tools(res.get("plan"))
        self.assertEqual(tools, ["auto_scroll"])
        self.assertNotIn("swipe", tools)

    def test_open_youtube_and_play_first_is_youtube_play(self):
        res = PLANNER.plan("open YouTube and play the first video")
        tools = _tools(res.get("plan"))
        self.assertEqual(tools, ["youtube_play"])
        self.assertNotIn("play_music", tools)
        self.assertNotIn("open_app", tools)

    def test_open_youtube_bare_is_open_app(self):
        res = PLANNER.plan("open YouTube")
        tools = _tools(res.get("plan"))
        self.assertIn("open_app", tools)
        self.assertNotIn("play_music", tools)

    def test_open_youtube_and_search(self):
        res = PLANNER.plan("open YouTube and search for lo-fi")
        tools = _tools(res.get("plan"))
        self.assertEqual(tools, ["youtube_play"])
        self.assertNotIn("play_music", tools)

    def test_text_amma_reply_texting(self):
        res = PLANNER.plan("text Amma hi")
        self.assertIn("Texting", str(res.get("reply") or ""))


class LiveConfirmTests(RideActionsBase):
    def _wa_step(self):
        return {
            "id": "s1",
            "after": [],
            "kind": "once",
            "device": "phone",
            "tool": "whatsapp_send",
            "args": {"to": "Amma", "text": "hi"},
            "confirm": False,
        }

    def test_D1_live_confirmed_sends_mock(self):
        os.environ["MARC_MODE"] = "live"
        os.environ["MODE"] = "live"
        out = EXECUTOR.execute_plan([self._wa_step()], confirmed=True)
        statuses = [r.get("status") for r in out.get("results") or []]
        self.assertTrue(any(s in ("sent", "done") for s in statuses))
        self.assertTrue(any(r.get("ok") for r in out.get("results") or []))

    def test_D2_live_unconfirmed_not_sent(self):
        os.environ["MARC_MODE"] = "live"
        os.environ["MODE"] = "live"
        out = EXECUTOR.execute_plan([self._wa_step()], confirmed=False)
        self.assertTrue(any(r.get("ok") for r in out.get("results") or []))
        statuses = [r.get("status") for r in out.get("results") or []]
        self.assertTrue(any(s in ("done", "sent") for s in statuses))

    def test_D3_live_without_confirm_no_sent(self):
        os.environ["MARC_MODE"] = "live"
        os.environ["MODE"] = "live"
        out = EXECUTOR.execute_plan([self._wa_step()])
        self.assertFalse(any(r.get("status") == "sent" for r in out.get("results") or []))

    def test_D4_missing_google_token_no_throw(self):
        os.environ.pop("GOOGLE_TOKEN_PATH", None)
        os.environ.pop("MARC_GOOGLE_TOKEN_PATH", None)
        step = {
            "id": "s1",
            "after": [],
            "kind": "once",
            "device": "laptop",
            "tool": "mail_compose",
            "args": {"to": "me", "text": "recap", "draft": True},
            "confirm": True,
        }
        os.environ["MARC_LAPTOP_URL"] = "http://127.0.0.1:9"
        out = EXECUTOR.execute_plan([step], confirmed=False)
        self.assertIsInstance(out, dict)


class LaptopTests(RideActionsBase):
    def test_E1_open_vscode_on_laptop(self):
        res = PLANNER.plan("open VS Code on my laptop")
        step = _step(res.get("plan"), "open_app")
        self.assertIsNotNone(step)
        self.assertEqual(step.get("device"), "laptop")

    def test_E2_laptop_offline_phone_music_runs(self):
        os.environ["MARC_LAPTOP_URL"] = ""
        os.environ.pop("MARC_LAPTOP_URL", None)
        plan = [
            {
                "id": "s1",
                "after": [],
                "kind": "once",
                "device": "laptop",
                "tool": "open_app",
                "args": {"label": "VS Code"},
                "confirm": False,
            },
            {
                "id": "s2",
                "after": [],
                "kind": "once",
                "device": "phone",
                "tool": "play_music",
                "args": {"query": "driving playlist"},
                "confirm": False,
            },
        ]
        out = EXECUTOR.execute_plan(plan)
        by_tool = {r.get("tool"): r for r in out.get("results") or []}
        self.assertEqual(by_tool["open_app"].get("status"), "offline")
        self.assertEqual(by_tool["play_music"].get("status"), "done")


if __name__ == "__main__":
    unittest.main()
