"""mind.sqlite extended schema tests (stdlib only, temp dir)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_index():
    path = ROOT / "brain" / "index.py"
    spec = importlib.util.spec_from_file_location("brain_index_ext", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["brain_index_ext"] = mod
    # brain package relative imports not required — index is standalone
    spec.loader.exec_module(mod)
    return mod


class MindSqliteExtTest(unittest.TestCase):
    def test_ensure_schema_and_upsert_message(self):
        idx = _load_index()
        with tempfile.TemporaryDirectory() as tmp:
            mind = Path(tmp)
            db = idx.ensure_schema(mind)
            self.assertTrue(db.exists())
            tid = idx.upsert_message(
                channel="instagram",
                external_id="thread-1",
                person_slug="priya",
                direction="in",
                body="hello",
                message_id="m1",
                mind_dir=mind,
            )
            self.assertGreater(tid, 0)
            idx.upsert_person("priya", display="Priya", channels=["whatsapp"], mind_dir=mind)
            idx.record_job("j1", "mind_reindex", "done", path=str(mind), mind_dir=mind)


if __name__ == "__main__":
    unittest.main()
