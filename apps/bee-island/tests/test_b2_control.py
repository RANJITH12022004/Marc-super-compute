"""B2 control unittest (importlib-loaded, stdlib only, no network, no Android)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSE_TOOLS_PATH = Path(__file__).resolve().parents[1] / "muse_tools.py"
BEE_CONTROL_PATH = Path(__file__).resolve().parents[1] / "bee_control.py"
PHONE_ACTIONS_PATH = Path(__file__).resolve().parents[1] / "phone_actions.py"

COMPOUND = "Text Amma I am leaving now, play A.R. Rahman on Spotify, and email the office I am on the way"
SECRET = "sk-secret-example"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


muse_tools = _load_module(MUSE_TOOLS_PATH, "muse_tools")
bee_control = _load_module(BEE_CONTROL_PATH, "bee_control")
if PHONE_ACTIONS_PATH.is_file():
    phone_actions = _load_module(PHONE_ACTIONS_PATH, "phone_actions")
else:
    phone_actions = None


class B2ControlTests(unittest.TestCase):
    def test_skip_muse_open_spotify(self):
        self.assertTrue(bee_control.skip_muse("open Spotify") is True)

    def test_compound_split_utterance(self):
        steps = bee_control.split_utterance(COMPOUND)
        self.assertEqual(len(steps), 3)
        tools = [s.get("tool") for s in steps]
        self.assertEqual(tools, ["whatsapp_send", "play_music", "mail_compose"])
        music = [s for s in steps if s.get("tool") == "play_music"]
        self.assertEqual(len(music), 1)
        self.assertEqual(music[0].get("after"), [])

    def test_plan_ask_reboot_refuse(self):
        plan = bee_control.plan_ask("please reboot the phone")
        self.assertEqual(plan.get("steps"), [])
        cv = bee_control.classify_voice("please reboot the phone")
        self.assertEqual(cv.get("kind"), "refuse")
        cv2 = bee_control.classify_voice("reboot")
        self.assertEqual(cv2.get("kind"), "refuse")

    def test_headers_redacted(self):
        headers = muse_tools.build_headers(SECRET)
        redacted = muse_tools.redact(headers)
        self.assertNotIn(SECRET, str(redacted))
        for v in redacted.values():
            self.assertNotIn(SECRET, str(v))
        self.assertEqual(redacted.get("Authorization"), "Bearer ***")

    def test_parse_fixture_no_secret(self):
        fixture = {
            "output": [
                {
                    "type": "function_call",
                    "name": "open_app",
                    "arguments": '{"app": "Spotify"}',
                },
                {
                    "type": "function_call",
                    "name": "play_music",
                    "arguments": '{"query": "A.R. Rahman"}',
                },
            ]
        }
        steps = muse_tools.parse_function_calls(fixture)
        self.assertTrue(len(steps) >= 1)
        self.assertNotIn(SECRET, str(steps))

    def test_dispatch_laptop_offline(self):
        steps = [
            {"id": "s1", "tool": "open_app", "args": {"app": "Spotify"}, "device": "phone", "after": []},
            {"id": "s2", "tool": "type_into", "args": {"text": "hello"}, "device": "laptop", "after": []},
        ]
        phone_calls = []

        def run_phone(step):
            phone_calls.append(step)
            return {"id": step.get("id"), "ok": True, "tool": step.get("tool")}

        laptop_calls = []

        def run_laptop(step):
            laptop_calls.append(step)
            return {"id": step.get("id"), "ok": True}

        results = bee_control.dispatch(steps, run_phone, run_laptop, laptop_ok=False)
        self.assertEqual(len(phone_calls), 1)
        self.assertEqual(len(laptop_calls), 0)
        self.assertIn("laptop offline", str(results).lower())
        # phone result must be present alongside the offline entry
        phone_results = [r for r in results if isinstance(r, dict) and r.get("id") == "s1"]
        self.assertEqual(len(phone_results), 1)
        self.assertTrue(phone_results[0].get("ok") is True)
        offline = [r for r in results if isinstance(r, dict) and "laptop offline" in str(r).lower()]
        self.assertTrue(len(offline) >= 1)


if __name__ == "__main__":
    unittest.main()
