"""Hermes project switch tests via importlib (no network, no Hermes binary)."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

HERMES = Path(__file__).resolve().parents[2] / "server" / "hermes"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PATHS = _load("hermes_paths_muse_t", HERMES / "paths.py")
SESSION = _load("hermes_session_muse_t", HERMES / "session.py")


class ProjectHermesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.work_a = tmp / "a"
        self.work_b = tmp / "b"
        self.work_a.mkdir()
        self.work_b.mkdir()
        projects = {
            "proj-a": {"workdir": str(self.work_a)},
            "proj-b": {"workdir": str(self.work_b)},
        }
        self.projects_file = tmp / "projects.json"
        self.projects_file.write_text(json.dumps(projects), encoding="utf-8")
        self._old = os.environ.get("HERMES_PROJECTS_FILE")
        os.environ["HERMES_PROJECTS_FILE"] = str(self.projects_file)
        try:
            SESSION.project_stop()
        except Exception:
            pass

    def tearDown(self):
        try:
            SESSION.project_stop()
        except Exception:
            pass
        if self._old is None:
            os.environ.pop("HERMES_PROJECTS_FILE", None)
        else:
            os.environ["HERMES_PROJECTS_FILE"] = self._old

    def test_use_a_then_b(self):
        first = SESSION.project_use("proj-a")
        self.assertTrue(first.get("ok"), first)
        second = SESSION.project_use("proj-b")
        self.assertTrue(second.get("ok"), second)
        self.assertEqual(second.get("slug"), "proj-b")
        active = (second.get("active") or {})
        self.assertEqual(active.get("slug"), "proj-b")

    def test_unsafe_workdir_refused(self):
        self.assertFalse(PATHS.is_safe_workdir("/tmp/mark-laptop/work"))
        self.assertFalse(PATHS.is_safe_workdir("/home/rox/marc/android"))


if __name__ == "__main__":
    unittest.main()
