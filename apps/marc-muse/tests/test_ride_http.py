"""Ride HTTP tests — GET /island and POST /utterance (stdlib only).

Run:
  python -m unittest discover -s apps/marc-muse/tests -v   # from repo root

Only localhost networking is used (ThreadingHTTPServer on 127.0.0.1:0).
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

# APP_ROOT is parent of tests/ (i.e. apps/marc-muse).
APP_ROOT = Path(__file__).resolve().parent.parent

# Register apps/marc-muse on sys.path so `server` sibling imports resolve.
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "marc_server_under_test", str(APP_ROOT / "server.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load server.py from %s" % (APP_ROOT / "server.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["marc_server_under_test"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


SERVER = _load_server()


class RideHttpTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = dict(os.environ)
        # Open auth: Handler treats missing MARC_TOKEN as allowed.
        os.environ.pop("MARC_TOKEN", None)
        # Never hit Muse spark / real network from planner.
        os.environ.pop("MODEL_API_KEY", None)
        os.environ.pop("MARC_SPARK_URL", None)
        os.environ.pop("MODEL_API_URL", None)
        os.environ["MARC_MODE"] = "sandbox"

        # Belt-and-braces: block urllib-based egress. Test client uses
        # http.client (localhost) so it is unaffected.
        self._real_urlopen = urllib.request.urlopen

        def _no_network(*args, **kwargs):
            raise AssertionError("network must not be used in ride http tests")

        urllib.request.urlopen = _no_network  # type: ignore[assignment]

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}
        )
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass
        try:
            self._thread.join(timeout=5)
        except Exception:
            pass
        try:
            urllib.request.urlopen = self._real_urlopen  # type: ignore[assignment]
        except Exception:
            pass
        os.environ.clear()
        os.environ.update(self._saved_env)

    # -- helpers ----------------------------------------------------
    def _request(self, method, path, payload=None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, resp.getheader("Content-Type") or "", raw
        finally:
            conn.close()

    def _get_json(self, path):
        status, ctype, raw = self._request("GET", path)
        try:
            data = json.loads(raw.decode("utf-8", "replace")) if raw else None
        except Exception:
            data = None
        return status, ctype, data

    def _post_json(self, path, payload):
        status, ctype, raw = self._request("POST", path, payload)
        try:
            data = json.loads(raw.decode("utf-8", "replace")) if raw else None
        except Exception:
            data = None
        return status, ctype, data

    # -- tests ------------------------------------------------------
    def test_island_returns_state_line_agents(self):
        status, ctype, data = self._get_json("/island")
        self.assertEqual(status, 200, "GET /island must be 200, got %r" % (data,))
        self.assertIn("application/json", ctype)
        self.assertIsInstance(data, dict)
        for key in ("state", "line", "agents"):
            self.assertIn(key, data, "GET /island missing key %r: %r" % (key, data))

    def test_utterance_open_spotify(self):
        payload = {"text": "open Spotify", "context": "desk", "source": "phone"}
        status, ctype, data = self._post_json("/utterance", payload)
        self.assertEqual(status, 200, "POST /utterance must be 200, got %r" % (data,))
        self.assertIn("application/json", ctype)
        self.assertIsInstance(data, dict)
        self.assertIsInstance(data.get("plan"), list)
        self.assertIsInstance(data.get("island"), dict)

    def test_utterance_empty_text_is_400(self):
        status, _ctype, data = self._post_json("/utterance", {"text": ""})
        self.assertEqual(status, 400, "POST /utterance {text:''} must be 400")


if __name__ == "__main__":
    unittest.main()
