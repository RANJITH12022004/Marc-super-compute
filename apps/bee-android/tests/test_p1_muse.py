"""P1 Muse client + vault — stdlib unittest, no network, no real keys."""

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


C = _load("muse_client")
S = _load("muse_store")


class P1MuseClientTests(unittest.TestCase):
    def test_models(self):
        self.assertEqual(C.SPARK, "muse-spark-1.3")
        self.assertEqual(C.WONDER, "muse-wonder-1.0")
        self.assertEqual(C.VOICE, "muse-voice-transcribe-1.0")
        self.assertEqual(C.RESPONSES_URL, "https://api.meta.ai/v1/responses")

    def test_capture_response_id_not_event_id(self):
        evt = {"id": "evt_1", "response": {"id": "resp_9"}}
        self.assertEqual(C.capture_response_id(evt), "resp_9")

    def test_redact_authorization(self):
        headers = C.build_headers("sk-secret-example")
        redacted = C.redact(headers)
        self.assertEqual(redacted["Authorization"], "Bearer ***")
        self.assertNotIn("sk-secret-example", str(redacted))

    def test_expired_ref(self):
        self.assertTrue(C.is_expired_ref("referenced response not found"))
        self.assertTrue(C.is_expired_ref("previous_response_id expired"))

    def test_user_message_shape(self):
        msg = C.user_message("hello")
        self.assertEqual(msg["type"], "message")
        self.assertEqual(msg["role"], "user")
        self.assertEqual(msg["content"][0]["type"], "input_text")


class P1MuseStoreTests(unittest.TestCase):
    def test_mask_key_never_full(self):
        raw = "LLM_abcdefghijk"
        mask = S.mask_key(raw)
        self.assertNotEqual(mask, raw)
        self.assertNotIn(raw, mask)
        self.assertTrue(mask.endswith("hijk"))

    def test_needle_off(self):
        self.assertFalse(S.needle_enabled())

    def test_default_models(self):
        models = S.default_models()
        self.assertEqual(models["spark"], "muse-spark-1.3")
        self.assertEqual(models["wonder"], "muse-wonder-1.0")
        self.assertEqual(models["voice"], "muse-voice-transcribe-1.0")

    def test_save_rejects_empty(self):
        with self.assertRaises(ValueError):
            S.save_key({}, "")


if __name__ == "__main__":
    unittest.main()
