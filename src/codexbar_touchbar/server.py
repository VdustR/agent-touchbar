"""Loopback-only HTTP bridge used by BetterTouchTool widgets."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from urllib.parse import urlparse

from .core import APP_NAMES, StateStore, compact_snapshot
from .btt import previous_slot_count, update_buttons


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


def handler_factory(
    store: StateSource, action_tracker: ActionTracker | None = None
) -> type[BaseHTTPRequestHandler]:
    tracker = action_tracker or ActionTracker()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CodexBarTouchBar/0.1"

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
            if path == "/api/state":
                self.send_json(store.snapshot())
            elif path == "/api/btt":
                self.send_json(compact_snapshot(store.snapshot()))
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
                        "ok": status == HTTPStatus.OK,
                        "errors": snapshot["errors"],
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
                    tracker.record("session", "redacted", "received")
                    try:
                        store.focus_session(session_id)
                    except Exception:
                        tracker.record("session", "redacted", "failed")
                        raise
                    tracker.record("session", "redacted", "succeeded")
                    self.send_json({"ok": True, "id": session_id})
                    return
                if path == "/api/focus/provider":
                    provider = payload.get("provider")
                    if provider not in APP_NAMES:
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
        previous: dict[str, dict] = {}
        while True:
            try:
                state.refresh()
                state.wait_for_session_data()
                previous = update_buttons(
                    state.snapshot(), previous_slot_count(), previous
                )
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            time.sleep(0.25)

    threading.Thread(target=update_loop, daemon=True, name="btt-buttons").start()
    server_type = ThreadingHTTPServer
    if host == "::1":
        class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_type = IPv6ThreadingHTTPServer
    server_type((host, port), handler_factory(state)).serve_forever()
