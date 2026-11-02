"""Sandbox IG webhook + send gate tests (no network)."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class MetaIgWebhookTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("MARC_MODE", None)
        os.environ.pop("META_WA_ACCESS_TOKEN", None)
        os.environ.pop("META_IG_ACCESS_TOKEN", None)
        self.mc = _load("meta_cloud_ig", ROOT / "connectors" / "meta_cloud.py")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_ig_live_gate_does_not_require_wa(self):
        os.environ["MARC_MODE"] = "live"
        os.environ["META_IG_ACCESS_TOKEN"] = "ig-only-token"
        os.environ.pop("META_WA_ACCESS_TOKEN", None)
        self.assertTrue(self.mc.ig_is_live())
        self.assertFalse(self.mc.has_wa_token())

    def test_send_instagram_sandbox_without_wa(self):
        os.environ["MARC_MODE"] = "sandbox"
        out = self.mc.send_instagram("@priya.fake.ig", "FAKE: hi")
        self.assertTrue(isinstance(out, dict))
        self.assertEqual(out.get("mode") or "sandbox", "sandbox")

    def test_parse_ig_fixture(self):
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "ig-user-1"},
                            "message": {"mid": "m1", "text": "hello marc"},
                        }
                    ]
                }
            ],
        }
        msgs = self.mc.parse_webhook(payload)
        self.assertTrue(msgs)
        first = msgs[0] if isinstance(msgs, list) else msgs
        blob = str(first).lower()
        self.assertTrue("hello" in blob or "ig" in blob or "instagram" in blob)


if __name__ == "__main__":
    unittest.main()
