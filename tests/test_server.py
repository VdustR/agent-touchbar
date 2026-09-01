from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from agent_touchbar.server import ActionTracker, RendererTracker, handler_factory, task_fingerprint


class FakeStore:
    include_usage = True

    def snapshot(self) -> dict[str, Any]:
        usage = [{"provider": "codex", "usage": {}}] if self.include_usage else []
        return {"generatedAt": "now", "sessions": [], "usage": usage, "errors": {"sessions": None, "usage": {}}}

    def focus_session(self, session_id: str) -> None:
        if session_id != "valid":
            raise ValueError("Unknown or expired session id")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tracker = ActionTracker()
        cls.renderer_tracker = RendererTracker()
        cls.renderer_tracker.heartbeat({"controlStrip": True, "systemModal": True})
        cls.store = FakeStore()
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            handler_factory(
                cls.store,
                cls.tracker,
                cls.renderer_tracker,
            ),
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
        self.assertEqual(body["service"], "agent-touchbar")
        self.assertTrue(body["ok"])
        self.assertIsNone(body["lastAction"])

    def test_health_requires_live_native_renderer(self) -> None:
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), handler_factory(self.store, renderer_tracker=RendererTracker())
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            body = json.loads(response.read())
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(response.status, 503)
        self.assertFalse(body["ok"])
        self.assertFalse(body["nativeRenderer"]["alive"])

    def test_native_state_contract_is_versioned_and_ordered(self) -> None:
        status, body = self.request("GET", "/api/v1/state")
        self.assertEqual(status, 200)
        self.assertEqual(body["schemaVersion"], 1)
        self.assertEqual(
            [item["id"] for item in body["items"]],
            ["quota:codex", "quota:claude", "quota:antigravity"],
        )

    def test_renderer_heartbeat_reports_capabilities_without_identity(self) -> None:
        status, body = self.request(
            "POST",
            "/api/v1/renderer/heartbeat",
            {"capabilities": {"controlStrip": True, "systemModal": False}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        status, health = self.request("GET", "/healthz")
        self.assertEqual(status, 503)
        self.assertFalse(health["ok"])
        self.assertTrue(health["nativeRenderer"]["alive"])
        self.assertEqual(
            health["nativeRenderer"]["capabilities"],
            {"controlStrip": True, "systemModal": False},
        )
        self.assertNotIn("task", json.dumps(health["nativeRenderer"]))

    def test_renderer_heartbeat_rejects_non_boolean_capabilities(self) -> None:
        status, body = self.request(
            "POST",
            "/api/v1/renderer/heartbeat",
            {"capabilities": {"controlStrip": "yes"}},
        )
        self.assertEqual(status, 400)
        self.assertIn("capabilities", body["error"])

    def test_health_requires_codex_usage(self) -> None:
        self.store.include_usage = False
        try:
            status, body = self.request("GET", "/healthz")
        finally:
            self.store.include_usage = True
        self.assertEqual(status, 503)
        self.assertFalse(body["ok"])

    def test_session_focus_rejects_unknown_id(self) -> None:
        status, body = self.request("POST", "/api/focus/session", {"id": "unknown"})
        self.assertEqual(status, 400)
        self.assertIn("expired", body["error"])

    def test_session_focus_records_privacy_safe_target_fingerprint(self) -> None:
        status, body = self.request("POST", "/api/focus/session", {"id": "valid"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        action = self.tracker.snapshot()
        assert action is not None
        self.assertEqual(action["target"], f"task:{task_fingerprint('valid')}")
        self.assertNotIn("valid", json.dumps(action))

    def test_native_task_focus_records_privacy_safe_target(self) -> None:
        status, body = self.request(
            "POST", "/api/v1/actions/focus-task", {"taskId": "valid"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["target"], f"task:{task_fingerprint('valid')}")

    @patch("agent_touchbar.server.subprocess.run")
    def test_native_provider_focus_uses_allowlisted_app(self, run) -> None:
        status, body = self.request(
            "POST", "/api/v1/actions/focus-provider", {"provider": "claude"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        run.assert_called_once_with(
            ["/usr/bin/open", "-a", "Claude"], check=True, timeout=8
        )

    def test_rejects_non_loopback_host_header(self) -> None:
        status, body = self.request("GET", "/api/v1/state", host="attacker.example")
        self.assertEqual(status, 400)
        self.assertIn("Host", body["error"])

    def test_raw_state_endpoint_is_not_exposed(self) -> None:
        status, body = self.request("GET", "/api/state")
        self.assertEqual(status, 404)
        self.assertEqual(body, {"error": "Not found"})

    def test_post_requires_json(self) -> None:
        status, body = self.request("POST", "/api/focus/session", {"id": "valid"}, "text/plain")
        self.assertEqual(status, 400)
        self.assertIn("Content-Type", body["error"])

    def test_provider_focus_rejects_non_string_provider(self) -> None:
        status, body = self.request("POST", "/api/focus/provider", {"provider": []})
        self.assertEqual(status, 400)
        self.assertIn("provider", body["error"])

    @patch("agent_touchbar.server.subprocess.run")
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
