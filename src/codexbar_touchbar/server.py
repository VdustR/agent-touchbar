"""Loopback-only HTTP bridge used by the native Touch Bar renderer."""

from __future__ import annotations

import json
import hashlib
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from urllib.parse import urlparse

from .core import APP_NAMES, StateStore, renderer_snapshot


class StateSource(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def focus_session(self, session_id: str) -> None: ...


class ActionTracker:
    """Keep a privacy-minimized record of the latest Touch Bar action."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: dict[str, Any] | None = None

    def record(self, kind: str, target: str, outcome: str) -> None:
        with self._lock:
            self._value = {
                "kind": kind,
                "target": target,
                "outcome": outcome,
                "at": datetime.now(timezone.utc).isoformat(),
            }

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._value) if self._value else None


def task_fingerprint(task_id: str) -> str:
    return hashlib.sha256(task_id.encode()).hexdigest()[:10]


class RendererTracker:
    """Track the native renderer without recording user or task identity."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: dict[str, Any] | None = None

    def heartbeat(self, capabilities: dict[str, bool]) -> None:
        with self._lock:
            self._value = {
                "lastSeenAt": datetime.now(timezone.utc).isoformat(),
                "lastSeenMonotonic": time.monotonic(),
                "capabilities": dict(capabilities),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._value is None:
                return {"alive": False, "lastSeenAt": None, "capabilities": {}}
            return {
                "alive": time.monotonic() - self._value["lastSeenMonotonic"] < 10,
                "lastSeenAt": self._value["lastSeenAt"],
                "capabilities": dict(self._value["capabilities"]),
            }


def handler_factory(
    store: StateSource,
    action_tracker: ActionTracker | None = None,
    renderer_tracker: RendererTracker | None = None,
) -> type[BaseHTTPRequestHandler]:
    tracker = action_tracker or ActionTracker()
    native_tracker = renderer_tracker or RendererTracker()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CodexBarTouchBar"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def read_payload(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise ValueError("Content-Type must be application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("Invalid request size")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Invalid request body")
            return value

        def allowed_host(self) -> bool:
            port = int(getattr(self.server, "server_port", 4317))
            return self.headers.get("Host", "") in {
                f"127.0.0.1:{port}",
                f"localhost:{port}",
                f"[::1]:{port}",
            }

        def reject_untrusted_host(self) -> bool:
            if self.allowed_host():
                return False
            self.send_json({"error": "Untrusted Host header"}, HTTPStatus.BAD_REQUEST)
            return True

        def do_GET(self) -> None:
            if self.reject_untrusted_host():
                return
            path = urlparse(self.path).path
            if path == "/api/v1/state":
                self.send_json(renderer_snapshot(store.snapshot()))
            elif path == "/healthz":
                snapshot = store.snapshot()
                providers = {
                    item.get("provider")
                    for item in snapshot["usage"]
                    if isinstance(item, dict)
                }
                healthy = (
                    not snapshot["errors"]["sessions"]
                    and "codex" not in snapshot["errors"]["usage"]
                    and "codex" in providers
                )
                status = HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
                self.send_json(
                    {
                        "service": "codexbar-touchbar",
                        "ok": status == HTTPStatus.OK,
                        "errors": snapshot["errors"],
                        "nativeRenderer": native_tracker.snapshot(),
                        "lastAction": tracker.snapshot(),
                    },
                    status,
                )
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.reject_untrusted_host():
                return
            try:
                payload = self.read_payload()
                path = urlparse(self.path).path
                if path == "/api/focus/session":
                    session_id = payload.get("id")
                    if not isinstance(session_id, str) or len(session_id) > 128:
                        raise ValueError("Invalid session id")
                    target = f"task:{task_fingerprint(session_id)}"
                    tracker.record("session", target, "received")
                    try:
                        store.focus_session(session_id)
                    except Exception:
                        tracker.record("session", target, "failed")
                        raise
                    tracker.record("session", target, "succeeded")
                    self.send_json({"ok": True, "id": session_id})
                    return
                if path == "/api/v1/actions/focus-task":
                    session_id = payload.get("taskId")
                    if not isinstance(session_id, str) or len(session_id) > 128:
                        raise ValueError("Invalid task id")
                    target = f"task:{task_fingerprint(session_id)}"
                    tracker.record("session", target, "received")
                    try:
                        store.focus_session(session_id)
                    except Exception:
                        tracker.record("session", target, "failed")
                        raise
                    tracker.record("session", target, "succeeded")
                    self.send_json({"ok": True, "target": target})
                    return
                if path == "/api/focus/provider":
                    provider = payload.get("provider")
                    if not isinstance(provider, str) or provider not in APP_NAMES:
                        raise ValueError("Unknown provider")
                    tracker.record("provider", provider, "received")
                    try:
                        subprocess.run(
                            ["/usr/bin/open", "-a", APP_NAMES[provider]], check=True, timeout=8
                        )
                    except Exception:
                        tracker.record("provider", provider, "failed")
                        raise
                    tracker.record("provider", provider, "succeeded")
                    self.send_json({"ok": True, "provider": provider})
                    return
                if path == "/api/v1/actions/focus-provider":
                    provider = payload.get("provider")
                    if not isinstance(provider, str) or provider not in APP_NAMES:
                        raise ValueError("Unknown provider")
                    tracker.record("provider", provider, "received")
                    try:
                        subprocess.run(
                            ["/usr/bin/open", "-a", APP_NAMES[provider]],
                            check=True,
                            timeout=8,
                        )
                    except Exception:
                        tracker.record("provider", provider, "failed")
                        raise
                    tracker.record("provider", provider, "succeeded")
                    self.send_json({"ok": True, "provider": provider})
                    return
                if path == "/api/v1/renderer/heartbeat":
                    capabilities = payload.get("capabilities")
                    if not isinstance(capabilities, dict) or any(
                        not isinstance(key, str) or not isinstance(value, bool)
                        for key, value in capabilities.items()
                    ):
                        raise ValueError("Invalid renderer capabilities")
                    native_tracker.heartbeat(capabilities)
                    self.send_json({"ok": True})
                    return
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except (OSError, subprocess.SubprocessError) as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)

    return Handler


def serve(host: str, port: int, store: StateStore | None = None) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("The bridge only permits a loopback host")
    state = store or StateStore()
    state.wait_for_initial_data()
    def update_loop() -> None:
        retry_delay = 0.25
        while True:
            try:
                state.refresh()
                state.wait_for_session_data()
                retry_delay = 0.25
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                retry_delay = min(max(retry_delay * 2, 1.0), 8.0)
            time.sleep(retry_delay)

    threading.Thread(target=update_loop, daemon=True, name="state-refresh").start()
    server_type = ThreadingHTTPServer
    if host == "::1":
        class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_type = IPv6ThreadingHTTPServer
    server_type((host, port), handler_factory(state)).serve_forever()
