"""Closed-loop phone hands: Java-as-text + local planner recipes."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "com" / "bee" / "island"
MUSE = ROOT.parent / "marc-muse"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("no spec for %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bee_control = _load_module(ROOT / "bee_control.py", "bee_control_d4")
ride_split = _load_module(MUSE / "ride_split.py", "ride_split_d4")


def _read(name):
    with open(os.path.join(str(SRC), name), encoding="utf-8") as f:
        return f.read()


class ClosedLoopHandsTest(unittest.TestCase):
    def test_whatsapp_clicks_named_contact_not_share_sheet(self):
        java = _read("PhoneActions.java")
        self.assertIn("clickChatRow", java)
        self.assertIn("driveWhatsApp", java)
        self.assertIn("wrong person", java)
        self.assertIn("Type a message", java)
        run_idx = java.find("if (\"whatsapp_send\".equals(tool))")
        intent_idx = java.find("Intent.ACTION_SEND")
        self.assertGreater(run_idx, 0)
        self.assertGreater(intent_idx, run_idx)

    def test_play_music_taps_play_not_search_uri_only(self):
        java = _read("PhoneActions.java")
        self.assertIn("drivePlayMusic", java)
        start = java.find("static Map<String, Object> drivePlayMusic")
        end = java.find("static Map<String, Object> driveCall")
        drive = java[start:end]
        self.assertNotIn("spotify:search:", drive)
        self.assertNotIn("clickFirstResultRow", drive)
        self.assertIn("clickChatRow", drive)
        self.assertIn("no query", drive)

    def test_click_label_uses_clickable_ancestor(self):
        access = _read("IslandAccess.java")
        self.assertIn("clickLabel", access)
        self.assertIn("clickClickableAncestor", access)
        self.assertIn("getParent", access)
        self.assertIn("isClickable", access)
        self.assertIn("waitFor", access)
        self.assertIn("nodeDump", access)
        chat = access[access.find("clickChatRow") : access.find("clickFirstResultRow")]
        self.assertIn("getParent", chat + access[access.find("clickClickableAncestor") :])

    def test_reels_never_scrolls_home(self):
        java = _read("PhoneActions.java")
        start = java.find("static Map<String, Object> driveReels")
        end = java.find("private static boolean waitPackage")
        drive = java[start:end]
        self.assertIn("reels tab missing", drive)
        self.assertIn("startAutoScroll", drive)
        self.assertIn("isSelectedLabel", drive)
        self.assertLess(drive.find("reels tab missing"), drive.find("startAutoScroll"))

    def test_whatsapp_waits_composer_skips_me(self):
        java = _read("PhoneActions.java")
        start = java.find("static Map<String, Object> driveWhatsApp")
        end = java.find("static Map<String, Object> drivePlayMusic")
        drive = java[start:end]
        self.assertIn("Type a message", drive)
        self.assertIn("Say who to text.", drive)
        self.assertIn("wrong person", drive)
        self.assertIn("typeFocused", drive)
        self.assertIn("typeWaId", drive)
        self.assertLess(drive.find("Type a message"), drive.find("typeWaId"))
        self.assertIn("send failed", drive)
        self.assertIn("clickSendControl", drive)
        self.assertIn("focusedEditText", drive)
        self.assertNotIn('clickLabel("Send")', drive)

    def test_send_control_uses_view_id(self):
        access = _read("IslandAccess.java")
        self.assertIn("clickViewId", access)
        self.assertIn("focusedEditText", access)
        self.assertIn("clickSendControl", access)
        self.assertIn("com.whatsapp:id/send", access)
        self.assertIn("clickTextExactPrefer", access)

    def test_youtube_play_is_not_spotify(self):
        java = _read("PhoneActions.java")
        self.assertIn("driveYouTube", java)
        self.assertIn("youtube_play", java)
        access = _read("IslandAccess.java")
        self.assertIn("isVideoSized", access)
        self.assertIn("isResultChrome", access)
        self.assertIn("notification", access)
        start = java.find("static Map<String, Object> driveYouTube")
        end = java.find("private static boolean youtubePlayerUp")
        if end < 0:
            end = java.find("private static boolean waitPackage")
        drive = java[start:end]
        self.assertNotIn("drivePlayMusic", drive)
        self.assertIn("youtube", drive.lower())

    def test_ask_router_leftover_runs_hands_when_phone_steps_empty(self):
        router = _read("AskRouter.java")
        leftover = router[router.find("static void leftover") : router.find("static void actOrConfirm")]
        self.assertIn("actOrConfirm", leftover)
        self.assertIn("splitUtterance", leftover)
        empty_idx = leftover.find("if (!phoneSteps.isEmpty())")
        split_idx = leftover.find("splitUtterance")
        act_idx = leftover.rfind("actOrConfirm")
        self.assertGreater(empty_idx, 0)
        self.assertGreater(split_idx, empty_idx)
        self.assertGreater(act_idx, split_idx)

    def test_reels_auto_scroll_until_stop(self):
        access = _read("IslandAccess.java")
        service = _read("IslandService.java")
        ask = _read("BeeAsk.java")
        router = _read("AskRouter.java")
        self.assertIn("foregroundPackage", access)
        self.assertIn("clickChatRow", access)
        self.assertIn("edittext", access.lower())
        self.assertIn("startAutoScroll", service)
        self.assertIn("stopAutoScroll", service)
        self.assertIn("15000", service)
        self.assertIn("REEL_CAP_MS", service)
        self.assertNotIn("AUTO_SCROLL_MS = 1800", service)
        self.assertIn("auto_scroll", ask)
        self.assertIn("IslandService.stopAutoScroll", router)
        finish = router[router.find("static void finish") :]
        speak_at = finish.find("speak(")
        dispatch_at = finish.find("BeeAsk.dispatch")
        self.assertGreater(dispatch_at, 0)
        self.assertGreater(speak_at, 0)
        self.assertLess(speak_at, dispatch_at)

    def test_rox_url_defaults_to_https_door(self):
        rox = _read("RoxClient.java")
        self.assertIn("https://marc-door.vercel.app", rox)
        self.assertIn("/v1/health", rox)
        self.assertIn("/v1/utterance", rox)
        self.assertIn("startsWith(\"https://\")", rox)

    def test_planner_instagram_reels_is_auto_scroll(self):
        steps = bee_control.split_utterance("open instagram and scroll reels")
        tools = [s.get("tool") for s in steps]
        self.assertEqual(tools, ["auto_scroll"])
        self.assertNotIn("swipe", tools)
        tool, args, _device = ride_split.clause_to_tool("auto scroll reels")
        self.assertEqual(tool, "auto_scroll")
        self.assertEqual((args or {}).get("direction"), "up")
        plan = ride_split.local_plan("open Instagram and auto scroll reels")
        tools2 = [s.get("tool") for s in (plan.get("plan") or [])]
        self.assertEqual(tools2, ["auto_scroll"])

    def test_drive_call_not_dial_only(self):
        java = _read("PhoneActions.java")
        self.assertIn("driveCall", java)
        self.assertIn("ACTION_CALL", java)

    def test_whatsapp_defaults_to_business(self):
        java = _read("PhoneActions.java")
        self.assertIn("com.whatsapp.w4b", java)
        self.assertIn("resolveWaPackage", java)
        self.assertIn("personal whatsapp", java)
        step = bee_control.clause_to_tool("text rahull marc test")
        self.assertEqual(step.tool, "whatsapp_send")
        self.assertEqual((step.args or {}).get("package"), "com.whatsapp.w4b")
        tool, args, _ = ride_split.clause_to_tool("text rahull marc test")
        self.assertEqual(tool, "whatsapp_send")
        self.assertEqual((args or {}).get("package"), "com.whatsapp.w4b")
        tool2, args2, _ = ride_split.clause_to_tool(
            "text rahull marc test on my personal whatsapp"
        )
        self.assertEqual((args2 or {}).get("package"), "com.whatsapp")

    def test_notifications_and_suggest_reply_tools(self):
        notify = _read("BeeNotify.java")
        self.assertIn("NotificationListenerService", notify)
        self.assertIn("spokenSummary", notify)
        self.assertIn("suggestFor", notify)
        java = _read("PhoneActions.java")
        self.assertIn("notifications_list", java)
        self.assertIn("suggest_reply", java)
        ask = _read("AskRouter.java")
        self.assertIn("Nothing to confirm.", ask)
        steps = bee_control.split_utterance("what are the new notifications")
        self.assertEqual([s.get("tool") for s in steps], ["notifications_list"])
        steps2 = bee_control.split_utterance("what should i reply to rahull")
        self.assertEqual([s.get("tool") for s in steps2], ["suggest_reply"])
        tool, args, _ = ride_split.clause_to_tool("what are the new notifications?")
        self.assertEqual(tool, "notifications_list")
        tool2, args2, _ = ride_split.clause_to_tool("what should i reply to priya")
        self.assertEqual(tool2, "suggest_reply")
        self.assertIn("priya", ((args2 or {}).get("to") or "").lower())

    def test_payment_gate_and_pill_states(self):
        gate = _read("PaymentGate.java")
        self.assertIn("com.dreamplug.androidapp", gate)
        self.assertIn("com.google.android.apps.nbu.paisa.user", gate)
        service = _read("IslandService.java")
        self.assertIn("IslandPillView", service)
        self.assertIn("HydrationHeroView", service)
        self.assertIn("onPaymentHidden", service)
        self.assertIn("Didn't catch that. Try again.", service)
        pill = _read("IslandPillView.java")
        self.assertIn("STATE_LISTENING", pill)
        self.assertIn("STATE_HIDDEN", pill)
        self.assertIn("0xFF000000", pill)
        self.assertNotIn("0xFFE8B15A", pill)

    def test_chat_touch_maps_to_tool(self):
        step = bee_control.clause_to_tool("touch priya about dinner")
        self.assertEqual(step.tool, "chat_touch")
        self.assertEqual((step.args or {}).get("to").lower(), "priya")
        self.assertIn("dinner", ((step.args or {}).get("topic") or "").lower())
        tool, args, _ = ride_split.clause_to_tool("touch priya about dinner")
        self.assertEqual(tool, "chat_touch")
        ask = _read("BeeAsk.java")
        self.assertIn("chat_touch", ask)
        router = _read("AskRouter.java")
        self.assertIn("Say confirm to send.", router)

    def test_phone_profile_snapshot_tool(self):
        step = bee_control.clause_to_tool("refresh my phone profile")
        self.assertEqual(step.tool, "phone_profile_snapshot")
        phone = _read("PhoneActions.java")
        self.assertIn("phone_profile_snapshot", phone)
        self.assertIn("visibleTextDump", _read("IslandAccess.java"))
        self.assertIn("phone_profile_snapshot", _read("BeeAsk.java"))

    def test_door_whoami_uses_v1_and_auth(self):
        rox = _read("RoxClient.java")
        self.assertIn("/v1/whoami", rox)
        self.assertIn("applyAuth", rox)
        mind = _read("BeeMind.java")
        self.assertIn("where am i", mind)
        self.assertNotIn('me = "Unknown."', mind)
        self.assertNotIn('now = "Unknown."', mind)

    def test_confirm_includes_wa_and_dial(self):
        ask = _read("BeeAsk.java")
        self.assertIn('"whatsapp_send"', ask)
        self.assertIn('"dial"', ask)
        self.assertIn("isBrainTool", ask)
        self.assertIn("isVagueContact", ask)

    def test_island_backdrop_and_wave_present(self):
        self.assertIn("STATE_CONFIRM", _read("IslandBackdropView.java"))
        self.assertIn("setMode", _read("IslandWaveView.java"))
        service = _read("IslandService.java")
        self.assertIn("setVoiceLevel", service)
        self.assertIn("IslandWaveView", service)
        self.assertIn("OvershootInterpolator", service)


if __name__ == "__main__":
    unittest.main()
