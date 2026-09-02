"""CodexBar process adapter and normalized state model."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
from urllib.parse import urlparse
from urllib.request import urlopen

PROVIDERS = ("codex", "claude", "antigravity")
APP_NAMES = {"codex": "ChatGPT", "claude": "Claude", "antigravity": "Antigravity"}
WINDOW_LABELS = {300: "5h", 10080: "7d"}
ATTENTION_STATES = {"attention", "blocked", "needs_input", "waiting", "approval_required"}
DISPLAY_STATES = ATTENTION_STATES | {"active", "idle", "available"}
DEFAULT_SESSION_TTL = 10.0
CAPABILITIES = {
    "codex": {
        "tasks": {"supported": True, "source": "codexDesktop"},
        "focusTask": {"supported": True, "source": "codexDeeplink"},
        "quota": {"supported": True, "source": "codexbar"},
    },
    "claude": {
        "tasks": {"supported": True, "source": "claudeDesktop"},
        "focusTask": {"supported": False, "source": None},
        "quota": {"supported": True, "source": "codexbar"},
    },
    "antigravity": {
        "tasks": {"supported": True, "source": "antigravityDesktop"},
        "focusTask": {"supported": False, "source": None},
        "quota": {"supported": True, "source": "codexbar"},
    },
}


class ProviderAdapter(Protocol):
    def sessions(self) -> Any: ...
    def usage(self, provider: str) -> Any: ...


class CodexBarAdapter:
    """Keep CodexBar behind the capabilities it still serves reliably."""

    def sessions(self) -> Any:
        return run_codexbar("sessions", "--json-v2", timeout=8)

    def usage(self, provider: str) -> Any:
        return run_codexbar("usage", "--provider", provider, "--format", "json")


def find_executable(name: str, candidates: tuple[str, ...]) -> str:
    def absolute(path: str) -> str:
        return str(Path(path).expanduser().absolute())

    override = os.environ.get(f"AGENT_TOUCHBAR_{name.upper()}")
    if override and Path(override).is_file():
        return absolute(override)
    resolved = shutil.which(name)
    if resolved:
        return absolute(resolved)
    for candidate in candidates:
        if Path(candidate).is_file():
            return absolute(candidate)
    raise FileNotFoundError(f"Required executable not found: {name}")


def codexbar_path() -> str:
    return find_executable("codexbar", ("/opt/homebrew/bin/codexbar", "/usr/local/bin/codexbar"))


def run_codexbar(*args: str, timeout: int = 20) -> Any:
    result = subprocess.run(
        [codexbar_path(), *args], check=True, capture_output=True, text=True, timeout=timeout
    )
    return json.loads(result.stdout)


def quota_windows(provider: dict[str, Any]) -> list[dict[str, Any]]:
    usage = provider.get("usage") or {}
    extra = usage.get("extraRateWindows")
    if provider.get("provider") == "antigravity" and isinstance(extra, list) and extra:
        windows = []
        for item in extra:
            if not isinstance(item, dict) or not isinstance(item.get("window"), dict):
                continue
            window = item["window"]
            title = item.get("title")
            minutes = window.get("windowMinutes")
            period = WINDOW_LABELS.get(minutes, "limit") if isinstance(minutes, int) else "limit"
            scope = title.removesuffix(" weekly") if isinstance(title, str) and title else ""
            if scope.endswith("5-hour"):
                scope = scope.removesuffix("5-hour").strip()
            label = f"{scope} {period}".strip()
            windows.append({"label": label, **window})
        if windows:
            return windows
    windows: list[dict[str, Any]] = []
    for key, fallback in (("primary", "primary"), ("secondary", "secondary"), ("tertiary", "tertiary")):
        window = usage.get(key)
        if not isinstance(window, dict):
            continue
        raw_minutes = window.get("windowMinutes")
        minutes = raw_minutes if isinstance(raw_minutes, int) else None
        label = WINDOW_LABELS.get(minutes, fallback) if minutes is not None else fallback
        windows.append({"label": label, **window})
    return windows


def session_sort_key(session: dict[str, Any]) -> tuple[int, float]:
    state = session.get("state")
    state_rank = (
        0
        if isinstance(state, str) and state in ATTENTION_STATES
        else {"active": 1, "available": 2, "idle": 3}.get(state if isinstance(state, str) else "", 4)
    )
    raw = session.get("lastActivityAt") or session.get("startedAt") or ""
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        timestamp = 0.0
    return state_rank, -timestamp


@dataclass
class Cache:
    value: Any
    updated_at: float = 0.0
    error: Any = None
    refreshing: bool = False


class StateStore:
    def __init__(
        self,
        usage_ttl: float = 60,
        sessions_ttl: float = DEFAULT_SESSION_TTL,
        provider_adapter: ProviderAdapter | None = None,
    ) -> None:
        self.usage_ttl = usage_ttl
        self.sessions_ttl = sessions_ttl
        self.lock = threading.Lock()
        self.sessions = Cache([])
        self.session_counts: dict[str, dict[str, int]] = {}
        self.usage = Cache([], error={})
        self.provider_adapter = provider_adapter or CodexBarAdapter()

    def _refresh_sessions(self) -> None:
        counts: dict[str, dict[str, int]] = {}
        runtime_sessions: list[dict[str, Any]] = []
        runtime_error: str | None = None
        try:
            payload = self.provider_adapter.sessions()
            if not isinstance(payload, list):
                raise ValueError("CodexBar session payload is not a list")
            runtime_sessions = [item for item in payload if isinstance(item, dict)]
            for item in runtime_sessions:
                if not isinstance(item, dict):
                    continue
                provider = item.get("provider")
                state = item.get("state")
                if (
                    isinstance(provider, str)
                    and isinstance(state, str)
                    and provider in PROVIDERS
                    and state in {"active", "idle"}
                ):
                    counts.setdefault(provider, {"active": 0, "idle": 0})[state] += 1
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as caught:
            runtime_error = str(caught)

        value: list[dict[str, Any]] | None
        try:
            value = []
            codex_runtime = [
                item for item in runtime_sessions
                if item.get("provider") == "codex" and isinstance(item.get("id"), str)
            ]
            codexbar_codex = {
                item["id"]: item for item in codex_runtime
            }
            desktop_codex = self._codex_desktop_sessions()
            for item in desktop_codex:
                runtime = codexbar_codex.get(item["id"])
                if runtime:
                    item.update(runtime)
                value.append(item)

            claude_titles = self._claude_desktop_titles()
            for item in runtime_sessions:
                session_id = item.get("id")
                if item.get("provider") != "claude" or not isinstance(session_id, str):
                    continue
                title = claude_titles.get(session_id)
                if not title:
                    continue
                value.append({**item, "sessionName": title, "source": "desktopApp"})

            value.extend(self._antigravity_desktop_sessions())
            codex_counts = {"active": 0, "idle": 0}
            for item in value:
                if item.get("provider") == "codex" and item.get("state") in codex_counts:
                    codex_counts[item["state"]] += 1
            counts["codex"] = codex_counts
            error = runtime_error
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as caught:
            value, error = None, str(caught)
        with self.lock:
            if value is not None:
                self.sessions.value = value
                self.session_counts = counts
            self.sessions.error = error
            self.sessions.updated_at = time.monotonic()
            self.sessions.refreshing = False

    @staticmethod
    def _codex_desktop_sessions() -> list[dict[str, Any]]:
        override = os.environ.get("AGENT_TOUCHBAR_CODEX_STATE_DB")
        path = Path(override).expanduser() if override else Path.home() / ".codex/state_5.sqlite"
        if not path.is_file():
            raise ValueError("Codex Desktop task registry is unavailable")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.2)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT id, name, cwd, recency_at
                FROM threads
                WHERE archived = 0
                  AND source = 'vscode'
                  AND preview <> ''
                  AND name IS NOT NULL
                  AND name <> ''
                ORDER BY recency_at_ms DESC
                """
            ).fetchall()
        except (OSError, sqlite3.Error) as error:
            raise ValueError("Codex Desktop task registry is unavailable") from error
        finally:
            if connection is not None:
                connection.close()
        return [
            {
                "id": row["id"],
                "provider": "codex",
                "projectName": Path(row["cwd"]).name,
                "sessionName": row["name"],
                "state": "idle",
                "source": "desktopApp",
                "lastActivityAt": datetime.fromtimestamp(
                    row["recency_at"]
                ).astimezone().isoformat(),
            }
            for row in rows
        ]

    @staticmethod
    def _claude_desktop_titles() -> dict[str, str]:
        override = os.environ.get("AGENT_TOUCHBAR_CLAUDE_SESSION_DIR")
        root = Path(override).expanduser() if override else (
            Path.home() / "Library/Application Support/Claude/claude-code-sessions"
        )
        if not root.is_dir():
            return {}
        titles: dict[str, tuple[int, str]] = {}
        for path in root.glob("*/*/local_*.json"):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            session_id = data.get("cliSessionId")
            title = data.get("title")
            if (
                data.get("isArchived") is True
                or not isinstance(session_id, str)
                or not isinstance(title, str)
                or not title.strip()
            ):
                continue
            activity = data.get("lastActivityAt")
            timestamp = activity if isinstance(activity, int) else 0
            previous = titles.get(session_id)
            if previous is None or timestamp >= previous[0]:
                titles[session_id] = (timestamp, title.strip())
        return {session_id: value[1] for session_id, value in titles.items()}

    @staticmethod
    def _antigravity_desktop_sessions() -> list[dict[str, Any]]:
        override = os.environ.get("AGENT_TOUCHBAR_ANTIGRAVITY_DEVTOOLS_PORT")
        port_file = Path(override).expanduser() if override else (
            Path.home() / "Library/Application Support/Antigravity/DevToolsActivePort"
        )
        if not port_file.is_file():
            return []
        try:
            port = int(port_file.read_text().splitlines()[0])
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=0.5) as response:
                targets = json.loads(response.read())
            target = next(
                item for item in targets
                if item.get("type") == "page" and item.get("title") == "Antigravity"
            )
            expression = """JSON.stringify([...document.querySelectorAll('[aria-label="Sidebar"] a[href]')].map(a => ({id: a.getAttribute('href'), title: (a.innerText || '').trim()})).filter(x => x.id && x.title && x.id !== '/' && x.id !== '/history' && !x.id.startsWith('/?')))"""
            value = _websocket_evaluate(target["webSocketDebuggerUrl"], expression)
            items = json.loads(value)
        except (OSError, ValueError, KeyError, StopIteration, json.JSONDecodeError):
            return []
        return [
            {
                "id": f"antigravity:{item['id']}",
                "provider": "antigravity",
                "sessionName": item["title"],
                "state": "idle",
                "source": "desktopApp",
            }
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("title"), str)
        ]

    def _refresh_usage(self) -> None:
        with self.lock:
            previous = {
                item.get("provider"): item
                for item in self.usage.value
                if isinstance(item, dict) and isinstance(item.get("provider"), str)
            }
        current: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        for provider in PROVIDERS:
            try:
                payload = self.provider_adapter.usage(provider)
                if not isinstance(payload, list):
                    raise ValueError("CodexBar usage payload is not a list")
                if any(
                    not isinstance(item, dict)
                    or item.get("provider") != provider
                    or not isinstance(item.get("usage"), dict)
                    for item in payload
                ):
                    raise ValueError("CodexBar usage entry has an invalid shape")
                current.update(
                    (item["provider"], item)
                    for item in payload
                    if isinstance(item, dict) and isinstance(item.get("provider"), str)
                )
                with self.lock:
                    published = {
                        item["provider"]: item
                        for item in self.usage.value
                        if isinstance(item, dict) and isinstance(item.get("provider"), str)
                    }
                    published.pop(provider, None)
                    published.update(current)
                    self.usage.value = [
                        published[item] for item in PROVIDERS if item in published
                    ]
                    self.usage.error = dict(errors)
                    self.usage.updated_at = time.monotonic()
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as caught:
                errors[provider] = str(caught)
                with self.lock:
                    self.usage.error = dict(errors)
                    self.usage.updated_at = time.monotonic()
        with self.lock:
            self.usage.value = [
                current[provider] if provider in current else previous[provider]
                for provider in PROVIDERS
                if provider in current or (provider in errors and provider in previous)
            ]
            self.usage.error = errors
            self.usage.updated_at = time.monotonic()
            self.usage.refreshing = False

    def _start_if_stale(self, cache: Cache, ttl: float, target: Any, name: str) -> None:
        with self.lock:
            if cache.refreshing or (
                cache.updated_at != 0 and time.monotonic() - cache.updated_at < ttl
            ):
                return
            cache.refreshing = True
        threading.Thread(target=target, daemon=True, name=name).start()

    def refresh(self) -> None:
        self._start_if_stale(self.sessions, self.sessions_ttl, self._refresh_sessions, "sessions")
        self._start_if_stale(self.usage, self.usage_ttl, self._refresh_usage, "usage")

    def wait_for_initial_data(self, timeout: float = 25) -> None:
        self.refresh()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if not self.sessions.refreshing and not self.usage.refreshing:
                    return
            time.sleep(0.05)

    def wait_for_session_data(self, timeout: float = 9) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if not self.sessions.refreshing:
                    return
            time.sleep(0.05)

    def snapshot(self) -> dict[str, Any]:
        self.refresh()
        with self.lock:
            sessions = [dict(item) for item in sorted(self.sessions.value, key=session_sort_key)]
            return {
                "generatedAt": datetime.now().astimezone().isoformat(),
                "sessions": sessions,
                "sessionCounts": self.session_counts,
                "usage": self.usage.value,
                "errors": {"sessions": self.sessions.error, "usage": self.usage.error},
                "capabilities": CAPABILITIES,
            }

    def focus_session(self, session_id: str) -> None:
        with self.lock:
            session = next(
                (dict(item) for item in self.sessions.value if item.get("id") == session_id),
                None,
            )
        if session is None:
            raise ValueError("Unknown or expired session id")
        provider = session.get("provider")
        if session.get("source") == "desktopApp" and provider == "codex":
            subprocess.run(
                ["/usr/bin/open", f"codex://threads/{quote(session_id, safe='')}"],
                check=True,
                timeout=3,
            )
            return
        if session.get("source") == "desktopApp" and provider in APP_NAMES:
            subprocess.run(
                ["/usr/bin/open", "-a", APP_NAMES[provider]],
                check=True,
                timeout=3,
            )
            return
        raise ValueError("Task does not support exact focus")


def _websocket_evaluate(websocket_url: str, expression: str) -> str:
    parsed = urlparse(websocket_url)
    if parsed.hostname != "127.0.0.1" or not parsed.port:
        raise ValueError("Antigravity DevTools endpoint must be loopback")
    key = base64.b64encode(os.urandom(16)).decode()
    connection = socket.create_connection((parsed.hostname, parsed.port), timeout=0.5)
    connection.settimeout(0.5)
    try:
        request = (
            f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        connection.sendall(request.encode())
        headers = b""
        while b"\r\n\r\n" not in headers:
            headers += connection.recv(4096)
        if not headers.startswith(b"HTTP/1.1 101"):
            raise ValueError("Antigravity DevTools websocket rejected the connection")
        payload = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }).encode()
        mask = os.urandom(4)
        length = len(payload)
        header = bytes([0x81, 0x80 | (126 if length >= 126 else length)])
        if length >= 126:
            header += length.to_bytes(2, "big")
        connection.sendall(header + mask + bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload)))
        first = connection.recv(2)
        response_length = first[1] & 0x7F
        if response_length == 126:
            response_length = int.from_bytes(connection.recv(2), "big")
        elif response_length == 127:
            response_length = int.from_bytes(connection.recv(8), "big")
        response = b""
        while len(response) < response_length:
            response += connection.recv(response_length - len(response))
        message = json.loads(response)
        return message["result"]["result"]["value"]
    finally:
        connection.close()


def compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    providers = [
        {
            "provider": item.get("provider"),
            "windows": quota_windows(item),
            "confidence": (item.get("usage") or {}).get("dataConfidence"),
            "sessionCounts": snapshot.get("sessionCounts", {}).get(item.get("provider")),
        }
        for item in snapshot["usage"]
    ]
    session_keys = (
        "id", "provider", "projectName", "sessionName", "state", "source",
        "lastActivityAt", "startedAt", "appSessionId",
    )
    sessions = [{key: item.get(key) for key in session_keys} for item in snapshot["sessions"]]
    return {
        "generatedAt": snapshot["generatedAt"],
        "providers": providers,
        "sessions": sessions,
        "capabilities": snapshot.get("capabilities", CAPABILITIES),
    }


def renderer_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build the ordered, renderer-neutral local UI contract."""
    compact = compact_snapshot(snapshot)
    attention: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    for session in sorted(compact["sessions"], key=session_sort_key):
        session_id = session.get("id")
        if not isinstance(session_id, str):
            continue
        name = session.get("sessionName")
        if not isinstance(name, str) or not name:
            continue
        label = name
        provider = session.get("provider")
        if provider not in PROVIDERS:
            continue
        item = {
            "id": f"task:{session_id}",
            "kind": "task",
            "provider": provider,
            "label": label,
            "state": session.get("state") or "idle",
            "iconProvider": provider,
            "action": {"type": "focusTask", "taskId": session_id},
        }
        (attention if session.get("state") in ATTENTION_STATES else tasks).append(item)

    quota_items: list[dict[str, Any]] = []
    for provider in PROVIDERS:
        data = next(
            (item for item in compact["providers"] if item.get("provider") == provider),
            None,
        )
        windows = data.get("windows", []) if isinstance(data, dict) else []
        if provider == "antigravity":
            windows = [
                window for window in windows
                if str(window.get("label", "")).startswith("Gemini ")
            ]
            for window in windows:
                label = str(window.get("label", ""))
                if label.startswith("Gemini "):
                    window["label"] = label.removeprefix("Gemini ")
        counts = snapshot.get("sessionCounts", {}).get(provider)
        parts: list[str] = []
        remaining: list[float] = []
        for window in windows:
            used = window.get("usedPercent") if isinstance(window, dict) else None
            if isinstance(used, (int, float)) and not isinstance(used, bool):
                value = 100 - used
                remaining.append(value)
                parts.append(f"{window.get('label', 'limit')} {value:.0f}%")
        lowest = min(remaining) if remaining else None
        health = (
            "unavailable"
            if lowest is None
            else "healthy"
            if lowest >= 50
            else "warning"
            if lowest >= 20
            else "critical"
        )
        quota_items.append(
            {
                "id": f"quota:{provider}",
                "kind": "quota",
                "provider": provider,
                "label": " · ".join(parts) or "—",
                "state": health,
                "iconProvider": provider,
                "windows": windows,
                "sessionCounts": counts,
                "action": {"type": "focusProvider", "provider": provider},
            }
        )
    return {
        "schemaVersion": 1,
        "generatedAt": compact["generatedAt"],
        "items": [*attention, *quota_items, *tasks],
        "capabilities": compact["capabilities"],
    }
