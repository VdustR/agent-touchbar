from __future__ import annotations

import os
import json
import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_touchbar.core import CAPABILITIES, StateStore, compact_snapshot, find_executable, quota_windows, renderer_snapshot, session_sort_key


class CoreTests(unittest.TestCase):
    def test_find_executable_preserves_stable_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "versioned"
            link = root / "stable"
            target.write_text("")
            link.symlink_to(target)
            with patch.dict(os.environ, {"AGENT_TOUCHBAR_TOOL": str(link)}):
                self.assertEqual(find_executable("tool", ()), str(link))

    def test_session_refresh_interval_prioritizes_interactive_updates(self) -> None:
        self.assertLessEqual(StateStore().sessions_ttl, 0.75)

    @patch("agent_touchbar.core.subprocess.run")
    def test_codex_session_focus_uses_thread_deep_link(self, run) -> None:
        store = StateStore()
        store.sessions.value = [
            {"id": "thread/id", "provider": "codex", "source": "desktopApp"}
        ]
        store.focus_session("thread/id")
        run.assert_called_once_with(
            ["/usr/bin/open", "codex://threads/thread%2Fid"], check=True, timeout=3
        )

    @patch("agent_touchbar.core.subprocess.run")
    def test_non_codex_session_focus_opens_provider_app(self, run) -> None:
        store = StateStore()
        store.sessions.value = [
            {"id": "claude", "provider": "claude", "source": "desktopApp"}
        ]
        store.focus_session("claude")
        run.assert_called_once_with(
            ["/usr/bin/open", "-a", "Claude"], check=True, timeout=3
        )

    def test_session_refresh_only_overlays_native_codex_tasks(self) -> None:
        store = StateStore()
        sessions = [
            {"id": "codex", "provider": "codex", "state": "active", "source": "desktopApp"},
            {"id": "claude", "provider": "claude"},
            {"id": "antigravity", "provider": "antigravity"},
        ]
        native = [{"id": "codex", "provider": "codex", "state": "idle", "source": "desktopApp"}]
        with patch("agent_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_codex_desktop_sessions", return_value=native):
            store._refresh_sessions()
        self.assertEqual(
            store.sessions.value,
            [{"id": "codex", "provider": "codex", "state": "active", "source": "desktopApp"}],
        )

    def test_session_refresh_rejects_codex_sessions_without_string_ids(self) -> None:
        store = StateStore()
        sessions = [
            {"provider": "codex", "state": "active", "source": "desktopApp"},
            {"id": None, "provider": "codex", "state": "idle", "source": "desktopApp"},
            {"id": "valid", "provider": "codex", "state": "active", "source": "desktopApp"},
        ]
        native = [{
            "id": "valid",
            "provider": "codex",
            "state": "idle",
            "source": "desktopApp",
        }]
        with patch("agent_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_codex_desktop_sessions", return_value=native):
            store._refresh_sessions()
        self.assertEqual([item["id"] for item in store.sessions.value], ["valid"])

    def test_session_refresh_loads_native_tasks_when_runtime_payload_is_invalid(self) -> None:
        store = StateStore()
        store.sessions.value = [{"id": "cached", "provider": "codex"}]
        native = [{"id": "native", "provider": "codex", "sessionName": "Native", "state": "idle", "source": "desktopApp"}]
        with (
            patch("agent_touchbar.core.run_codexbar", return_value={}),
            patch.object(store, "_codex_desktop_sessions", return_value=native),
            patch.object(store, "_claude_desktop_titles", return_value={}),
            patch.object(store, "_antigravity_desktop_sessions", return_value=[]),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, native)
        self.assertIn("not a list", store.sessions.error)
        self.assertFalse(store.sessions.refreshing)

    def test_session_refresh_counts_supported_states_for_each_provider(self) -> None:
        store = StateStore()
        sessions = [
            {"id": "1", "provider": "claude", "state": "active"},
            {"id": "2", "provider": "claude", "state": "idle"},
            {"id": "3", "provider": "claude", "state": "unknown"},
        ]
        with patch("agent_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_codex_desktop_sessions", return_value=[]):
            store._refresh_sessions()
        self.assertEqual(store.session_counts["claude"], {"active": 1, "idle": 1})

    def test_session_refresh_ignores_non_string_states(self) -> None:
        store = StateStore()
        sessions = [
            {"id": "invalid", "provider": "codex", "state": [], "source": "desktopApp"},
            {"id": "valid", "provider": "codex", "state": "active", "source": "desktopApp"},
        ]
        native = [{
            "id": "valid",
            "provider": "codex",
            "state": "idle",
            "source": "desktopApp",
        }]
        with patch("agent_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_codex_desktop_sessions", return_value=native):
            store._refresh_sessions()
        self.assertEqual(store.session_counts["codex"], {"active": 1, "idle": 0})
        self.assertFalse(store.sessions.refreshing)
        self.assertEqual([item["id"] for item in store.sessions.value], ["valid"])

    def test_empty_native_registry_never_falls_back_to_codexbar_tasks(self) -> None:
        store = StateStore()
        runtime = [{
            "id": "runtime-only",
            "provider": "codex",
            "state": "active",
            "source": "desktopApp",
        }]
        with (
            patch("agent_touchbar.core.run_codexbar", return_value=runtime),
            patch.object(store, "_codex_desktop_sessions", return_value=[]),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, [])
        self.assertEqual(store.session_counts["codex"], {"active": 0, "idle": 0})

    def test_missing_native_registry_preserves_cached_tasks_and_reports_error(self) -> None:
        store = StateStore()
        store.sessions.value = [{"id": "cached", "provider": "codex", "state": "idle"}]
        with (
            patch.dict(os.environ, {"AGENT_TOUCHBAR_CODEX_STATE_DB": "/missing/state.sqlite"}),
            patch("agent_touchbar.core.run_codexbar", return_value=[]),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value[0]["id"], "cached")
        self.assertIn("registry", store.sessions.error)

    def test_codex_desktop_registry_adds_idle_visible_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "state.sqlite"
            connection = sqlite3.connect(database)
            connection.execute(
                """CREATE TABLE threads (
                    id TEXT, name TEXT, cwd TEXT, recency_at INTEGER,
                    recency_at_ms INTEGER, archived INTEGER, source TEXT, preview TEXT
                )"""
            )
            connection.executemany(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("active", "Active task", "/tmp/active", 20, 20000, 0, "vscode", "visible"),
                    ("idle", "Idle task", "/tmp/idle", 10, 10000, 0, "vscode", "visible"),
                    ("hidden", "Hidden", "/tmp/hidden", 30, 30000, 0, "exec", "visible"),
                    ("archived", "Archived", "/tmp/archived", 40, 40000, 1, "vscode", "visible"),
                ],
            )
            connection.commit()
            connection.close()
            sessions = [{
                "id": "active", "provider": "codex", "state": "active",
                "source": "desktopApp", "sessionName": "Runtime title",
            }]
            with (
                patch.dict(os.environ, {"AGENT_TOUCHBAR_CODEX_STATE_DB": str(database)}),
                patch("agent_touchbar.core.run_codexbar", return_value=sessions),
            ):
                store = StateStore()
                store._refresh_sessions()
        self.assertEqual([item["id"] for item in store.sessions.value], ["active", "idle"])
        self.assertEqual(store.sessions.value[0]["state"], "active")
        self.assertEqual(store.sessions.value[0]["sessionName"], "Runtime title")
        self.assertEqual(store.sessions.value[1]["sessionName"], "Idle task")
        self.assertEqual(store.session_counts["codex"], {"active": 1, "idle": 1})

    def test_invalid_codex_desktop_registry_preserves_cached_tasks_and_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "state.sqlite"
            sqlite3.connect(database).close()
            store = StateStore()
            store.sessions.value = [{"id": "cached", "provider": "codex", "state": "idle"}]
            with (
                patch.dict(os.environ, {"AGENT_TOUCHBAR_CODEX_STATE_DB": str(database)}),
                patch("agent_touchbar.core.run_codexbar", return_value=[]),
            ):
                store._refresh_sessions()
        self.assertEqual(store.sessions.value[0]["id"], "cached")
        self.assertIn("registry", store.sessions.error)

    @patch("agent_touchbar.core.threading.Thread")
    def test_uninitialized_cache_always_refreshes(self, thread) -> None:
        store = StateStore(usage_ttl=60)
        with patch("agent_touchbar.core.time.monotonic", return_value=10):
            store._start_if_stale(store.usage, 60, store._refresh_usage, "usage")
        self.assertTrue(store.usage.refreshing)
        thread.assert_called_once()

    def test_usage_refresh_preserves_failed_provider_cache(self) -> None:
        store = StateStore()
        store.usage.value = [
            {"provider": "codex", "usage": {"primary": {"usedPercent": 10}}},
            {"provider": "claude", "usage": {"primary": {"usedPercent": 20}}},
        ]

        def response(*args, **kwargs):
            provider = args[2]
            if provider == "claude":
                raise OSError("temporary failure")
            return [{"provider": provider, "usage": {"primary": {"usedPercent": 30}}}]

        with patch("agent_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()

        providers = {item["provider"]: item for item in store.usage.value}
        self.assertEqual(providers["claude"]["usage"]["primary"]["usedPercent"], 20)
        self.assertEqual(providers["codex"]["usage"]["primary"]["usedPercent"], 30)
        self.assertIn("claude", store.usage.error)

    def test_usage_refresh_clears_successful_empty_provider(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "claude", "usage": {}}]
        with patch("agent_touchbar.core.run_codexbar", return_value=[]):
            store._refresh_usage()
        self.assertEqual(store.usage.value, [])

    def test_usage_refresh_preserves_cache_and_reports_non_list_payload(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "codex", "usage": {}}]

        def response(*args, **kwargs):
            provider = args[2]
            return {} if provider == "codex" else []

        with patch("agent_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()
        self.assertEqual(store.usage.value, [{"provider": "codex", "usage": {}}])
        self.assertIn("not a list", store.usage.error["codex"])

    def test_usage_refresh_rejects_non_object_usage(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "codex", "usage": {}}]

        def response(*args, **kwargs):
            provider = args[2]
            return [{"provider": provider, "usage": "unavailable"}]

        with patch("agent_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()
        self.assertEqual(store.usage.value, [{"provider": "codex", "usage": {}}])
        self.assertIn("invalid shape", store.usage.error["codex"])

    def test_usage_refresh_rejects_wrong_provider(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "codex", "usage": {"primary": {}}}]

        def response(*args, **kwargs):
            provider = args[2]
            if provider == "claude":
                return [{"provider": "codex", "usage": {}}]
            return [{"provider": provider, "usage": {}}]

        with patch("agent_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()
        self.assertIn("claude", store.usage.error)

    def test_usage_refresh_publishes_codex_before_optional_providers(self) -> None:
        store = StateStore()

        def response(*args, **kwargs):
            provider = args[2]
            if provider == "codex":
                return [{"provider": "codex", "usage": {}}]
            self.assertEqual(store.usage.value[0]["provider"], "codex")
            raise OSError("optional provider unavailable")

        with patch("agent_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()
        self.assertEqual(store.usage.value[0]["provider"], "codex")

    def test_usage_refresh_publishes_codex_error_before_optional_providers(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "codex", "usage": {}}]

        def response(*args, **kwargs):
            provider = args[2]
            if provider == "codex":
                raise OSError("codex unavailable")
            self.assertIn("codex", store.usage.error)
            return []

        with patch("agent_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()
        self.assertIn("codex", store.usage.error)

    def test_quota_windows_only_returns_reported_windows(self) -> None:
        provider = {
            "usage": {
                "primary": {"windowMinutes": 10080, "usedPercent": 25},
                "secondary": None,
            }
        }
        self.assertEqual(quota_windows(provider), [{"label": "7d", "windowMinutes": 10080, "usedPercent": 25}])

    def test_quota_windows_preserve_named_extra_rate_windows(self) -> None:
        provider = {"provider": "antigravity", "usage": {"extraRateWindows": [
            {"title": "Gemini 5-hour", "window": {"windowMinutes": 300, "usedPercent": 10}},
            {"title": "Claude/GPT weekly", "window": {"windowMinutes": 10080, "usedPercent": 20}},
            {"title": "Gemini 2.5 weekly", "window": {"windowMinutes": 10080, "usedPercent": 30}},
        ]}}
        self.assertEqual(
            [window["label"] for window in quota_windows(provider)],
            ["Gemini 5h", "Claude/GPT 7d", "Gemini 2.5 7d"],
        )

    def test_sessions_sort_by_state_then_recent_activity(self) -> None:
        sessions = [
            {"id": "idle", "state": "idle", "lastActivityAt": "2026-08-31T10:00:00Z"},
            {"id": "older", "state": "active", "lastActivityAt": "2026-08-31T09:00:00Z"},
            {"id": "newer", "state": "active", "lastActivityAt": "2026-08-31T11:00:00Z"},
        ]
        self.assertEqual([item["id"] for item in sorted(sessions, key=session_sort_key)], ["newer", "older", "idle"])

    def test_attention_sessions_sort_before_active_and_idle(self) -> None:
        sessions = [
            {"id": "idle", "state": "idle"},
            {"id": "active", "state": "active"},
            {"id": "attention", "state": "needs_input"},
        ]
        self.assertEqual(
            [item["id"] for item in sorted(sessions, key=session_sort_key)],
            ["attention", "active", "idle"],
        )

    def test_claude_session_without_desktop_title_is_not_exposed(self) -> None:
        store = StateStore()
        sessions = [{"id": "claude-id", "provider": "claude", "state": "active", "source": "desktopApp"}]
        with (
            patch("agent_touchbar.core.run_codexbar", return_value=sessions),
            patch.object(store, "_codex_desktop_sessions", return_value=[]),
            patch.object(store, "_claude_desktop_titles", return_value={}),
            patch.object(store, "_antigravity_desktop_sessions", return_value=[]),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, [])
        self.assertEqual(store.session_counts["claude"], {"active": 1, "idle": 0})

    def test_claude_codexbar_title_is_not_used_without_desktop_match(self) -> None:
        store = StateStore()
        sessions = [{
            "id": "claude-id",
            "provider": "claude",
            "state": "active",
            "source": "desktopApp",
            "sessionName": "CodexBar title",
        }]
        with (
            patch("agent_touchbar.core.run_codexbar", return_value=sessions),
            patch.object(store, "_codex_desktop_sessions", return_value=[]),
            patch.object(store, "_claude_desktop_titles", return_value={}),
            patch.object(store, "_antigravity_desktop_sessions", return_value=[]),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, [])

    def test_claude_desktop_title_replaces_project_metadata(self) -> None:
        store = StateStore()
        sessions = [{
            "id": "claude-id",
            "provider": "claude",
            "state": "active",
            "projectName": "worktree-name",
        }]
        with (
            patch("agent_touchbar.core.run_codexbar", return_value=sessions),
            patch.object(store, "_codex_desktop_sessions", return_value=[]),
            patch.object(store, "_claude_desktop_titles", return_value={"claude-id": "UI title"}),
            patch.object(store, "_antigravity_desktop_sessions", return_value=[]),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value[0]["sessionName"], "UI title")
        self.assertNotEqual(store.sessions.value[0]["sessionName"], "worktree-name")

    def test_claude_desktop_titles_only_returns_visible_unarchived_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_dir = root / "account" / "workspace"
            session_dir.mkdir(parents=True)
            (session_dir / "local_visible.json").write_text(json.dumps({
                "cliSessionId": "visible-id",
                "title": "Visible UI title",
                "lastActivityAt": 2,
                "isArchived": False,
            }))
            (session_dir / "local_archived.json").write_text(json.dumps({
                "cliSessionId": "archived-id",
                "title": "Archived title",
                "lastActivityAt": 3,
                "isArchived": True,
            }))
            with patch.dict(os.environ, {"AGENT_TOUCHBAR_CLAUDE_SESSION_DIR": directory}):
                titles = StateStore._claude_desktop_titles()
        self.assertEqual(titles, {"visible-id": "Visible UI title"})

    def test_antigravity_desktop_session_is_exposed_with_ui_title(self) -> None:
        store = StateStore()
        antigravity = [{
            "id": "antigravity:/conversation/one",
            "provider": "antigravity",
            "sessionName": "UI conversation",
            "state": "idle",
            "source": "desktopApp",
        }]
        with (
            patch("agent_touchbar.core.run_codexbar", return_value=[]),
            patch.object(store, "_codex_desktop_sessions", return_value=[]),
            patch.object(store, "_claude_desktop_titles", return_value={}),
            patch.object(store, "_antigravity_desktop_sessions", return_value=antigravity),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, antigravity)

    def test_compact_snapshot_does_not_expose_transcripts_or_accounts(self) -> None:
        snapshot = {
            "generatedAt": "now",
            "usage": [{"provider": "codex", "accountEmail": "private", "usage": {}}],
            "sessions": [{"id": "1", "provider": "codex", "transcriptPath": "/private"}],
            "sessionCounts": {"codex": {"active": 1, "idle": 0}},
        }
        result = compact_snapshot(snapshot)
        encoded = str(result)
        self.assertNotIn("private", encoded)
        self.assertNotIn("transcriptPath", encoded)
        self.assertEqual(result["providers"][0]["sessionCounts"], {"active": 1, "idle": 0})
        self.assertEqual(result["capabilities"], CAPABILITIES)
        self.assertEqual(result["capabilities"]["codex"]["tasks"]["source"], "codexDesktop")
        self.assertFalse(result["capabilities"]["claude"]["focusTask"]["supported"])

    def test_renderer_snapshot_orders_attention_quota_active_and_idle(self) -> None:
        snapshot = {
            "generatedAt": "now",
            "usage": [{
                "provider": "codex",
                "usage": {"primary": {"windowMinutes": 10080, "usedPercent": 25}},
            }],
            "sessions": [
                {"id": "idle", "provider": "codex", "sessionName": "Idle", "state": "idle"},
                {"id": "active", "provider": "codex", "sessionName": "Active", "state": "active"},
                {"id": "input", "provider": "codex", "sessionName": "Input", "state": "needs_input"},
            ],
            "sessionCounts": {"codex": {"active": 1, "idle": 1}},
        }
        result = renderer_snapshot(snapshot)
        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual(
            [item["id"] for item in result["items"]],
            [
                "task:input",
                "quota:codex",
                "quota:claude",
                "quota:antigravity",
                "task:active",
                "task:idle",
            ],
        )
        self.assertEqual(result["items"][1]["label"], "7d 75%")
        self.assertEqual(
            result["items"][4]["action"],
            {"type": "focusTask", "taskId": "active"},
        )

    def test_renderer_drops_sessions_without_ui_name_without_leaking_metadata(self) -> None:
        result = renderer_snapshot({
            "generatedAt": "now",
            "usage": [],
            "sessions": [{
                "id": "task-id",
                "provider": "codex",
                "projectName": "Project",
                "state": "idle",
                "transcriptPath": "/private/transcript",
            }],
            "sessionCounts": {},
        })
        encoded = json.dumps(result)
        self.assertEqual(len(result["items"]), 3)
        self.assertNotIn("transcript", encoded)
        self.assertNotIn("private", encoded)

    def test_renderer_does_not_render_session_counts_in_quota(self) -> None:
        result = renderer_snapshot({
            "generatedAt": "now",
            "usage": [],
            "sessions": [],
            "sessionCounts": {"claude": {"active": 2, "idle": 3}},
        })
        claude = next(item for item in result["items"] if item["id"] == "quota:claude")
        self.assertEqual(claude["label"], "—")
        self.assertEqual(claude["sessionCounts"], {"active": 2, "idle": 3})

    def test_renderer_renders_named_provider_sessions_and_compact_antigravity_quota(self) -> None:
        result = renderer_snapshot({
            "generatedAt": "now",
            "usage": [{
                "provider": "antigravity",
                "usage": {"extraRateWindows": [
                    {"title": "Gemini 5-hour", "window": {"windowMinutes": 300, "usedPercent": 10}},
                    {"title": "Claude/GPT weekly", "window": {"windowMinutes": 10080, "usedPercent": 20}},
                ]},
            }],
            "sessions": [
                {"id": "codex", "provider": "codex", "sessionName": "Codex", "state": "active"},
                {"id": "claude", "provider": "claude", "sessionName": "Claude", "state": "active"},
            ],
            "sessionCounts": {},
        })
        self.assertIn("task:codex", [item["id"] for item in result["items"]])
        self.assertIn("task:claude", [item["id"] for item in result["items"]])
        antigravity = next(item for item in result["items"] if item["id"] == "quota:antigravity")
        self.assertEqual(antigravity["label"], "5h 90%")


if __name__ == "__main__":
    unittest.main()
