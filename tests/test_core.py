from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codexbar_touchbar.core import StateStore, compact_snapshot, quota_windows, session_sort_key


class CoreTests(unittest.TestCase):
    def test_session_refresh_interval_prioritizes_interactive_updates(self) -> None:
        self.assertLessEqual(StateStore().sessions_ttl, 0.75)

    @patch("codexbar_touchbar.core.subprocess.run")
    def test_desktop_session_focus_uses_cached_provider_without_rescan(self, run) -> None:
        store = StateStore()
        store.sessions.value = [
            {"id": "claude-session", "provider": "claude", "source": "desktopApp"}
        ]
        store.focus_session("claude-session")
        run.assert_called_once_with(
            ["/usr/bin/open", "-b", "com.anthropic.claudefordesktop"],
            check=True,
            timeout=3,
        )

    def test_claude_title_enrichment_reads_only_matching_title_metadata(self) -> None:
        with TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "session.jsonl"
            records = [
                {"type": "user", "sessionId": "wanted", "message": {"content": "private"}},
                {"type": "ai-title", "sessionId": "other", "aiTitle": "Wrong"},
                {"type": "ai-title", "sessionId": "wanted", "aiTitle": "Generated"},
                {"type": "custom-title", "sessionId": "wanted", "customTitle": "Chosen"},
            ]
            transcript.write_text("\n".join(json.dumps(item) for item in records))
            store = StateStore()
            session = {"id": "wanted", "provider": "claude", "transcriptPath": str(transcript)}
            self.assertEqual(store._claude_title(session), "Chosen")

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
        }
        result = compact_snapshot(snapshot)
        encoded = str(result)
        self.assertNotIn("private", encoded)
        self.assertNotIn("transcriptPath", encoded)


if __name__ == "__main__":
    unittest.main()
