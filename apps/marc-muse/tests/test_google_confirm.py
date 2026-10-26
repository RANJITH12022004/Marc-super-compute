"""Google connector confirm-gate tests — FAKE fixtures only (stdlib + unittest).

Verifies:
  1. Without a token, ``compose`` creates a draft, not a send.
  2. ``calendar_create`` in sandbox is a draft (confirm-gated).
  3. No network is required (urllib disabled; offline FAKE fixtures used).

No real PII. All addresses/subjects are FAKE sandbox fixtures.

Run:
  python -m unittest test_google_confirm -v      # from apps/marc-muse/tests/
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent
GOOGLE_PATH = APP_ROOT / "connectors" / "google.py"
DRAFTS_PATH = APP_ROOT / "drafts.py"


def load_module(name: str, path: Path):
    """Load a stdlib-only module by file path (hyphen-safe)."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Ensure the app root is importable for sibling fallbacks.
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

DRAFTS = load_module("drafts", DRAFTS_PATH)
# Register under the names the google connector probes.
sys.modules.setdefault("drafts", DRAFTS)
GOOGLE = load_module("google_connector_under_test", GOOGLE_PATH)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class GoogleConfirmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert GOOGLE_PATH.is_file(), "missing %s" % GOOGLE_PATH
        assert DRAFTS_PATH.is_file(), "missing %s" % DRAFTS_PATH

    def setUp(self):
        # Isolate env: sandbox mode, fresh mind dir, no token.
        self._saved_env = dict(os.environ)
        self._tmp = tempfile.TemporaryDirectory()
        mind = str(Path(self._tmp.name) / "mind")
        os.environ["MARC_MODE"] = "sandbox"
        os.environ["MODE"] = "sandbox"
        os.environ["MARC_MIND_DIR"] = mind
        os.environ["MIND_DIR"] = mind
        # Point token vars at a path that does not exist.
        missing = str(Path(self._tmp.name) / "missing_token.json")
        os.environ["GOOGLE_TOKEN_PATH"] = missing
        os.environ["MARC_GOOGLE_TOKEN_PATH"] = missing
        # Belt-and-braces: disable the network for every test.
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("network must not be used in sandbox tests")

        urllib.request.urlopen = _no_network  # type: ignore[assignment]

    def tearDown(self):
        urllib.request.urlopen = self._real_urlopen  # type: ignore[assignment]
        os.environ.clear()
        os.environ.update(self._saved_env)
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    # -- mode / token ----------------------------------------------------

    def test_no_token_file(self):
        """Without a token file, has_token() is False."""
        self.assertFalse(GOOGLE.has_token())

    def test_mode_is_sandbox_without_token(self):
        """Sandbox mode when MARC_MODE=sandbox and token is missing."""
        self.assertEqual(GOOGLE.get_mode(), "sandbox")
        self.assertTrue(GOOGLE.is_sandbox())
        self.assertTrue(GOOGLE.is_sandbox("sandbox"))
        self.assertFalse(GOOGLE.is_sandbox("live"))

    def test_confirm_gated_tools(self):
        """mail_compose / mail_send / calendar_create require confirmation."""
        gated = set(getattr(GOOGLE, "CONFIRM_TOOLS", set()))
        alias = set(getattr(GOOGLE, "CONFIRM_GATED", gated))
        for tool in ("mail_compose", "mail_send", "calendar_create"):
            self.assertIn(tool, gated, "%s must be confirm-gated" % tool)
            self.assertIn(tool, alias)

    # -- compose is a draft, not a send ----------------------------------

    def test_compose_creates_draft_not_send(self):
        """compose() without a token queues a draft — nothing is sent."""
        res = GOOGLE.compose(
            to="sam.professional.fake@gmail.com (FAKE)",
            subject="FAKE: hello",
            body="FAKE: hello body, do not contact.",
        )
        self.assertIsInstance(res, dict)
        self.assertNotEqual(res.get("status"), "sent")
        self.assertIn(res.get("status"), ("queued", "draft"))
        self.assertTrue(res.get("sandbox"))
        self.assertEqual(res.get("tool"), "mail_compose")
        # Draft-only channel mapping: mail_compose -> mail.
        self.assertEqual(res.get("channel"), "mail")
        # The draft is persisted via drafts (file-backed).
        draft_id = res.get("id")
        self.assertTrue(draft_id)
        stored = DRAFTS.get(draft_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.get("status"), "queued")

    def test_compose_confirmed_still_draft_without_token(self):
        """Even confirmed=True stays a draft when there is no token/live."""
        res = GOOGLE.compose(
            to="sam.professional.fake@gmail.com (FAKE)",
            subject="FAKE: confirmed hello",
            body="FAKE: confirmed body.",
            confirmed=True,
        )
        self.assertIsInstance(res, dict)
        self.assertNotEqual(res.get("status"), "sent")
        self.assertIn(res.get("status"), ("queued", "draft"))
        self.assertTrue(res.get("sandbox"))

    # -- calendar_create is a draft in sandbox ----------------------------

    def test_calendar_create_sandbox_is_draft(self):
        """calendar_create() in sandbox queues a draft — nothing created live."""
        res = GOOGLE.calendar_create(
            title="FAKE: Dinner with Priya",
            when="Sat 19:00 (FAKE)",
        )
        self.assertIsInstance(res, dict)
        self.assertNotEqual(res.get("status"), "created")
        self.assertNotEqual(res.get("status"), "sent")
        self.assertIn(res.get("status"), ("queued", "draft"))
        self.assertTrue(res.get("sandbox"))
        self.assertEqual(res.get("tool"), "calendar_create")
        self.assertEqual(res.get("channel"), "calendar")
        draft_id = res.get("id")
        self.assertTrue(draft_id)
        stored = DRAFTS.get(draft_id)
        self.assertIsNotNone(stored)

    def test_calendar_create_confirmed_still_draft_without_token(self):
        """confirmed=True without live+token still yields a draft."""
        res = GOOGLE.calendar_create(
            title="FAKE: Standup",
            when="Mon 09:30 (FAKE)",
            confirmed=True,
        )
        self.assertIsInstance(res, dict)
        self.assertIn(res.get("status"), ("queued", "draft"))
        self.assertTrue(res.get("sandbox"))

    # -- reads work offline (no network) ----------------------------------

    def test_search_mail_offline_fake(self):
        """search_mail returns FAKE fixtures offline (urlopen disabled)."""
        res = GOOGLE.search_mail("Q3")
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "sandbox")
        self.assertIsInstance(res.get("messages"), list)
        self.assertGreaterEqual(len(res["messages"]), 1)

    def test_summarize_thread_offline_fake(self):
        """summarize_thread summarises FAKE fixtures offline."""
        res = GOOGLE.summarize_thread("t_q3")
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "sandbox")
        self.assertIn("FAKE", res.get("summary", ""))

    def test_calendar_list_offline_fake(self):
        """calendar_list returns FAKE events offline."""
        res = GOOGLE.calendar_list()
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "sandbox")
        self.assertIsInstance(res.get("events"), list)
        self.assertGreaterEqual(len(res["events"]), 1)

    def test_drive_search_offline_fake(self):
        """drive_search filters FAKE files offline."""
        res = GOOGLE.drive_search("Q3")
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "sandbox")
        self.assertIsInstance(res.get("files"), list)
        self.assertGreaterEqual(len(res["files"]), 1)

    def test_write_file_no_network(self):
        """write_file persists locally without touching the network."""
        target = Path(self._tmp.name) / "mind" / "note.txt"
        out = GOOGLE.write_file(target, "FAKE: hello draft")
        self.assertEqual(Path(str(out)), target)
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"), "FAKE: hello draft")


if __name__ == "__main__":
    unittest.main()
