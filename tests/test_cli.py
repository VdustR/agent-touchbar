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

from codexbar_touchbar.cli import doctor, install_service, launch_agent_loaded, main, native_renderer_is_healthy, stop_service, uninstall_service


class CliTests(unittest.TestCase):
    @patch("codexbar_touchbar.cli.subprocess.run")
    @patch("codexbar_touchbar.cli.os.getuid", return_value=1234)
    def test_launch_agent_loaded_queries_user_domain(self, _getuid, run) -> None:
        run.return_value.returncode = 0
        self.assertTrue(launch_agent_loaded())
        self.assertEqual(run.call_args.args[0][-1], "gui/1234/com.vdustr.codexbar-touchbar")

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_stop_service_accepts_missing_launch_agent(self, run) -> None:
        run.return_value.returncode = 3
        run.return_value.stderr = "Could not find service"
        stop_service()

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_stop_service_rejects_unexpected_failure(self, run) -> None:
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "Not privileged"
        run.return_value.args = ["launchctl", "bootout"]
        with self.assertRaises(subprocess.CalledProcessError):
            stop_service()

    @patch("codexbar_touchbar.cli.subprocess.run")
    @patch("codexbar_touchbar.cli.codexbar_path", return_value="/custom/bin/codexbar")
    def test_launch_agent_has_only_required_environment(self, _codexbar, run) -> None:
        run.return_value.returncode = 0
        with TemporaryDirectory() as temporary:
            plist = Path(temporary) / "agent.plist"
            with (
                patch("codexbar_touchbar.cli.launch_agent_path", return_value=plist),
                patch("codexbar_touchbar.cli.data_dir", return_value=Path(temporary)),
                patch("codexbar_touchbar.cli.sys.argv", ["/custom/current/codexbar-touchbar"]),
            ):
                install_service()
            payload = plistlib.loads(plist.read_bytes())
            self.assertEqual(payload["EnvironmentVariables"], {
                "CODEXBAR_TOUCHBAR_CODEXBAR": "/custom/bin/codexbar",
                "CODEXBAR_TOUCHBAR_DATA_DIR": temporary,
            })

    def test_install_replaces_bridge_service(self) -> None:
        events: list[str] = []
        with (
            patch("codexbar_touchbar.cli.stop_service", side_effect=lambda: events.append("stop")),
            patch("codexbar_touchbar.cli.install_service", side_effect=lambda: events.append("install")),
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.build_parser") as parser,
        ):
            plist.return_value.is_file.return_value = False
            parser.return_value.parse_args.return_value.command = "install"
            parser.return_value.parse_args.return_value.session_slots = 4
            main()
        self.assertEqual(events, ["stop", "install"])

    def test_failed_install_restores_previous_service(self) -> None:
        events: list[str] = []
        with (
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.stop_service", side_effect=lambda: events.append("stop")),
            patch("codexbar_touchbar.cli.install_service", side_effect=OSError("failed")),
            patch("codexbar_touchbar.cli.start_service", side_effect=lambda: events.append("restore")),
            patch("codexbar_touchbar.cli.build_parser") as parser,
        ):
            plist.return_value.is_file.return_value = True
            parser.return_value.parse_args.return_value.command = "install"
            parser.return_value.parse_args.return_value.session_slots = 4
            with self.assertRaises(OSError):
                main()
        self.assertEqual(events, ["stop", "restore"])

    def test_uninstall_removes_bridge_service(self) -> None:
        with (
            patch("codexbar_touchbar.cli.uninstall_service") as remove,
            patch("codexbar_touchbar.cli.build_parser") as parser,
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
            patch("codexbar_touchbar.cli.codexbar_path", return_value="/bin/codexbar"),
            patch("codexbar_touchbar.cli.launch_agent_path") as plist,
            patch("codexbar_touchbar.cli.bridge_is_healthy", return_value=True),
            patch("codexbar_touchbar.cli.native_renderer_is_healthy", return_value=renderer),
            patch("codexbar_touchbar.cli.launch_agent_loaded", return_value=True),
            patch("codexbar_touchbar.cli.StateStore") as store_type,
        ):
            plist.return_value.is_file.return_value = True
            store_type.return_value.snapshot.return_value = snapshot
            return doctor()

    def test_doctor_requires_native_renderer(self) -> None:
        self.assertEqual(self.doctor_result(False), 1)

    def test_doctor_accepts_complete_native_install(self) -> None:
        self.assertEqual(self.doctor_result(True), 0)

    def test_renderer_health_reads_liveness_from_aggregate_503(self) -> None:
        error = HTTPError(
            "http://127.0.0.1:4317/healthz",
            503,
            "unhealthy",
            Message(),
            BytesIO(b'{"ok":false,"nativeRenderer":{"alive":true}}'),
        )
        with patch("codexbar_touchbar.cli.urllib.request.urlopen", side_effect=error):
            self.assertTrue(native_renderer_is_healthy())

    @patch("codexbar_touchbar.cli.subprocess.run")
    def test_uninstall_boots_out_loaded_label_without_plist(self, run) -> None:
        run.return_value.returncode = 0
        with patch("codexbar_touchbar.cli.launch_agent_path", return_value=Path("/missing")):
            uninstall_service()
        self.assertIn("com.vdustr.codexbar-touchbar", run.call_args.args[0][-1])


if __name__ == "__main__":
    unittest.main()
