from __future__ import annotations

import plistlib
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codexbar_touchbar.cli import doctor, install_service, launch_agent_loaded, main, stop_service, uninstall_service


class CliTests(unittest.TestCase):
    @patch("codexbar_touchbar.cli.subprocess.run")
    @patch("codexbar_touchbar.cli.os.getuid", return_value=1234)
    def test_launch_agent_loaded_queries_the_user_domain(self, _getuid, run) -> None:
        run.return_value.returncode = 0
        self.assertTrue(launch_agent_loaded())
        self.assertEqual(
            run.call_args.args[0],
            ["/bin/launchctl", "print", "gui/1234/com.vdustr.codexbar-touchbar"],
        )

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_launch_agent_loaded_rejects_an_unloaded_service(self, run) -> None:
        run.return_value.returncode = 113
        self.assertFalse(launch_agent_loaded())

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_stop_service_accepts_missing_launch_agent(self, run) -> None:
        run.return_value.returncode = 3
        run.return_value.stderr = 'Could not find service "com.vdustr.codexbar-touchbar"'
        stop_service()

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_stop_service_rejects_unexpected_launchctl_failure(self, run) -> None:
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "Not privileged"
        run.return_value.args = ["launchctl", "bootout"]
        with self.assertRaises(subprocess.CalledProcessError):
            stop_service()

    @patch("codexbar_touchbar.cli.subprocess.run")
    @patch("codexbar_touchbar.cli.codexbar_path", return_value="/custom/bin/codexbar")
    def test_launch_agent_pins_resolved_codexbar(self, _codexbar, _run) -> None:
        _run.return_value.returncode = 0
        with TemporaryDirectory() as temporary:
            plist = Path(temporary) / "agent.plist"
            with (
                patch("codexbar_touchbar.cli.launch_agent_path", return_value=plist),
                patch("codexbar_touchbar.cli.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.cli.sys.argv", ["/custom/current/codexbar-touchbar"]),
                patch("codexbar_touchbar.cli.bttcli_path", return_value="/custom/bin/bttcli"),
            ):
                install_service()
            payload = plistlib.loads(plist.read_bytes())
            self.assertEqual(
                payload["EnvironmentVariables"]["CODEXBAR_TOUCHBAR_CODEXBAR"],
                "/custom/bin/codexbar",
            )
            self.assertEqual(
                payload["EnvironmentVariables"]["CODEXBAR_TOUCHBAR_BTTCLI"],
                "/custom/bin/bttcli",
            )
            self.assertEqual(
                payload["EnvironmentVariables"]["CODEXBAR_TOUCHBAR_DATA_DIR"],
                temporary,
            )
            self.assertEqual(
                payload["ProgramArguments"],
                ["/custom/current/codexbar-touchbar", "serve"],
            )

    @patch("codexbar_touchbar.cli.subprocess.run")
    @patch("codexbar_touchbar.cli.codexbar_path", return_value="/custom/bin/codexbar")
    def test_module_install_preserves_python_interpreter(self, _codexbar, _run) -> None:
        _run.return_value.returncode = 0
        with TemporaryDirectory() as temporary:
            plist = Path(temporary) / "agent.plist"
            with (
                patch("codexbar_touchbar.cli.launch_agent_path", return_value=plist),
                patch("codexbar_touchbar.cli.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.cli.sys.executable", "/custom/bin/python"),
                patch("codexbar_touchbar.cli.sys.argv", ["/package/codexbar_touchbar/__main__.py"]),
                patch("codexbar_touchbar.cli.bttcli_path", return_value="/custom/bin/bttcli"),
            ):
                install_service()
            payload = plistlib.loads(plist.read_bytes())
            self.assertEqual(
                payload["ProgramArguments"],
                ["/custom/bin/python", "-m", "codexbar_touchbar", "serve"],
            )

    def test_install_stops_service_before_replacing_widgets(self) -> None:
        events = []
        with (
            patch("codexbar_touchbar.cli.stop_service", side_effect=lambda: events.append("stop")),
            patch("codexbar_touchbar.cli.install_service", side_effect=lambda: events.append("service")),
            patch("codexbar_touchbar.cli.install_widgets", side_effect=lambda _: events.append("widgets") or []),
            patch("codexbar_touchbar.cli.extract_icons", return_value={}),
            patch("codexbar_touchbar.cli.build_parser") as parser,
        ):
            parser.return_value.parse_args.return_value.command = "install"
            parser.return_value.parse_args.return_value.session_slots = 4
            main()
        self.assertEqual(events, ["stop", "widgets", "service"])

    def test_failed_update_restores_previous_service(self) -> None:
        events = []
        with (
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.stop_service", side_effect=lambda: events.append("stop")),
            patch("codexbar_touchbar.cli.start_service", side_effect=lambda: events.append("restore")),
            patch("codexbar_touchbar.cli.install_widgets", side_effect=OSError("BTT failed")),
            patch("codexbar_touchbar.cli.extract_icons", return_value={}),
            patch("codexbar_touchbar.cli.build_parser") as parser,
        ):
            plist.return_value.is_file.return_value = True
            parser.return_value.parse_args.return_value.command = "install"
            parser.return_value.parse_args.return_value.session_slots = 4
            with self.assertRaises(OSError):
                main()
        self.assertEqual(events, ["stop", "restore"])

    def test_uninstall_stops_service_before_removing_widgets(self) -> None:
        events = []
        with (
            patch("codexbar_touchbar.cli.uninstall_service", side_effect=lambda: events.append("service")),
            patch("codexbar_touchbar.cli.uninstall_widgets", side_effect=lambda _: events.append("widgets") or []),
            patch("codexbar_touchbar.cli.build_parser") as parser,
        ):
            parser.return_value.parse_args.return_value.command = "uninstall"
            parser.return_value.parse_args.return_value.session_slots = 4
            main()
        self.assertEqual(events, ["service", "widgets"])

    def test_invalid_uninstall_slot_count_does_not_stop_service(self) -> None:
        with (
            patch("codexbar_touchbar.cli.uninstall_service") as uninstall_service,
            patch("codexbar_touchbar.cli.uninstall_widgets") as uninstall_widgets,
            patch("codexbar_touchbar.cli.build_parser") as parser,
        ):
            parser.return_value.parse_args.return_value.command = "uninstall"
            parser.return_value.parse_args.return_value.session_slots = 0
            with self.assertRaises(ValueError):
                main()
        uninstall_service.assert_not_called()
        uninstall_widgets.assert_not_called()

    def test_doctor_requires_launch_agent(self) -> None:
        snapshot = {"sessions": [], "usage": [], "errors": {"sessions": None, "usage": {}}}
        with (
            patch("codexbar_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("codexbar_touchbar.cli.launch_agent_path", return_value=Path("/missing")),
            patch("codexbar_touchbar.cli.Path.is_dir", return_value=True),
            patch("codexbar_touchbar.cli.bttcli_path", return_value="/bin/bttcli"),
            patch("codexbar_touchbar.cli.run_cli") as run_cli,
            patch("codexbar_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("codexbar_touchbar.cli.launch_agent_loaded", return_value=False),
            patch("codexbar_touchbar.cli.StateStore") as store_type,
        ):
            run_cli.return_value.returncode = 0
            run_cli.return_value.stdout = '{"BTTUUID":"installed"}'
            store_type.return_value.snapshot.return_value = snapshot
            self.assertEqual(doctor(), 1)

    def test_doctor_requires_btt_cli_connectivity_and_managed_trigger(self) -> None:
        snapshot = {"sessions": [], "usage": [], "errors": {"sessions": None, "usage": {}}}
        with (
            patch("codexbar_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.bttcli_path", return_value="/bin/bttcli"),
            patch("codexbar_touchbar.cli.run_cli") as run_cli,
            patch("codexbar_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("codexbar_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("codexbar_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            run_cli.return_value.returncode = 1
            run_cli.return_value.stdout = ""
            store_type.return_value.snapshot.return_value = snapshot
            self.assertEqual(doctor(), 1)

    def test_doctor_requires_successful_codex_usage_refresh(self) -> None:
        snapshot = {
            "sessions": [],
            "usage": [],
            "errors": {"sessions": None, "usage": {"codex": "timeout"}},
        }
        with (
            patch("codexbar_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.bttcli_path", return_value="/bin/bttcli"),
            patch("codexbar_touchbar.cli.run_cli") as run_cli,
            patch("codexbar_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("codexbar_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("codexbar_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            run_cli.return_value.returncode = 0
            run_cli.return_value.stdout = '{"BTTUUID":"installed"}'
            store_type.return_value.snapshot.return_value = snapshot
            self.assertEqual(doctor(), 1)

    def test_doctor_requires_running_bridge(self) -> None:
        snapshot = {
            "sessions": [],
            "usage": [{"provider": "codex", "usage": {}}],
            "errors": {"sessions": None, "usage": {}},
        }
        with (
            patch("codexbar_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.bttcli_path", return_value="/bin/bttcli"),
            patch("codexbar_touchbar.cli.run_cli") as run_cli,
            patch("codexbar_touchbar.cli.bridge_is_healthy", return_value=False),
            patch("codexbar_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("codexbar_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            run_cli.return_value.returncode = 0
            run_cli.return_value.stdout = '{"BTTUUID":"installed"}'
            store_type.return_value.snapshot.return_value = snapshot
            self.assertEqual(doctor(), 1)

    def test_doctor_accepts_valid_executable_path_containing_required(self) -> None:
        snapshot = {
            "sessions": [],
            "usage": [{"provider": "codex", "usage": {}}],
            "errors": {"sessions": None, "usage": {}},
        }
        with (
            patch(
                "codexbar_touchbar.cli.codexbar_path",
                return_value="/Users/me/Required Tools/codexbar",
            ),
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.bttcli_path", return_value="/bin/bttcli"),
            patch("codexbar_touchbar.cli.run_cli") as run_cli,
            patch("codexbar_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("codexbar_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("codexbar_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            run_cli.return_value.returncode = 0
            run_cli.return_value.stdout = '{"BTTUUID":"installed"}'
            store_type.return_value.snapshot.return_value = snapshot
            self.assertEqual(doctor(), 0)

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_uninstall_boots_out_loaded_label_without_plist(self, run) -> None:
        run.return_value.returncode = 0
        with patch("codexbar_touchbar.cli.launch_agent_path", return_value=Path("/missing")):
            uninstall_service()
        self.assertIn("com.vdustr.codexbar-touchbar", run.call_args.args[0][-1])


if __name__ == "__main__":
    unittest.main()
