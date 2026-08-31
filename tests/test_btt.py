from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import call, patch

from codexbar_touchbar.btt import button_updates, definitions, install_widgets, previous_slot_count, session_action, uninstall_widgets, update_buttons, widget_uuid


class BetterTouchToolTests(unittest.TestCase):
    @patch("codexbar_touchbar.btt.bttcli_path", return_value="/bin/bttcli")
    @patch("codexbar_touchbar.btt.subprocess.run")
    def test_run_cli_has_a_bounded_timeout(self, run, _path) -> None:
        from codexbar_touchbar.btt import BTT_CLI_TIMEOUT_SECONDS, run_cli

        run_cli("get_trigger", "uuid=test", check=False)
        run.assert_called_once_with(
            ["/bin/bttcli", "get_trigger", "uuid=test"],
            check=False,
            capture_output=True,
            text=True,
            timeout=BTT_CLI_TIMEOUT_SECONDS,
        )

    def test_definitions_have_stable_unique_ids_and_standard_tap_actions(self) -> None:
        widgets = definitions()
        identifiers = [item["BTTUUID"] for item in widgets]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(identifiers[0], widget_uuid("Codex usage"))
        for item in widgets:
            self.assertNotIn("BTTPredefinedActionType", item)
            self.assertNotIn("BTTTerminalCommand", item)
            self.assertEqual(len(item["BTTActionsToExecute"]), 1)
            action = item["BTTActionsToExecute"][0]
            self.assertEqual(action["BTTActionCategory"], 0)
            self.assertEqual(action["BTTPredefinedActionType"], 206)
            self.assertIn("curl", action["BTTShellTaskActionScript"])
            self.assertEqual(
                action["BTTShellTaskActionConfig"], "/bin/bash:::-c:::-:::"
            )
            config = item["BTTTriggerConfig"]
            self.assertEqual(config["BTTTouchBarButtonFontSize"], 11)
            self.assertEqual(config["BTTTouchBarButtonUseFixedWidth"], 1)
            self.assertEqual(config["BTTTouchBarButtonUseFixedHeight"], 1)
            self.assertNotIn("BTTActionCategoryTouchRelease", item)

    def test_attention_sessions_sort_before_quota_and_active_after(self) -> None:
        snapshot = {"usage": [], "sessions": [
            {"id": "attention", "provider": "codex", "source": "desktopApp", "state": "needs_input"},
            {"id": "active", "provider": "codex", "source": "desktopApp", "state": "active"},
        ]}
        updates = dict(button_updates(snapshot, 2))
        self.assertLess(updates[widget_uuid("Agent session 1")]["BTTOrder"], 10)
        self.assertGreater(updates[widget_uuid("Agent session 2")]["BTTOrder"], 12)

    def test_all_supported_attention_slots_precede_quota_orders(self) -> None:
        snapshot = {"usage": [], "sessions": [
            {
                "id": f"attention-{index}",
                "provider": "codex",
                "source": "desktopApp",
                "state": "needs_input",
            }
            for index in range(12)
        ]}
        updates = dict(button_updates(snapshot, 12))
        orders = [
            updates[widget_uuid(f"Agent session {index + 1}")]["BTTOrder"]
            for index in range(12)
        ]
        self.assertLess(max(orders), 10)

    def test_native_button_updates_bind_visible_session_identity(self) -> None:
        snapshot = {
            "usage": [{"provider": "codex", "usage": {"primary": {"windowMinutes": 10080, "usedPercent": 25}}}],
            "sessions": [{"id": "session-1", "provider": "codex", "state": "active", "source": "desktopApp", "sessionName": "Current"}],
        }
        updates = dict(button_updates(snapshot, 2))
        quota = updates[widget_uuid("Codex usage")]
        session = updates[widget_uuid("Agent session 1")]
        self.assertEqual(quota["BTTTouchBarButtonName"], "7d 75%")
        self.assertNotIn("BTTTerminalCommand", session)
        self.assertNotIn(widget_uuid("Agent session 2"), updates)

    def test_quota_button_appends_only_observed_nonzero_session_states(self) -> None:
        snapshot = {
            "usage": [{"provider": "claude", "usage": {"primary": {"windowMinutes": 300, "usedPercent": 20}}}],
            "sessionCounts": {"claude": {"active": 1, "idle": 2}},
            "sessions": [],
        }
        updates = dict(button_updates(snapshot, 1))
        self.assertEqual(
            updates[widget_uuid("Claude usage")]["BTTTouchBarButtonName"],
            "5h 80% · 1 active · 2 idle",
        )

    def test_missing_quota_uses_neutral_color(self) -> None:
        updates = dict(button_updates({"usage": [], "sessions": []}, 1))
        self.assertEqual(
            updates[widget_uuid("Codex usage")]["BTTTriggerConfig"]["BTTTouchBarButtonColor"],
            "55, 60, 68, 255",
        )

    @patch("codexbar_touchbar.btt.run_cli")
    def test_unchanged_native_buttons_are_not_reconfigured(self, run_cli) -> None:
        run_cli.return_value = subprocess.CompletedProcess([], 0, "{}", "")
        snapshot = {"usage": [], "sessions": []}
        previous = update_buttons(snapshot, 2)
        first_count = run_cli.call_count
        update_buttons(snapshot, 2, previous)
        self.assertEqual(run_cli.call_count, first_count)

    @patch("codexbar_touchbar.btt.slot_action_path", return_value=Path("/missing/session-1.json"))
    @patch("codexbar_touchbar.btt.run_cli")
    def test_initial_refresh_removes_stale_empty_session_trigger(self, run_cli, _path) -> None:
        run_cli.return_value = subprocess.CompletedProcess([], 0, '{"BTTUUID":"existing"}', "")
        update_buttons({"usage": [], "sessions": []}, 1, None)
        run_cli.assert_any_call(
            "delete_trigger", f"uuid={widget_uuid('Agent session 1')}"
        )

    @patch("codexbar_touchbar.btt.run_cli")
    def test_failed_stale_trigger_lookup_is_retried_by_the_update_loop(self, run_cli) -> None:
        run_cli.return_value = subprocess.CompletedProcess(
            ["bttcli", "get_trigger"], 1, "", "socket unavailable"
        )
        with self.assertRaises(subprocess.CalledProcessError):
            update_buttons({"usage": [], "sessions": []}, 1, None)

    @patch("codexbar_touchbar.btt.slot_action_path", return_value=Path("/missing/session-1.json"))
    @patch("codexbar_touchbar.btt.run_cli")
    def test_dynamic_session_trigger_is_created_and_removed(self, run_cli, _path) -> None:
        run_cli.return_value = subprocess.CompletedProcess([], 0, "{}", "")
        active = {"usage": [], "sessions": [
            {"id": "one", "provider": "codex", "state": "active", "source": "desktopApp"}
        ]}
        previous = update_buttons(active, 2, {})
        added = [call for call in run_cli.call_args_list if call.args[0] == "add_new_trigger"]
        self.assertEqual(len(added), 1)
        added_payload = json.loads(added[0].args[1].removeprefix("json="))
        self.assertEqual(added_payload["BTTTouchBarButtonName"], "● session")
        self.assertIn(
            '"id":"one"',
            added_payload["BTTTerminalCommand"],
        )
        self.assertEqual(added_payload["BTTPredefinedActionType"], 137)
        self.assertIn(
            '"id":"one"',
            added_payload["BTTActionsToExecute"][0]["BTTShellTaskActionScript"],
        )
        run_cli.reset_mock()
        run_cli.return_value = subprocess.CompletedProcess([], 0, '{"BTTUUID":"existing"}', "")
        update_buttons({"usage": [], "sessions": []}, 2, previous)
        deleted = [call.args[1] for call in run_cli.call_args_list if call.args[0] == "delete_trigger"]
        self.assertEqual(deleted, [f"uuid={widget_uuid('Agent session 1')}"])

    @patch("codexbar_touchbar.btt.run_cli")
    def test_session_identity_change_fully_replaces_trigger(self, run_cli) -> None:
        run_cli.return_value = subprocess.CompletedProcess([], 0, "{}", "")
        previous_snapshot = {"usage": [], "sessions": [
            {"id": "old", "provider": "codex", "state": "active", "source": "desktopApp"}
        ]}
        current_snapshot = {"usage": [], "sessions": [
            {"id": "new", "provider": "codex", "state": "active", "source": "desktopApp"}
        ]}
        previous = update_buttons(previous_snapshot, 1, {})
        run_cli.reset_mock()
        run_cli.return_value = subprocess.CompletedProcess([], 0, '{"BTTUUID":"existing"}', "")
        update_buttons(current_snapshot, 1, previous)
        commands = [call.args[0] for call in run_cli.call_args_list]
        self.assertEqual(commands, ["get_trigger", "delete_trigger", "add_new_trigger"])
        added = json.loads(run_cli.call_args_list[-1].args[1].removeprefix("json="))
        self.assertIn('"id":"new"', added["BTTTerminalCommand"])

    @patch("codexbar_touchbar.btt.run_cli")
    def test_changed_session_trigger_is_fully_replaced(self, run_cli) -> None:
        run_cli.return_value = subprocess.CompletedProcess([], 0, '{"BTTUUID":"existing"}', "")
        snapshot = {"usage": [], "sessions": [
            {"id": "new", "provider": "codex", "state": "active", "source": "desktopApp"}
        ]}
        update_buttons(snapshot, 1, {widget_uuid("Agent session 1"): {"old": True}})
        commands = [
            call.args[0]
            for call in run_cli.call_args_list
            if call.args[0] != "update_trigger"
        ]
        self.assertEqual(commands, ["get_trigger", "delete_trigger", "add_new_trigger"])

    @patch("codexbar_touchbar.btt.run_cli")
    def test_failed_session_lookup_retains_previous_tap_target(self, run_cli) -> None:
        run_cli.return_value = subprocess.CompletedProcess(
            ["bttcli", "get_trigger"], 1, "", "socket unavailable"
        )
        snapshot = {"usage": [], "sessions": [
            {"id": "new", "provider": "codex", "state": "active", "source": "desktopApp"}
        ]}
        with self.assertRaises(subprocess.CalledProcessError):
            update_buttons(snapshot, 1, {widget_uuid("Agent session 1"): {"old": True}})
        session_calls = [
            item
            for item in run_cli.call_args_list
            if item.args[0] in {"get_trigger", "delete_trigger", "add_new_trigger"}
        ]
        self.assertEqual(
            session_calls,
            [call("get_trigger", f"uuid={widget_uuid('Agent session 1')}", check=False)],
        )

    def test_cli_sessions_are_not_rendered_as_desktop_buttons(self) -> None:
        snapshot = {
            "usage": [],
            "sessions": [
                {"id": "cli", "provider": "codex", "state": "active", "source": "cli", "projectName": "T"},
                {"id": "desktop", "provider": "codex", "state": "idle", "source": "desktopApp", "projectName": "Project"},
            ],
        }
        updates = dict(button_updates(snapshot, 1))
        self.assertEqual(
            updates[widget_uuid("Agent session 1")]["BTTTouchBarButtonName"],
            "○ ⌁ Project",
        )

    def test_touch_bar_sessions_only_include_codex_desktop_tasks(self) -> None:
        snapshot = {
            "usage": [],
            "sessions": [
                {"id": "codex-active", "provider": "codex", "state": "active", "source": "desktopApp", "sessionName": "Active"},
                {"id": "antigravity", "provider": "antigravity", "state": "available", "source": "appPresence", "sessionName": "Antigravity"},
                {"id": "claude", "provider": "claude", "state": "idle", "source": "desktopApp", "sessionName": "Claude"},
                {"id": "codex-idle", "provider": "codex", "state": "idle", "source": "desktopApp", "sessionName": "Idle"},
            ],
        }
        updates = dict(button_updates(snapshot, 4))
        self.assertEqual(updates[widget_uuid("Agent session 1")]["BTTTouchBarButtonName"], "● Active")
        self.assertEqual(updates[widget_uuid("Agent session 2")]["BTTTouchBarButtonName"], "○ Idle")
        self.assertNotIn(widget_uuid("Agent session 3"), updates)

    def test_sessions_without_supported_states_are_not_rendered(self) -> None:
        snapshot = {
            "usage": [],
            "sessions": [
                {"id": "claude", "provider": "claude", "source": "desktopApp"},
                {"id": "antigravity", "provider": "antigravity", "source": "desktopApp"},
            ],
        }
        updates = dict(button_updates(snapshot, 1))
        self.assertNotIn(widget_uuid("Agent session 1"), updates)

    def test_unsupported_codex_session_state_is_not_rendered_as_idle(self) -> None:
        snapshot = {
            "usage": [],
            "sessions": [
                {"id": "ended", "provider": "codex", "source": "desktopApp", "state": "ended"},
            ],
        }
        updates = dict(button_updates(snapshot, 1))
        self.assertNotIn(widget_uuid("Agent session 1"), updates)

    def test_non_string_session_labels_fall_back_safely(self) -> None:
        snapshot = {
            "usage": [],
            "sessions": [
                {
                    "id": "valid",
                    "provider": "codex",
                    "source": "desktopApp",
                    "state": "active",
                    "sessionName": 1,
                    "projectName": [],
                }
            ],
        }
        session = dict(button_updates(snapshot, 1))[widget_uuid("Agent session 1")]
        self.assertEqual(session["BTTTouchBarButtonName"], "● session")

    def test_no_attention_widget_is_created_without_a_supported_state(self) -> None:
        names = [item["BTTTouchBarButtonName"] for item in definitions()]
        self.assertNotIn("Attention session", names)

    def test_session_action_binds_the_task_identity(self) -> None:
        action = session_action("session-one")
        self.assertIn('"id":"session-one"', action)
        self.assertNotIn("/api/btt", action)

    def test_session_action_shell_quotes_opaque_id(self) -> None:
        script = session_action("thread'$(touch /tmp/nope)")
        result = subprocess.run(
            ["/bin/bash", "-n", "-c", script], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'\"'\"'", script)

    def test_reducing_slot_count_removes_excess_widgets(self) -> None:
        with TemporaryDirectory() as temporary:
            state = Path(temporary) / "session-slots.json"
            state.write_text('{"sessionSlots": 5}\n')
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                run_cli.return_value.returncode = 0
                run_cli.return_value.stdout = '{"BTTUUID":"existing"}'
                install_widgets(2)
            deleted = {
                call.args[1]
                for call in run_cli.call_args_list
                if call.args and call.args[0] == "delete_trigger"
            }
            self.assertIn(f"uuid={widget_uuid('Agent session 3')}", deleted)
            self.assertIn(f"uuid={widget_uuid('Agent session 5')}", deleted)
            self.assertIn(f"uuid={widget_uuid('Agent session 12')}", deleted)

    def test_install_replaces_managed_triggers_to_avoid_merged_actions(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                run_cli.return_value.returncode = 0
                run_cli.return_value.stdout = '{"BTTUUID":"existing"}'
                install_widgets(1)
            calls = [call.args[0] for call in run_cli.call_args_list if call.args]
            self.assertEqual(calls.count("add_new_trigger"), 3)
            self.assertGreaterEqual(calls.count("delete_trigger"), 4)
            self.assertNotIn("update_trigger", calls)

    def test_uninstall_fails_when_trigger_lookup_fails(self) -> None:
        with patch("codexbar_touchbar.btt.run_cli") as run_cli:
            run_cli.return_value.returncode = 1
            run_cli.return_value.args = ["bttcli", "get_trigger"]
            run_cli.return_value.stdout = ""
            run_cli.return_value.stderr = "socket unavailable"
            with self.assertRaises(subprocess.CalledProcessError):
                uninstall_widgets(1)

    def test_uninstall_checks_all_twelve_session_slots(self) -> None:
        with patch("codexbar_touchbar.btt.run_cli") as run_cli:
            run_cli.return_value.returncode = 0
            run_cli.return_value.stdout = "{}"
            uninstall_widgets(1)
        looked_up = {call.args[1] for call in run_cli.call_args_list if call.args[0] == "get_trigger"}
        self.assertIn(f"uuid={widget_uuid('Agent session 12')}", looked_up)
        self.assertIn(f"uuid={widget_uuid('Attention session')}", looked_up)

    def test_install_fails_when_legacy_trigger_cannot_be_deleted(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                def result(command, *args, **kwargs):
                    if command == "delete_trigger" and "E4F85058" in args[0]:
                        raise subprocess.CalledProcessError(1, [command, *args])
                    return subprocess.CompletedProcess([command, *args], 0, "{}", "")

                run_cli.side_effect = result
                with self.assertRaises(subprocess.CalledProcessError):
                    install_widgets(1)

    def test_missing_slot_state_defaults_to_managing_all_slots(self) -> None:
        with patch("codexbar_touchbar.btt.slot_state_path", return_value=Path("/missing")):
            self.assertEqual(previous_slot_count(), 12)

    def test_non_object_slot_state_defaults_to_managing_all_slots(self) -> None:
        with TemporaryDirectory() as temporary:
            state = Path(temporary) / "session-slots.json"
            state.write_text("[]")
            with patch("codexbar_touchbar.btt.slot_state_path", return_value=state):
                self.assertEqual(previous_slot_count(), 12)

    def test_boolean_slot_state_defaults_to_managing_all_slots(self) -> None:
        with TemporaryDirectory() as temporary:
            state = Path(temporary) / "session-slots.json"
            state.write_text('{"sessionSlots": true}')
            with patch("codexbar_touchbar.btt.slot_state_path", return_value=state):
                self.assertEqual(previous_slot_count(), 12)

    def test_install_fails_when_excess_slot_cannot_be_deleted(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                def response(*args, **kwargs):
                    if args == ("delete_trigger", f"uuid={widget_uuid('Agent session 5')}"):
                        raise subprocess.CalledProcessError(1, ["bttcli", *args])
                    return subprocess.CompletedProcess([], 0, '{"BTTUUID":"existing"}', "")

                run_cli.side_effect = response
                with self.assertRaises(subprocess.CalledProcessError):
                    install_widgets(4)

    def test_install_retries_after_excess_slot_lookup_failure(self) -> None:
        with TemporaryDirectory() as temporary:
            with (
                patch("codexbar_touchbar.btt.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.btt.run_cli") as run_cli,
            ):
                def response(*args, **kwargs):
                    if args == (
                        "get_trigger",
                        f"uuid={widget_uuid('Agent session 5')}",
                    ):
                        return subprocess.CompletedProcess(
                            ["bttcli", *args], 1, "", "socket unavailable"
                        )
                    return subprocess.CompletedProcess(["bttcli", *args], 0, "{}", "")

                run_cli.side_effect = response
                with self.assertRaises(subprocess.CalledProcessError):
                    install_widgets(4)


if __name__ == "__main__":
    unittest.main()
