"""B0 scaffold walls for bee-island (importlib-loaded).

Checks:
  * package com.bee.island in AndroidManifest.xml and app/build.gradle
  * app_name is 'bee' in res/values/strings.xml
  * bee_install.assert_safe_path rejects 'mark-laptop' and
    '/home/rox/marc/android' (any slash style)
  * CAMERA is not required here (documents no CAMERA gate for B0)
"""
from __future__ import annotations

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "AndroidManifest.xml"
GRADLE = ROOT / "app" / "build.gradle"
STRINGS = ROOT / "res" / "values" / "strings.xml"
INSTALL = Path(__file__).resolve().parents[3] / "deploy" / "phone" / "bee_install.py"


def load_install():
    spec = importlib.util.spec_from_file_location("bee_install", INSTALL)
    assert spec is not None and spec.loader is not None, f"no spec for {INSTALL}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_install_module_loads_via_importlib():
    assert INSTALL.is_file(), f"missing {INSTALL}"
    mod = load_install()
    assert hasattr(mod, "assert_safe_path")
    assert hasattr(mod, "REMOTE")
    assert hasattr(mod, "LOCAL")


def test_remote_is_bee_android():
    mod = load_install()
    assert mod.REMOTE == "/home/rox/bee/android"


def test_local_sources_from_bee_island():
    mod = load_install()
    local = str(getattr(mod, "LOCAL")).replace("\\", "/")
    assert "apps/bee-island" in local


def test_secret_never_printed():
    src = INSTALL.read_text(encoding="utf-8")
    assert "MARC_SSH_PW" in src
    for line in src.splitlines():
        low = line.lower()
        if "marc_ssh_pw" in low and ("print" in low or "log" in low or "echo" in low):
            raise AssertionError(f"installer must never print MARC_SSH_PW: {line!r}")


def test_assert_safe_path_rejects_mark_laptop():
    mod = load_install()
    bad = [
        "/home/rox/mark-laptop/foo",
        "C:\\mark-laptop\\x",
        "ssh://mark-laptop/home/rox/bee/android",
    ]
    for p in bad:
        try:
            mod.assert_safe_path(p)
        except Exception:
            continue
        raise AssertionError(f"assert_safe_path accepted mark-laptop path: {p!r}")


def test_assert_safe_path_rejects_marc_android():
    mod = load_install()
    bad = [
        "/home/rox/marc/android",
        "/home/rox/marc/android/app",
        "\\home\\rox\\marc\\android",
        "C:\\home\\rox\\marc\\android\\x",
        "/home/rox/marc/android".replace("/", "\\"),
    ]
    for p in bad:
        try:
            mod.assert_safe_path(p)
        except Exception:
            continue
        raise AssertionError(f"assert_safe_path accepted marc android path: {p!r}")


def test_assert_safe_path_allows_remote():
    mod = load_install()
    assert mod.assert_safe_path(mod.REMOTE) is not None


def test_manifest_package_is_bee_island():
    assert MANIFEST.is_file(), f"missing {MANIFEST}"
    text = MANIFEST.read_text(encoding="utf-8")
    assert "com.bee.island" in text
    root = ET.fromstring(text)
    assert root.get("package") == "com.bee.island" or "com.bee.island" in text


def test_gradle_package_is_bee_island():
    assert GRADLE.is_file(), f"missing {GRADLE}"
    text = GRADLE.read_text(encoding="utf-8")
    assert "com.bee.island" in text


def test_app_name_is_bee():
    assert STRINGS.is_file(), f"missing {STRINGS}"
    root = ET.parse(str(STRINGS)).getroot()
    names = {s.get("name"): (s.text or "").strip() for s in root.findall("string")}
    assert names.get("app_name") == "bee"


def test_camera_not_required_here():
    # B0 scaffold does not gate on CAMERA; document that explicitly so a
    # future CAMERA wall does not break this scaffold test.
    assert True


class B0ScaffoldTests(unittest.TestCase):
    def test_install_module_loads_via_importlib(self):
        test_install_module_loads_via_importlib()

    def test_remote_is_bee_android(self):
        test_remote_is_bee_android()

    def test_local_sources_from_bee_island(self):
        test_local_sources_from_bee_island()

    def test_secret_never_printed(self):
        test_secret_never_printed()

    def test_assert_safe_path_rejects_mark_laptop(self):
        test_assert_safe_path_rejects_mark_laptop()

    def test_assert_safe_path_rejects_marc_android(self):
        test_assert_safe_path_rejects_marc_android()

    def test_assert_safe_path_allows_remote(self):
        test_assert_safe_path_allows_remote()

    def test_manifest_package_is_bee_island(self):
        test_manifest_package_is_bee_island()

    def test_gradle_package_is_bee_island(self):
        test_gradle_package_is_bee_island()

    def test_app_name_is_bee(self):
        test_app_name_is_bee()


if __name__ == "__main__":
    unittest.main()
