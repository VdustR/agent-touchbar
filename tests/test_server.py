from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from codexbar_touchbar.server import ActionTracker, handler_factory


class FakeStore:
    def snapshot(self) -> dict[str, Any]:
        return {"generatedAt": "now", "sessions": [], "usage": [], "errors": {"sessions": None, "usage": {}}}

    def focus_session(self, session_id: str) -> None:
        if session_id != "valid":
            raise ValueError("Unknown or expired session id")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tracker = ActionTracker()
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), handler_factory(FakeStore(), cls.tracker)
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method: str, path: str, payload: object | None = None, content_type: str = "application/json", host: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=2)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": content_type} if body else {}
        if host:
            headers["Host"] = host
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        decoded = json.loads(response.read())
        connection.close()
        return response.status, decoded

    def test_health(self) -> None:
        status, body = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIsNone(body["lastAction"])

    def test_session_focus_rejects_unknown_id(self) -> None:
        status, body = self.request("POST", "/api/focus/session", {"id": "unknown"})
        self.assertEqual(status, 400)
        self.assertIn("expired", body["error"])

    def test_rejects_non_loopback_host_header(self) -> None:
        status, body = self.request("GET", "/api/state", host="attacker.example")
        self.assertEqual(status, 400)
        self.assertIn("Host", body["error"])

    def test_post_requires_json(self) -> None:
        status, body = self.request("POST", "/api/focus/session", {"id": "valid"}, "text/plain")
        self.assertEqual(status, 400)
        self.assertIn("Content-Type", body["error"])

    @patch("codexbar_touchbar.server.subprocess.run")
    def test_provider_focus_uses_allowlisted_app(self, run) -> None:
        status, body = self.request("POST", "/api/focus/provider", {"provider": "codex"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        run.assert_called_once_with(["/usr/bin/open", "-a", "ChatGPT"], check=True, timeout=8)
        action = self.tracker.snapshot()
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action["outcome"], "succeeded")
        self.assertEqual(action["target"], "codex")


if __name__ == "__main__":
    unittest.main()
