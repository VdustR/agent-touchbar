from __future__ import annotations

import unittest
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codexbar_touchbar.btt import definitions, install_widgets, session_action, session_script, widget_uuid


class BetterTouchToolTests(unittest.TestCase):
    def test_definitions_have_stable_unique_ids_and_widget_native_actions(self) -> None:
        widgets = definitions()
        identifiers = [item["BTTUUID"] for item in widgets]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(identifiers[0], widget_uuid("Codex usage"))
        for item in widgets:
            self.assertEqual(item["BTTPredefinedActionType"], 137)
            self.assertIn("curl", item["BTTTerminalCommand"])
            self.assertNotIn("BTTActionsToExecute", item)
            self.assertNotIn("BTTActionCategoryTouchRelease", item)

    def test_layout_places_quota_before_sessions(self) -> None:
        widgets = definitions()
        quota_orders = [item["BTTOrder"] for item in widgets[:3]]
        session_orders = [item["BTTOrder"] for item in widgets[3:]]
        self.assertLess(max(quota_orders), min(session_orders))

    def test_no_attention_widget_is_created_without_a_supported_state(self) -> None:
        names = [item["BTTWidgetName"] for item in definitions()]
        self.assertNotIn("Attention session", names)

    def test_session_action_uses_identity_persisted_by_render(self) -> None:
        render = session_script(1)
        action = session_action(1)
        self.assertIn("session-2.json", render)
        self.assertIn("session-2.json", action)
        self.assertIn("os.replace", render)
        self.assertNotIn("/api/btt", action)

    @patch("codexbar_touchbar.btt.data_dir", return_value=Path("/tmp/Application Support/Test"))
    def test_session_render_path_with_spaces_is_valid_python(self, _data_dir) -> None:
        script = session_script(0)
        result = subprocess.run(
            ["/bin/bash", "-n", "-c", script], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('action_path="/tmp/Application Support/Test/actions/session-1.json"', script)

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

    def test_install_replaces_managed_triggers_to_avoid_merged_actions(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                run_cli.return_value.stdout = '{"BTTUUID":"existing"}'
                install_widgets(1)
            calls = [call.args[0] for call in run_cli.call_args_list if call.args]
            self.assertEqual(calls.count("add_new_trigger"), 4)
            self.assertGreaterEqual(calls.count("delete_trigger"), 4)
            self.assertNotIn("update_trigger", calls)


if __name__ == "__main__":
    unittest.main()
