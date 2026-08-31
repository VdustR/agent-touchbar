from __future__ import annotations

import unittest

from codexbar_touchbar.core import compact_snapshot, quota_windows, session_sort_key


class CoreTests(unittest.TestCase):
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

