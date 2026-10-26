"""Meta Cloud sandbox tests — FAKE numbers only, no network."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class MetaCloudSandboxTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["MARC_MIND_DIR"] = self._td.name
        os.environ["MARC_MODE"] = "sandbox"
        os.environ.pop("META_WA_ACCESS_TOKEN", None)
        os.environ.pop("META_APP_SECRET", None)

    def tearDown(self):
        self._td.cleanup()

    def test_send_whatsapp_is_draft(self):
        import drafts
        from connectors import meta_cloud

        rec = meta_cloud.send_whatsapp("+1-555-0102", "FAKE: hi priya")
        self.assertTrue(rec.get("ok", True) or rec.get("id") or rec.get("draft"))
        listed = drafts.list_drafts()
        self.assertTrue(listed, "sandbox send must enqueue a draft")
        body = str(listed[0])
        self.assertNotIn("graph.facebook.com", body.lower())

    def test_parse_webhook_whatsapp_sample(self):
        from connectors import meta_cloud

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15550102",
                                        "id": "wamid.FAKE",
                                        "type": "text",
                                        "text": {"body": "FAKE: ping"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        parsed = meta_cloud.parse_webhook(payload)
        msgs = parsed if isinstance(parsed, list) else getattr(parsed, "messages", None) or parsed.get("messages")
        self.assertTrue(msgs)

    def test_verify_signature_sandbox_without_secret(self):
        from connectors import meta_cloud

        self.assertTrue(meta_cloud.verify_signature(b"{}", "sha256=deadbeef"))


if __name__ == "__main__":
    unittest.main()
