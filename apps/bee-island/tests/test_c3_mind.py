"""C3 mind unittest (importlib-loaded, stdlib only, no network, no Android)."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEE_MIND_PATH = ROOT / "bee_mind.py"
MUSE_TOOLS_PATH = ROOT / "muse_tools.py"

ME_FIXTURE = "Name: Ranjith\nRole: Bee keeper\nLoves honey and offline notes.\n"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bee_mind = _load_module(BEE_MIND_PATH, "bee_mind")
muse_tools = _load_module(MUSE_TOOLS_PATH, "muse_tools")


class C3MindTests(unittest.TestCase):
    def test_who_am_i_from_fixture(self):
        result = bee_mind.who_am_i(ME_FIXTURE)
        self.assertTrue(isinstance(result, str))
        self.assertTrue(len(result.strip()) > 0)
        self.assertIn("Ranjith", result)

    def test_who_am_i_offline_cache(self):
        cache_str = "cached-me-fallback-Ranjith"
        result = bee_mind.who_am_i("", cache_str)
        self.assertTrue(isinstance(result, str))
        self.assertTrue(len(result.strip()) > 0)
        self.assertIn(cache_str, result)
        # kw fallback form also returns cache
        result_kw = bee_mind.who_am_i("", fallback=cache_str)
        self.assertTrue(isinstance(result_kw, str))
        self.assertIn(cache_str, result_kw)

    def test_inject_context_no_secrets(self):
        me = "Name: Ranjith\nAuthorization: Bearer sk-secret123\nLikes bees"
        now = "Working on tests\nAuthorization: Bearer sk-other456"
        result = bee_mind.inject_context(me, now)
        self.assertTrue(isinstance(result, str))
        self.assertNotIn("Authorization", result)
        self.assertNotIn("Bearer sk-", result)

    def test_inject_context_includes_failed(self):
        me = ME_FIXTURE
        now = "Working on bee tests"
        fake = "fake-failed-line-xyz-987"
        result = bee_mind.inject_context(me, now, failed_text=fake)
        self.assertTrue(isinstance(result, str))
        self.assertIn(fake, result)
        # list form
        result_list = bee_mind.inject_context(me, now, failed_lines=[fake])
        self.assertIn(fake, result_list)
        # cache-dict form
        result_cache = bee_mind.inject_context(
            me, now, {"FAILED.md": fake})
        self.assertIn(fake, result_cache)
        # last-5 window: oldest lines dropped
        many = "\n".join("fail-line-%d" % i for i in range(7))
        result_many = bee_mind.inject_context(me, now, failed_text=many)
        self.assertIn("fail-line-6", result_many)
        self.assertNotIn("fail-line-0", result_many)
        self.assertNotIn("fail-line-1", result_many)
        # secrets still stripped from failed, clamp holds
        result_sec = bee_mind.inject_context(
            me, now,
            failed_text="Authorization: Bearer sk-fail999\n" + fake)
        self.assertIn(fake, result_sec)
        self.assertNotIn("Authorization", result_sec)
        self.assertLessEqual(len(result_sec), 800)
        # failed appears after ME+NOW
        self.assertLess(result.find("Ranjith"), result.find(fake))

    def test_payload_no_auth_and_redact(self):
        payload = muse_tools.build_complete_payload(muse_tools.SPARK, "hello")
        self.assertTrue(isinstance(payload, dict))
        self.assertNotIn("Authorization", payload)
        self.assertNotIn("Authorization", json.dumps(payload))
        headers = muse_tools.build_headers("sk-test123")
        redacted = muse_tools.redact(headers)
        self.assertEqual(redacted.get("Authorization"), "Bearer ***")

    def test_classify_mind(self):
        self.assertEqual(bee_mind.classify_mind("who am I"), "whoami")
        self.assertIsNone(bee_mind.classify_mind("open Spotify"))


if __name__ == "__main__":
    unittest.main()
