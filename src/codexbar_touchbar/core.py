"""CodexBar process adapter and normalized state model."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROVIDERS = ("codex", "claude", "antigravity")
APP_NAMES = {"codex": "ChatGPT", "claude": "Claude", "antigravity": "Antigravity"}
WINDOW_LABELS = {300: "5h", 10080: "7d"}


def find_executable(name: str, candidates: tuple[str, ...]) -> str:
    override = os.environ.get(f"CODEXBAR_TOUCHBAR_{name.upper()}")
    if override and Path(override).is_file():
        return override
    resolved = shutil.which(name)
    if resolved:
        return resolved
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
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
    state_rank = 0 if session.get("state") == "active" else 1
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
    def __init__(self, usage_ttl: float = 60, sessions_ttl: float = 0.75) -> None:
        self.usage_ttl = usage_ttl
        self.sessions_ttl = sessions_ttl
        self.lock = threading.Lock()
        self.sessions = Cache([])
        self.session_counts: dict[str, dict[str, int]] = {}
        self.usage = Cache([], error={})

    def _refresh_sessions(self) -> None:
        counts: dict[str, dict[str, int]] = {}
        try:
            value, error = run_codexbar("sessions", "--json-v2", timeout=8), None
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    provider = item.get("provider")
                    state = item.get("state")
                    if provider in PROVIDERS and state in {"active", "idle"}:
                        counts.setdefault(provider, {"active": 0, "idle": 0})[state] += 1
                codex_sessions = [
                    item
                    for item in value
                    if isinstance(item, dict) and item.get("provider") == "codex"
                ]
                value = codex_sessions
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as caught:
            value, error = None, str(caught)
        with self.lock:
            if value is not None:
                self.sessions.value = value
                self.session_counts = counts
            self.sessions.error = error
            self.sessions.updated_at = time.time()
            self.sessions.refreshing = False

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
                payload = run_codexbar("usage", "--provider", provider, "--format", "json")
                if isinstance(payload, list):
                    current.update(
                        (item["provider"], item)
                        for item in payload
                        if isinstance(item, dict) and isinstance(item.get("provider"), str)
                    )
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as caught:
                errors[provider] = str(caught)
        with self.lock:
            self.usage.value = [
                current.get(provider) or previous[provider]
                for provider in PROVIDERS
                if provider in current or provider in previous
            ]
            self.usage.error = errors
            self.usage.updated_at = time.time()
            self.usage.refreshing = False

    def _start_if_stale(self, cache: Cache, ttl: float, target: Any, name: str) -> None:
        with self.lock:
            if time.time() - cache.updated_at < ttl or cache.refreshing:
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
        subprocess.run(
            [codexbar_path(), "sessions", "focus", session_id],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )


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
        "lastActivityAt", "startedAt",
    )
    sessions = [{key: item.get(key) for key in session_keys} for item in snapshot["sessions"]]
    return {"generatedAt": snapshot["generatedAt"], "providers": providers, "sessions": sessions}
