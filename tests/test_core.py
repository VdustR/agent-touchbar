from __future__ import annotations

import unittest
from unittest.mock import patch

from codexbar_touchbar.core import StateStore, compact_snapshot, quota_windows, session_sort_key


class CoreTests(unittest.TestCase):
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
            {"id": "codex", "provider": "codex"},
            {"id": "claude", "provider": "claude"},
            {"id": "antigravity", "provider": "antigravity"},
        ]
        with patch("codexbar_touchbar.core.run_codexbar", return_value=sessions):
            store._refresh_sessions()
        self.assertEqual(store.sessions.value, [{"id": "codex", "provider": "codex"}])

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
