from __future__ import annotations

import plistlib
import subprocess
import unittest
from io import BytesIO
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from agent_touchbar.cli import bridge_is_healthy, doctor, install_service, launch_agent_loaded, main, native_renderer_is_healthy, state_contract_is_healthy, stop_service, uninstall_service


class CliTests(unittest.TestCase):
    @patch("agent_touchbar.cli.subprocess.run")
    @patch("agent_touchbar.cli.os.getuid", return_value=1234)
    def test_launch_agent_loaded_queries_user_domain(self, _getuid, run) -> None:
        run.return_value.returncode = 0
        self.assertTrue(launch_agent_loaded())
        self.assertEqual(run.call_args.args[0][-1], "gui/1234/com.vdustr.agent-touchbar")

    @patch("agent_touchbar.cli.subprocess.run")
    def test_stop_service_accepts_missing_launch_agent(self, run) -> None:
        run.return_value.returncode = 3
        run.return_value.stderr = "Could not find service"
        stop_service()

    @patch("agent_touchbar.cli.subprocess.run")
    def test_stop_service_rejects_unexpected_failure(self, run) -> None:
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "Not privileged"
        run.return_value.args = ["launchctl", "bootout"]
        with self.assertRaises(subprocess.CalledProcessError):
            stop_service()

    @patch("agent_touchbar.cli.subprocess.run")
    @patch("agent_touchbar.cli.codexbar_path", return_value="/custom/bin/codexbar")
    def test_launch_agent_has_only_required_environment(self, _codexbar, run) -> None:
        run.return_value.returncode = 0
        with TemporaryDirectory() as temporary:
            plist = Path(temporary) / "agent.plist"
            with (
                patch("agent_touchbar.cli.launch_agent_path", return_value=plist),
                patch("agent_touchbar.cli.data_dir", return_value=Path(temporary)),
                patch("agent_touchbar.cli.sys.argv", ["/custom/current/agent-touchbar"]),
            ):
                install_service()
            payload = plistlib.loads(plist.read_bytes())
            self.assertEqual(payload["EnvironmentVariables"], {
                "AGENT_TOUCHBAR_CODEXBAR": "/custom/bin/codexbar",
                "AGENT_TOUCHBAR_DATA_DIR": temporary,
            })
            self.assertEqual(payload["KeepAlive"], {"SuccessfulExit": False})

    @patch("agent_touchbar.cli.subprocess.run")
    @patch("agent_touchbar.cli.codexbar_path", return_value="/custom/bin/codexbar")
    def test_launch_agent_preserves_disabled_login_preference(self, _codexbar, run) -> None:
        run.return_value.returncode = 0
        with TemporaryDirectory() as temporary:
            plist = Path(temporary) / "agent.plist"
            with (
                patch("agent_touchbar.cli.launch_agent_path", return_value=plist),
                patch("agent_touchbar.cli.data_dir", return_value=Path(temporary)),
                patch("agent_touchbar.cli.sys.argv", ["/custom/current/agent-touchbar"]),
                patch.dict("agent_touchbar.cli.os.environ", {"AGENT_TOUCHBAR_OPEN_AT_LOGIN": "0"}),
            ):
                install_service()

            self.assertFalse(plistlib.loads(plist.read_bytes())["RunAtLoad"])

    def test_install_replaces_bridge_service(self) -> None:
        events: list[str] = []
        with (
            patch("agent_touchbar.cli.stop_service", side_effect=lambda: events.append("stop")),
            patch("agent_touchbar.cli.install_service", side_effect=lambda: events.append("install")),
            patch("agent_touchbar.cli.launch_agent_path") as plist,
            patch("agent_touchbar.cli.build_parser") as parser,
        ):
            plist.return_value.is_file.return_value = False
            parser.return_value.parse_args.return_value.command = "install"
            parser.return_value.parse_args.return_value.session_slots = 4
            main()
        self.assertEqual(events, ["stop", "install"])

    def test_failed_install_restores_previous_service(self) -> None:
        events: list[str] = []
        with (
            patch("agent_touchbar.cli.launch_agent_path") as plist,
            patch("agent_touchbar.cli.stop_service", side_effect=lambda: events.append("stop")),
            patch("agent_touchbar.cli.install_service", side_effect=OSError("failed")),
            patch("agent_touchbar.cli.start_service", side_effect=lambda: events.append("restore")),
            patch("agent_touchbar.cli.build_parser") as parser,
        ):
            plist.return_value.is_file.return_value = True
            parser.return_value.parse_args.return_value.command = "install"
            parser.return_value.parse_args.return_value.session_slots = 4
            with self.assertRaises(OSError):
                main()
        self.assertEqual(events, ["stop", "restore"])

    def test_uninstall_removes_bridge_service(self) -> None:
        with (
            patch("agent_touchbar.cli.uninstall_service") as remove,
            patch("agent_touchbar.cli.build_parser") as parser,
        ):
            parser.return_value.parse_args.return_value.command = "uninstall"
            parser.return_value.parse_args.return_value.session_slots = 4
            main()
        remove.assert_called_once_with()

    def doctor_result(self, renderer: bool) -> int:
        snapshot = {
            "sessions": [], "usage": [{"provider": "codex", "usage": {}}],
            "errors": {"sessions": None, "usage": {}},
        }
        with (
            patch("agent_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("agent_touchbar.cli.launch_agent_path") as plist,
            patch("agent_touchbar.cli.renderer_launch_agent_path") as renderer_plist,
            patch("agent_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("agent_touchbar.cli.native_renderer_is_healthy", return_value=renderer),
            patch("agent_touchbar.cli.state_contract_is_healthy", return_value=True),
            patch("agent_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("agent_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            renderer_plist.return_value.is_file.return_value = True
            store_type.return_value.snapshot.return_value = snapshot
            return doctor()

    def test_doctor_requires_native_renderer(self) -> None:
        self.assertEqual(self.doctor_result(False), 1)

    def test_doctor_accepts_complete_native_install(self) -> None:
        self.assertEqual(self.doctor_result(True), 0)

    def test_doctor_accepts_healthy_manually_launched_renderer(self) -> None:
        with (
            patch("agent_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("agent_touchbar.cli.launch_agent_path") as plist,
            patch("agent_touchbar.cli.renderer_launch_agent_path") as renderer_plist,
            patch("agent_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("agent_touchbar.cli.native_renderer_is_healthy", return_value=True),
            patch("agent_touchbar.cli.state_contract_is_healthy", return_value=True),
            patch(
                "agent_touchbar.cli.launch_agent_loaded",
                side_effect=lambda label="com.vdustr.agent-touchbar": not label.endswith(".renderer"),
            ),
        ):
            plist.return_value.is_file.return_value = True
            renderer_plist.return_value.is_file.return_value = True

            self.assertEqual(doctor(installation_only=True), 0)

    def test_installation_doctor_does_not_collect_provider_data(self) -> None:
        with (
            patch("agent_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("agent_touchbar.cli.launch_agent_path") as plist,
            patch("agent_touchbar.cli.renderer_launch_agent_path") as renderer_plist,
            patch("agent_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("agent_touchbar.cli.native_renderer_is_healthy", return_value=True),
            patch("agent_touchbar.cli.state_contract_is_healthy", return_value=True),
            patch("agent_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("agent_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            renderer_plist.return_value.is_file.return_value = True
            self.assertEqual(doctor(installation_only=True), 0)
        store_type.assert_not_called()

    def test_state_contract_requires_versioned_item_list(self) -> None:
        response = BytesIO(b'{"schemaVersion":1,"items":[]}')
        with patch("agent_touchbar.cli.urllib.request.urlopen", return_value=response):
            self.assertTrue(state_contract_is_healthy())

    def test_renderer_health_reads_liveness_from_aggregate_503(self) -> None:
        error = HTTPError(
            "http://127.0.0.1:4317/healthz",
            503,
            "unhealthy",
            Message(),
            BytesIO(b'{"ok":false,"nativeRenderer":{"alive":true,"capabilities":{"systemModal":true}}}'),
        )
        with patch("agent_touchbar.cli.urllib.request.urlopen", side_effect=error):
            self.assertTrue(native_renderer_is_healthy())

    def test_bridge_health_reads_service_identity_from_aggregate_503(self) -> None:
        error = HTTPError(
            "http://127.0.0.1:4317/healthz",
            503,
            "unhealthy",
            Message(),
            BytesIO(b'{"service":"agent-touchbar","ok":false}'),
        )
        with patch("agent_touchbar.cli.urllib.request.urlopen", side_effect=error):
            self.assertTrue(bridge_is_healthy())

    @patch("agent_touchbar.cli.subprocess.run")
    def test_uninstall_boots_out_loaded_label_without_plist(self, run) -> None:
        run.return_value.returncode = 0
        with patch("agent_touchbar.cli.launch_agent_path", return_value=Path("/missing")):
            uninstall_service()
        self.assertIn("com.vdustr.agent-touchbar", run.call_args.args[0][-1])


if __name__ == "__main__":
    unittest.main()
