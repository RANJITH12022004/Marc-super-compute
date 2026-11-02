"""Unittest for the local cognee memory adapter. No network required."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from apps.server.cognee import forget, recall, remember  # noqa: E402
from apps.server.cognee import memory as mem  # noqa: E402


class TestMemory(unittest.TestCase):
    def setUp(self):
        mem._clear_store()

    def tearDown(self):
        mem._clear_store()

    def test_dataset_isolation(self):
        # remember in personal, recall in project_foo does not see it.
        remember("pineapple skylark personal-only note", dataset="personal")
        res = recall("pineapple skylark", datasets=["project_foo"])
        self.assertTrue(res["ok"])
        self.assertEqual(res["hits"], [])
        self.assertEqual(res["text"], "")
        # ...and personal recall does see it.
        res2 = recall("pineapple skylark", datasets=["personal"])
        self.assertTrue(any("pineapple skylark" in h["text"] for h in res2["hits"]))

    def test_secret_redaction(self):
        remember("hello line\nAuthorization: Bearer SECRET-ABC-123\nbye line")
        res = recall("hello", datasets=["personal"])
        joined = res["text"] + "".join(h["text"] for h in res["hits"])
        self.assertNotIn("SECRET-ABC-123", joined)
        self.assertNotIn("Bearer", joined)

    def test_forget_removes(self):
        remember("forgettable zebra tango line", dataset="personal")
        before = recall("forgettable zebra", datasets=["personal"])
        self.assertTrue(any("forgettable zebra" in h["text"] for h in before["hits"]))
        forget("forgettable zebra", dataset="personal")
        after = recall("forgettable zebra", datasets=["personal"])
        self.assertEqual(after["hits"], [])
        self.assertEqual(after["text"], "")


if __name__ == "__main__":
    unittest.main()
