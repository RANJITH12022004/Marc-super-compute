"""Door mind proxy route presence (stdlib, no network)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DoorMindProxyTest(unittest.TestCase):
    def test_server_has_mind_routes(self):
        text = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('/v1/whoami', text)
        self.assertIn('/v1/mind', text)
        self.assertIn('/v1/note', text)
        self.assertIn("webhooks/meta", text)
        self.assertIn("_serve_whoami", text)
        self.assertIn("_serve_mind", text)
        self.assertIn("_serve_note", text)

    def test_vercel_js_files_exist(self):
        v1 = ROOT / "api" / "v1"
        for name in ("whoami.js", "mind.js", "note.js", "webhooks_meta.js"):
            self.assertTrue((v1 / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
