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
ATTENTION_STATES = {"attention", "blocked", "needs_input", "waiting", "approval_required"}
DISPLAY_STATES = ATTENTION_STATES | {"active", "idle", "available"}


def find_executable(name: str, candidates: tuple[str, ...]) -> str:
    def absolute(path: str) -> str:
        return str(Path(path).expanduser().absolute())

    override = os.environ.get(f"CODEXBAR_TOUCHBAR_{name.upper()}")
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
    def __init__(self, usage_ttl: float = 60, sessions_ttl: float = 0.75) -> None:
        self.usage_ttl = usage_ttl
        self.sessions_ttl = sessions_ttl
        self.lock = threading.Lock()
        self.sessions = Cache([])
        self.session_counts: dict[str, dict[str, int]] = {}
        self.usage = Cache([], error={})
        self._claude_title_cache: dict[str, dict[str, str]] = {}
        self._claude_title_cache_at = 0.0

    def _refresh_sessions(self) -> None:
        counts: dict[str, dict[str, int]] = {}
        try:
            value, error = run_codexbar("sessions", "--json-v2", timeout=8), None
            if not isinstance(value, list):
                raise ValueError("CodexBar session payload is not a list")
            for item in value:
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
            value = [
                item
                for item in value
                if isinstance(item, dict)
                and item.get("provider") in {"codex", "claude"}
                and isinstance(item.get("id"), str)
                and isinstance(item.get("state"), str)
                and item.get("state") in DISPLAY_STATES
                and item.get("source") == "desktopApp"
            ]
            claude_titles = self._claude_titles()
            for item in value:
                if item.get("provider") == "claude":
                    metadata = claude_titles.get(item["id"])
                    if metadata:
                        item["sessionName"] = metadata.get("title")
                        item["appSessionId"] = metadata.get("sessionId")
            if self._app_is_running("Antigravity"):
                value.append({
                    "id": "app:antigravity",
                    "provider": "antigravity",
                    "sessionName": "Antigravity Desktop",
                    "state": "available",
                    "source": "appPresence",
                })
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as caught:
            value, error = None, str(caught)
        with self.lock:
            if value is not None:
                self.sessions.value = value
                self.session_counts = counts
            self.sessions.error = error
            self.sessions.updated_at = time.monotonic()
            self.sessions.refreshing = False

    def _claude_titles(self) -> dict[str, dict[str, str]]:
        now = time.monotonic()
        if self._claude_title_cache_at and now - self._claude_title_cache_at < 5:
            return self._claude_title_cache
        root = Path.home() / "Library/Application Support/Claude/claude-code-sessions"
        result: dict[str, dict[str, str]] = {}
        for path in root.glob("*/*/*.json"):
            try:
                item = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(item, dict) or not isinstance(item.get("cliSessionId"), str):
                continue
            result[item["cliSessionId"]] = {
                key: value
                for key in ("title", "sessionId")
                if isinstance((value := item.get(key)), str) and value
            }
        self._claude_title_cache = result
        self._claude_title_cache_at = now
        return result

    @staticmethod
    def _app_is_running(name: str) -> bool:
        return subprocess.run(
            ["/usr/bin/pgrep", "-x", name], capture_output=True, timeout=2
        ).returncode == 0

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
        if provider in APP_NAMES:
            if provider == "claude":
                try:
                    subprocess.run(
                        [codexbar_path(), "sessions", "focus", session_id],
                        check=True, capture_output=True, text=True, timeout=8,
                    )
                    return
                except subprocess.SubprocessError:
                    pass
            subprocess.run(
                ["/usr/bin/open", "-a", APP_NAMES[provider]], check=True, timeout=8
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
        "lastActivityAt", "startedAt", "appSessionId",
    )
    sessions = [{key: item.get(key) for key in session_keys} for item in snapshot["sessions"]]
    return {"generatedAt": snapshot["generatedAt"], "providers": providers, "sessions": sessions}
