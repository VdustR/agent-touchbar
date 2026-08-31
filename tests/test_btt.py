from __future__ import annotations

import unittest

from codexbar_touchbar.btt import definitions, widget_uuid


class BetterTouchToolTests(unittest.TestCase):
    def test_definitions_have_stable_unique_ids_and_release_actions(self) -> None:
        widgets = definitions()
        identifiers = [item["BTTUUID"] for item in widgets]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(identifiers[0], widget_uuid("Codex usage"))
        for item in widgets:
            self.assertIn("BTTActionCategoryTouchRelease", item)
            self.assertNotIn("BTTActionsToExecute", item)

    def test_layout_places_quota_before_sessions(self) -> None:
        widgets = definitions()
        quota_orders = [item["BTTOrder"] for item in widgets[:3]]
        session_orders = [item["BTTOrder"] for item in widgets[3:]]
        self.assertLess(max(quota_orders), min(session_orders))

    def test_no_attention_widget_is_created_without_a_supported_state(self) -> None:
        names = [item["BTTWidgetName"] for item in definitions()]
        self.assertNotIn("Attention session", names)


if __name__ == "__main__":
    unittest.main()
