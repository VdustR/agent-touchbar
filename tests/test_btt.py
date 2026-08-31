from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codexbar_touchbar.btt import definitions, install_widgets, widget_uuid


class BetterTouchToolTests(unittest.TestCase):
    def test_definitions_have_stable_unique_ids_and_primary_actions(self) -> None:
        widgets = definitions()
        identifiers = [item["BTTUUID"] for item in widgets]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(identifiers[0], widget_uuid("Codex usage"))
        for item in widgets:
            self.assertIn("BTTActionsToExecute", item)
            self.assertNotIn("BTTActionCategoryTouchRelease", item)

    def test_layout_places_quota_before_sessions(self) -> None:
        widgets = definitions()
        quota_orders = [item["BTTOrder"] for item in widgets[:3]]
        session_orders = [item["BTTOrder"] for item in widgets[3:]]
        self.assertLess(max(quota_orders), min(session_orders))

    def test_no_attention_widget_is_created_without_a_supported_state(self) -> None:
        names = [item["BTTWidgetName"] for item in definitions()]
        self.assertNotIn("Attention session", names)

    def test_reducing_slot_count_removes_excess_widgets(self) -> None:
        with TemporaryDirectory() as temporary:
            state = Path(temporary) / "session-slots.json"
            state.write_text('{"sessionSlots": 5}\n')
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                run_cli.return_value.stdout = "{}"
                install_widgets(2)
            deleted = {
                call.args[1]
                for call in run_cli.call_args_list
                if call.args and call.args[0] == "delete_trigger"
            }
            self.assertIn(f"uuid={widget_uuid('Agent session 3')}", deleted)
            self.assertIn(f"uuid={widget_uuid('Agent session 5')}", deleted)


if __name__ == "__main__":
    unittest.main()
