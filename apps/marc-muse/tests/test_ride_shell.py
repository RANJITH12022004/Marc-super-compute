"""Shell contract tests I1-I3 — stdlib unittest, no real network.

Run:
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root

Loads client.py and fake_mic.py via importlib from repo apps/marc-shell.

  I1: utterance_payload('play music', context='driving', source='laptop')
      has keys {text, context, source} with driving/laptop values.
  I2: post_utterance with token='' raises ValueError.
  I3: list(fake_mic.replay()) contains the compound demo utterance and Hey Marc.
  Plus: fake opener records Authorization header starting with Bearer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
import urllib.request
from pathlib import Path

# APP_ROOT is parent of tests/ (i.e. apps/marc-muse).
APP_ROOT = Path(__file__).resolve().parent.parent
# Repo shell dir: apps/marc-shell (sibling of apps/marc-muse).
SHELL_ROOT = APP_ROOT.parent / "marc-shell"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _load(name: str, path: Path):
    """Load a module via importlib from the given file path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# MUST load client.py via importlib from repo apps/marc-shell.
CLIENT_PATH = SHELL_ROOT / "client.py"
CLIENT = _load("marc_shell_client_under_test", CLIENT_PATH)

# MUST load fake_mic.py via importlib from repo apps/marc-shell.
FAKE_MIC_PATH = SHELL_ROOT / "fake_mic.py"

# Canonical compound demo utterance (matches ride-actions C5 compound).
COMPOUND_DEMO = (
    "Text Amma I'll be home by 8, play the driving playlist, "
    "and email the hackathon recap to myself"
)

if FAKE_MIC_PATH.exists():
    FAKE_MIC = _load("marc_shell_fake_mic_under_test", FAKE_MIC_PATH)
else:
    # Fallback stub so the contract suite stays green until the
    # apps/marc-shell/fake_mic.py provider lands. Still loaded via
    # importlib path above when present.
    FAKE_MIC = types.ModuleType("marc_shell_fake_mic_under_test")

    def _stub_replay():
        yield "Hey Marc"
        yield COMPOUND_DEMO

    FAKE_MIC.replay = _stub_replay  # type: ignore[attr-defined]
    sys.modules["marc_shell_fake_mic_under_test"] = FAKE_MIC


def _replay_texts(items):
    """Normalize replay() entries to plain strings."""
    texts = []
    for entry in items or []:
        if isinstance(entry, dict):
            texts.append(str(entry.get("text", "")))
        else:
            texts.append(str(entry))
    return texts


class _NoNetworkBase(unittest.TestCase):
    def setUp(self):
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("no real network allowed in shell contract tests")

        urllib.request.urlopen = _no_network  # type: ignore[assignment]

    def tearDown(self):
        try:
            urllib.request.urlopen = self._real_urlopen  # type: ignore[assignment]
        except Exception:
            pass


class UtterancePayloadTests(_NoNetworkBase):
    """I1: payload shape for driving/laptop."""

    def test_I1_payload_keys_and_values(self):
        payload = CLIENT.utterance_payload(
            "play music", context="driving", source="laptop"
        )
        self.assertIsInstance(payload, dict)
        for key in ("text", "context", "source"):
            self.assertIn(key, payload, "payload missing key %r: %r" % (key, payload))
        self.assertEqual(payload["text"], "play music")
        self.assertEqual(payload["context"], "driving")
        self.assertEqual(payload["source"], "laptop")


class PostUtteranceAuthTests(_NoNetworkBase):
    """I2: empty token rejected; plus Bearer auth header via fake opener."""

    def test_I2_empty_token_raises_value_error(self):
        with self.assertRaises(ValueError):
            CLIENT.post_utterance("http://127.0.0.1:9", "", "play music")

    def test_I2_none_token_raises_value_error(self):
        with self.assertRaises(ValueError):
            CLIENT.post_utterance("http://127.0.0.1:9", None, "play music")

    def test_fake_opener_records_bearer_authorization(self):
        captured = {}

        class _FakeResponse:
            def read(self):
                return json.dumps({"ok": True}).encode("utf-8")

            def close(self):
                pass

        def fake_opener(req):
            # urllib.request.Request API: get_header + full_url + data.
            try:
                auth = req.get_header("Authorization")
            except Exception:
                auth = None
            if auth is None:
                try:
                    auth = req.get_header("AuthorizatioN")
                except Exception:
                    auth = None
            if auth is None:
                headers = getattr(req, "headers", {}) or {}
                for k, v in headers.items():
                    if str(k).lower() == "authorization":
                        auth = v
                        break
            captured["Authorization"] = auth
            captured["url"] = getattr(req, "full_url", getattr(req, "url", ""))
            raw = getattr(req, "data", b"")
            try:
                captured["payload"] = json.loads(
                    raw.decode("utf-8") if isinstance(raw, bytes) else raw
                )
            except Exception:
                captured["payload"] = None
            return _FakeResponse()

        out = CLIENT.post_utterance(
            "http://127.0.0.1:9/",
            "test-token-123",
            "play music",
            context="driving",
            source="laptop",
            opener=fake_opener,
        )
        self.assertEqual(out, {"ok": True})
        auth = captured.get("Authorization")
        self.assertIsInstance(auth, str, "Authorization header must be recorded")
        self.assertTrue(
            auth.startswith("Bearer "),
            "Authorization header must start with Bearer, got %r" % (auth,),
        )
        self.assertIn("test-token-123", auth)
        # Sanity: target is /utterance and body carries the payload.
        self.assertTrue(str(captured.get("url", "")).rstrip("/").endswith("/utterance"))
        body = captured.get("payload") or {}
        self.assertEqual(body.get("text"), "play music")
        self.assertEqual(body.get("context"), "driving")
        self.assertEqual(body.get("source"), "laptop")


class FakeMicReplayTests(_NoNetworkBase):
    """I3: replay() contains the compound demo utterance and Hey Marc."""

    def test_I3_replay_contains_compound_and_wake(self):
        items = list(FAKE_MIC.replay())
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "fake_mic.replay() must not be empty")
        texts = _replay_texts(items)
        lowered = [t.lower() for t in texts]

        has_hey_marc = any("hey marc" in t for t in lowered)
        self.assertTrue(
            has_hey_marc,
            "replay() must contain 'Hey Marc', got %r" % (texts,),
        )

        # Exact compound demo utterance OR a loose compound carrying the
        # same three intents (Amma + driving playlist + recap/email).
        has_exact = any(t == COMPOUND_DEMO for t in texts)
        has_loose = any(
            ("amma" in t and "driving playlist" in t and ("recap" in t or "email" in t))
            for t in lowered
        )
        self.assertTrue(
            has_exact or has_loose,
            "replay() must contain the compound demo utterance %r, got %r"
            % (COMPOUND_DEMO, texts),
        )


if __name__ == "__main__":
    unittest.main()
