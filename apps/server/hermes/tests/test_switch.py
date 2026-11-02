"""Hermes loopback switch tests — stdlib unittest, no Hermes binary.

- project_use a then project_use b => active b, previous stopped.
- unsafe workdir refused.
- project_run with hermes down still ok sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parent.parent
if str(HERMES_DIR) not in sys.path:
    sys.path.insert(0, str(HERMES_DIR))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


PATHS = _load("hermes_paths_under_test", HERMES_DIR / "paths.py")
SESSION = _load("hermes_session_under_test", HERMES_DIR / "session.py")
CLIENT = _load("hermes_client_under_test", HERMES_DIR / "client.py")


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.work_a = tmp / "work-a"
        self.work_b = tmp / "work-b"
        self.work_a.mkdir(parents=True, exist_ok=True)
        self.work_b.mkdir(parents=True, exist_ok=True)
        projects = {
            "proj-a": {"workdir": str(self.work_a)},
            "proj-b": {"workdir": str(self.work_b)},
            "unsafe-laptop": {"workdir": "/tmp/mark-laptop/work"},
            "unsafe-android": {"workdir": "/home/rox/marc/android/work"},
            "unsafe-root": {"workdir": "/"},
        }
        self.projects_file = tmp / "projects.json"
        self.projects_file.write_text(json.dumps(projects), encoding="utf-8")
        self._old_projects = os.environ.get("HERMES_PROJECTS_FILE")
        os.environ["HERMES_PROJECTS_FILE"] = str(self.projects_file)
        # Force HTTP down: closed loopback port.
        self._old_url = os.environ.get("HERMES_URL")
        os.environ["HERMES_URL"] = "http://127.0.0.1:9"
        try:
            SESSION.project_stop()
        except Exception:
            pass

    def tearDown(self):
        try:
            SESSION.project_stop()
        except Exception:
            pass
        if self._old_projects is None:
            os.environ.pop("HERMES_PROJECTS_FILE", None)
        else:
            os.environ["HERMES_PROJECTS_FILE"] = self._old_projects
        if self._old_url is None:
            os.environ.pop("HERMES_URL", None)
        else:
            os.environ["HERMES_URL"] = self._old_url

    def test_use_a_then_b_active_b_previous_stopped(self):
        first = SESSION.project_use("proj-a")
        self.assertTrue(first.get("ok"), first)
        second = SESSION.project_use("proj-b")
        self.assertTrue(second.get("ok"), second)
        self.assertEqual(second.get("slug"), "proj-b")
        active = second.get("active") or {}
        self.assertEqual(active.get("slug"), "proj-b")
        prev = second.get("previous") or {}
        self.assertEqual(prev.get("slug"), "proj-a")
        self.assertTrue(second.get("previous_stopped") or prev.get("stopped"))

    def test_client_use_a_then_b(self):
        first = CLIENT.project_use("proj-a")
        self.assertTrue(first.get("ok"), first)
        second = CLIENT.project_use("proj-b")
        self.assertTrue(second.get("ok"), second)
        self.assertEqual((second.get("active") or {}).get("slug"), "proj-b")

    def test_unsafe_workdir_refused(self):
        for slug in ("unsafe-laptop", "unsafe-android", "unsafe-root"):
            res = SESSION.project_use(slug)
            self.assertFalse(res.get("ok"), res)
            self.assertIn("error", res)
        self.assertFalse(PATHS.is_safe_workdir(""))
        self.assertFalse(PATHS.is_safe_workdir("/"))
        self.assertFalse(PATHS.is_safe_workdir("/tmp/mark-laptop/x"))
        self.assertFalse(PATHS.is_safe_workdir("/home/rox/marc/android"))
        self.assertFalse(PATHS.is_safe_goal("please reboot now"))
        self.assertFalse(PATHS.is_safe_goal("sudo apt update"))
        self.assertFalse(PATHS.is_safe_goal("rm -rf /tmp/x"))

    def test_project_run_hermes_down_still_ok_sandbox(self):
        res = CLIENT.project_run("summarize status", str(self.work_a))
        self.assertTrue(res.get("ok"), res)
        self.assertTrue(res.get("sandbox"), res)
        self.assertIsInstance(res.get("text"), str)
        self.assertTrue(res.get("text").strip())
        note = self.work_a / "var" / "hermes-last.md"
        self.assertTrue(note.is_file(), "sandbox note missing: %s" % note)


if __name__ == "__main__":
    unittest.main()
