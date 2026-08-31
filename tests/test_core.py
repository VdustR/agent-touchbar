from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codexbar_touchbar.core import StateStore, compact_snapshot, find_executable, quota_windows, session_sort_key


class CoreTests(unittest.TestCase):
    def test_find_executable_preserves_stable_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "versioned"
            link = root / "stable"
            target.write_text("")
            link.symlink_to(target)
            with patch.dict(os.environ, {"CODEXBAR_TOUCHBAR_TOOL": str(link)}):
                self.assertEqual(find_executable("tool", ()), str(link))

    def test_session_refresh_interval_prioritizes_interactive_updates(self) -> None:
        self.assertLessEqual(StateStore().sessions_ttl, 0.75)

    @patch("codexbar_touchbar.core.subprocess.run")
    def test_codex_session_focus_uses_thread_deep_link(self, run) -> None:
        store = StateStore()
        store.sessions.value = [
            {"id": "thread/id", "provider": "codex", "source": "desktopApp"}
        ]
        store.focus_session("thread/id")
        run.assert_called_once_with(
            ["/usr/bin/open", "codex://threads/thread%2Fid"], check=True, timeout=3
        )

    def test_session_refresh_keeps_only_codex_sessions(self) -> None:
        store = StateStore()
        sessions = [
            {"id": "codex", "provider": "codex", "state": "active", "source": "desktopApp"},
            {"id": "claude", "provider": "claude"},
            {"id": "antigravity", "provider": "antigravity"},
        ]
        with patch("codexbar_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_app_is_running", return_value=False):
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
        with patch("codexbar_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_app_is_running", return_value=False):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, [{"id": "valid", "provider": "codex", "state": "active", "source": "desktopApp"}])

    def test_session_refresh_rejects_non_list_payload(self) -> None:
        store = StateStore()
        store.sessions.value = [{"id": "cached", "provider": "codex"}]
        with patch("codexbar_touchbar.core.run_codexbar", return_value={}):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, [{"id": "cached", "provider": "codex"}])
        self.assertIn("not a list", store.sessions.error)
        self.assertFalse(store.sessions.refreshing)

    def test_session_refresh_counts_supported_states_for_each_provider(self) -> None:
        store = StateStore()
        sessions = [
            {"id": "1", "provider": "claude", "state": "active"},
            {"id": "2", "provider": "claude", "state": "idle"},
            {"id": "3", "provider": "claude", "state": "unknown"},
        ]
        with patch("codexbar_touchbar.core.run_codexbar", return_value=sessions):
            store._refresh_sessions()
        self.assertEqual(store.session_counts["claude"], {"active": 1, "idle": 1})

    def test_session_refresh_ignores_non_string_states(self) -> None:
        store = StateStore()
        sessions = [
            {"id": "invalid", "provider": "codex", "state": [], "source": "desktopApp"},
            {"id": "valid", "provider": "codex", "state": "active", "source": "desktopApp"},
        ]
        with patch("codexbar_touchbar.core.run_codexbar", return_value=sessions), patch.object(StateStore, "_app_is_running", return_value=False):
            store._refresh_sessions()
        self.assertEqual(store.session_counts["codex"], {"active": 1, "idle": 0})
        self.assertFalse(store.sessions.refreshing)
        self.assertEqual([item["id"] for item in store.sessions.value], ["valid"])

    @patch("codexbar_touchbar.core.threading.Thread")
    def test_uninitialized_cache_always_refreshes(self, thread) -> None:
        store = StateStore(usage_ttl=60)
        with patch("codexbar_touchbar.core.time.monotonic", return_value=10):
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

        with patch("codexbar_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()

        providers = {item["provider"]: item for item in store.usage.value}
        self.assertEqual(providers["claude"]["usage"]["primary"]["usedPercent"], 20)
        self.assertEqual(providers["codex"]["usage"]["primary"]["usedPercent"], 30)
        self.assertIn("claude", store.usage.error)

    def test_usage_refresh_clears_successful_empty_provider(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "claude", "usage": {}}]
        with patch("codexbar_touchbar.core.run_codexbar", return_value=[]):
            store._refresh_usage()
        self.assertEqual(store.usage.value, [])

    def test_usage_refresh_preserves_cache_and_reports_non_list_payload(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "codex", "usage": {}}]

        def response(*args, **kwargs):
            provider = args[2]
            return {} if provider == "codex" else []

        with patch("codexbar_touchbar.core.run_codexbar", side_effect=response):
            store._refresh_usage()
        self.assertEqual(store.usage.value, [{"provider": "codex", "usage": {}}])
        self.assertIn("not a list", store.usage.error["codex"])

    def test_usage_refresh_rejects_non_object_usage(self) -> None:
        store = StateStore()
        store.usage.value = [{"provider": "codex", "usage": {}}]

        def response(*args, **kwargs):
            provider = args[2]
            return [{"provider": provider, "usage": "unavailable"}]

        with patch("codexbar_touchbar.core.run_codexbar", side_effect=response):
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

        with patch("codexbar_touchbar.core.run_codexbar", side_effect=response):
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

        with patch("codexbar_touchbar.core.run_codexbar", side_effect=response):
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

        with patch("codexbar_touchbar.core.run_codexbar", side_effect=response):
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

    def test_claude_session_title_is_enriched_from_desktop_metadata(self) -> None:
        store = StateStore()
        sessions = [{"id": "claude-id", "provider": "claude", "state": "active", "source": "desktopApp"}]
        metadata = {"claude-id": {"title": "Visible Claude title", "sessionId": "local-id"}}
        with (
            patch("codexbar_touchbar.core.run_codexbar", return_value=sessions),
            patch.object(store, "_claude_titles", return_value=metadata),
            patch.object(store, "_app_is_running", return_value=False),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value[0]["sessionName"], "Visible Claude title")
        self.assertEqual(store.sessions.value[0]["appSessionId"], "local-id")

    def test_antigravity_presence_is_explicitly_app_level(self) -> None:
        store = StateStore()
        with (
            patch("codexbar_touchbar.core.run_codexbar", return_value=[]),
            patch.object(store, "_claude_titles", return_value={}),
            patch.object(store, "_app_is_running", return_value=True),
        ):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value[0]["source"], "appPresence")
        self.assertEqual(store.sessions.value[0]["state"], "available")

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


if __name__ == "__main__":
    unittest.main()
