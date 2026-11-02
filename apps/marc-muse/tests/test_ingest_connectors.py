"""Sandbox tests for Gmail digest, GitHub ingest, ME merge (no network)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class MeMergeTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.mind = Path(self._td.name)
        os.environ["MARC_MIND_DIR"] = str(self.mind)
        os.environ["MARC_MODE"] = "sandbox"
        from brain import vault

        self.vault = vault
        self.vault.seed()

    def tearDown(self):
        self._td.cleanup()

    def test_seed_does_not_clobber_me(self):
        me = self.mind / "ME.md"
        me.write_text("# ME\n\nCustom soul line XYZ\n", encoding="utf-8")
        self.vault.seed()
        text = me.read_text(encoding="utf-8")
        self.assertIn("Custom soul line XYZ", text)

    def test_merge_me_facts_github(self):
        self.vault.merge_me_facts({"github": "- [[notes/github/demo]] — demo"})
        text = (self.mind / "ME.md").read_text(encoding="utf-8")
        self.assertIn("## GitHub", text)
        self.assertIn("notes/github/demo", text)
        # second merge replaces section, keeps soul
        self.vault.merge_me_facts({"github": "- [[notes/github/other]] — other"})
        text2 = (self.mind / "ME.md").read_text(encoding="utf-8")
        self.assertIn("notes/github/other", text2)
        self.assertNotIn("notes/github/demo", text2)


class GithubIngestTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.mind = Path(self._td.name)
        os.environ["MARC_MIND_DIR"] = str(self.mind)
        os.environ["MARC_MODE"] = "sandbox"
        os.environ.pop("GITHUB_TOKEN", None)

    def tearDown(self):
        self._td.cleanup()

    def test_ingest_repos_sandbox(self):
        from connectors import github

        res = github.ingest_repos(mind_dir=self.mind)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "sandbox")
        self.assertGreaterEqual(int(res.get("written") or 0), 1)
        notes = list((self.mind / "notes" / "github").glob("*.md"))
        self.assertTrue(notes)


class GmailDigestTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.mind = Path(self._td.name)
        os.environ["MARC_MIND_DIR"] = str(self.mind)
        os.environ["MARC_MODE"] = "sandbox"

    def tearDown(self):
        self._td.cleanup()

    def test_fetch_mail_digest_sandbox(self):
        from connectors import google

        res = google.fetch_mail_digest(mind_dir=self.mind)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "sandbox")
        self.assertGreaterEqual(int(res.get("written") or 0), 1)
        self.assertTrue((self.mind / "notes" / "mail").is_dir())


class LaptopIngestTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name) / "home"
        self.mind = Path(self._td.name) / "mind"
        self.root.mkdir()
        self.mind.mkdir()
        (self.root / "Documents").mkdir()
        (self.root / "Documents" / "notes.md").write_text("# hello laptop\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "x.py").write_text("print(1)\n", encoding="utf-8")

    def tearDown(self):
        self._td.cleanup()

    def test_walk_denies_secrets(self):
        from brain import laptop_ingest as li

        res = li.walk_home(root=self.root, mind_dir=self.mind)
        self.assertTrue(res.get("ok"))
        self.assertGreaterEqual(int(res.get("count") or 0), 1)
        names = list((self.mind / "notes" / "laptop").glob("*.md"))
        joined = " ".join(p.name for p in names)
        self.assertIn("notes", joined.lower())
        self.assertNotIn(".env", joined)


class RagFirstTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.mind = Path(self._td.name)
        os.environ["MARC_MIND_DIR"] = str(self.mind)
        from brain import vault
        from brain import index as idx

        vault.seed()
        (self.mind / "notes").mkdir(exist_ok=True)
        (self.mind / "notes" / "github_demo.md").write_text(
            "# Marc-super-compute\n\nPersonal Marc stack repo.\n",
            encoding="utf-8",
        )
        idx.rebuild(self.mind)

    def tearDown(self):
        self._td.cleanup()

    def test_whoami_rag_first(self):
        from brain import recall

        res = recall.who_am_i()
        self.assertTrue(res.get("ok"))
        text = res.get("text") or ""
        self.assertTrue(text.strip())
        # Should surface vault / FTS material, not invent emptiness when notes exist
        self.assertTrue(
            "Ranjith" in text
            or "ME.md" in text
            or "Marc-super-compute" in text
            or "who am i" in text.lower()
        )

    def test_know_about_me_hits_rag(self):
        from brain import recall

        res = recall.mind_recall("what do you know about me")
        self.assertTrue(res.get("ok"))
        self.assertTrue((res.get("text") or "").strip())


if __name__ == "__main__":
    unittest.main()
