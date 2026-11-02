"""Door mailbox tests — stdlib unittest only, no network, no sockets.

Covers:
  - utterance in a thread + pull + put_result -> waiter gets phone_steps
  - health false (no pull yet) then true after pull
  - wrong/missing token -> unauthorized when MARC_TOKEN set;
    open mode when MARC_TOKEN empty (mirrors marc-muse)
"""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mailbox


class MailboxFlowTest(unittest.TestCase):
    def test_utterance_pull_result_thread(self):
        store = {}
        box = mailbox.Mailbox(backend=store)
        got = {}

        def waiter():
            jid = box.put_utterance("hello door", "phone")
            got["job_id"] = jid
            got["result"] = box.wait_result(jid, timeout_s=10)

        th = threading.Thread(target=waiter)
        th.start()

        # Bridge side: long-poll picks up the job.
        job = box.pull(timeout_s=10)
        self.assertIsNotNone(job)
        self.assertEqual(job["text"], "hello door")
        self.assertEqual(job["id"], got.get("job_id") or job["id"])

        box.put_result(job["id"], {"ok": True, "spoken": "hi",
                                   "phone_steps": ["say hi"],
                                   "reply": "hi"})
        th.join(timeout=10)
        self.assertFalse(th.is_alive())
        self.assertIsNotNone(got.get("result"))
        self.assertEqual(got["result"].get("phone_steps"), ["say hi"])
        self.assertEqual(got["result"].get("spoken"), "hi")

    def test_pull_timeout_returns_none(self):
        box = mailbox.Mailbox(backend={})
        self.assertIsNone(box.pull(timeout_s=0.1))
        self.assertIsNone(box.wait_result("nope", timeout_s=0.1))

    def test_health_false_then_true_after_pull(self):
        box = mailbox.Mailbox(backend={})
        h0 = box.health()
        self.assertTrue(h0["ok"])
        self.assertFalse(h0["bridge_seen"])
        self.assertIsNone(h0["bridge_seen_s"])
        box.pull(timeout_s=0.1)
        h1 = box.health()
        self.assertTrue(h1["bridge_seen"])
        self.assertIsNotNone(h1["bridge_seen_s"])
        self.assertLess(h1["bridge_seen_s"], 30.0)


class AuthTest(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("MARC_TOKEN")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("MARC_TOKEN", None)
        else:
            os.environ["MARC_TOKEN"] = self._old

    def test_open_mode_when_no_token(self):
        os.environ.pop("MARC_TOKEN", None)
        self.assertTrue(mailbox.is_authorized({}))
        self.assertTrue(mailbox.is_authorized(
            {"Authorization": "Bearer anything"}))

    def test_wrong_token_401(self):
        os.environ["MARC_TOKEN"] = "secret123"
        # Missing / wrong -> unauthorized (server maps this to 401).
        self.assertFalse(mailbox.is_authorized({}))
        self.assertFalse(mailbox.is_authorized(
            {"Authorization": "Bearer wrong"}))
        self.assertFalse(mailbox.is_authorized(
            {"authorization": "Bearer wrong"}))
        # Right token (either case) -> authorized.
        self.assertTrue(mailbox.is_authorized(
            {"Authorization": "Bearer secret123"}))
        self.assertTrue(mailbox.is_authorized(
            {"authorization": "Bearer secret123"}))
        # Compat alias mirrored from marc-muse.
        self.assertTrue(mailbox.is_authorized(
            {"X-Marc-Token": "secret123"}))


if __name__ == "__main__":
    unittest.main()
