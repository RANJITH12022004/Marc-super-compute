"""Mind tools never become phone_steps; planner expands where-am-i."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class PlannerMindRegexTests(unittest.TestCase):
    def test_where_am_i_is_mind_recall(self):
        import planner

        tool, args = planner._clause_to_tool("where am i")
        self.assertEqual(tool, "mind_recall")
        self.assertTrue((args or {}).get("rag_first"))

    def test_what_will_you_do_is_mind_recall(self):
        import planner

        tool, args = planner._clause_to_tool("what will you do")
        self.assertEqual(tool, "mind_recall")

    def test_mind_device_is_laptop(self):
        import planner

        self.assertEqual(
            planner._resolve_device("who am i", "auto", tool="mind_recall"),
            "laptop",
        )


class PhoneStepsFilterTests(unittest.TestCase):
    def test_brain_tools_stripped(self):
        # Mirror server filter logic without spinning HTTP.
        plan = [
            {"tool": "mind_recall", "device": "phone", "args": {"query": "who"}},
            {"tool": "dial", "device": "phone", "args": {"to": "Mom"}},
            {"tool": "whoami", "device": "laptop", "args": {}},
        ]
        brain = frozenset({"mind_recall", "mind_note", "whoami", "who_am_i"})
        phone_steps = []
        for s in plan:
            tool = str(s.get("tool") or "").strip().lower()
            if tool in brain:
                continue
            if str(s.get("device") or "phone").lower() == "phone":
                phone_steps.append(s)
        self.assertEqual(len(phone_steps), 1)
        self.assertEqual(phone_steps[0]["tool"], "dial")


if __name__ == "__main__":
    unittest.main()
