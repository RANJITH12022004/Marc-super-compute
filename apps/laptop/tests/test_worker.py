"""Tests for apps/laptop/worker.py.

Covers: health ok, allowlist refuses reboot, unknown tool ok:false.
Uses handle_run/health_payload (no sockets) plus an import-leak guard.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

WORKER_PATH = os.path.join(os.path.dirname(__file__), "..", "worker.py")


def load_worker():
    spec = importlib.util.spec_from_file_location("marc_laptop_worker", WORKER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["marc_laptop_worker"] = mod
    spec.loader.exec_module(mod)
    return mod


worker = load_worker()


class LaptopWorkerTest(unittest.TestCase):
    def setUp(self):
        self._mode = os.environ.get("MARC_MODE")
        self._token = os.environ.get("MARC_TOKEN")

    def tearDown(self):
        if self._mode is None:
            os.environ.pop("MARC_MODE", None)
        else:
            os.environ["MARC_MODE"] = self._mode
        if self._token is None:
            os.environ.pop("MARC_TOKEN", None)
        else:
            os.environ["MARC_TOKEN"] = self._token

    def test_no_bee_island_import(self):
        src = open(WORKER_PATH, encoding="utf-8").read().lower()
        self.assertNotIn("import bee", src)
        self.assertNotIn("from bee", src)
        self.assertNotIn("bee.island", src)

    def test_health_ok(self):
        self.assertEqual(worker.health_payload(), {"ok": True, "device": "laptop"})

    def test_allowlist_refuses_reboot_family(self):
        os.environ.pop("MARC_TOKEN", None)
        for evil in ("reboot", "shutdown", "sudo", "rm", "Reboot", "SHUTDOWN"):
            status, payload = worker.handle_run(evil, {})
            self.assertFalse(payload["ok"])
            self.assertIn(status, (400, 403))
            err = payload.get("error") or ""
            self.assertTrue("refus" in err or "unknown" in err)

    def test_unknown_tool_ok_false(self):
        status, payload = worker.handle_run("do_evil_thing", {"x": 1})
        self.assertFalse(payload["ok"])
        self.assertEqual(status, 400)

    def test_open_app_sandbox_ok(self):
        os.environ["MARC_MODE"] = "sandbox"
        status, payload = worker.handle_run("open_app", {"label": "notepad"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["label"], "notepad")

    def test_type_into_sandbox_ok(self):
        os.environ["MARC_MODE"] = "sandbox"
        status, payload = worker.handle_run("type_into", {"text": "hello"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_auth_open_without_token(self):
        os.environ.pop("MARC_TOKEN", None)
        self.assertTrue(worker.check_auth({}, ""))

    def test_auth_enforced_with_token(self):
        os.environ["MARC_TOKEN"] = "secret123"
        self.assertFalse(worker.check_auth({}, ""))
        self.assertTrue(worker.check_auth({"X-MARC-Token": "secret123"}, ""))
        self.assertTrue(worker.check_auth({}, "secret123"))
        self.assertFalse(worker.check_auth({"X-MARC-Token": "wrong"}, ""))


if __name__ == "__main__":
    unittest.main()
