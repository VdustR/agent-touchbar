from __future__ import annotations

import plistlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codexbar_touchbar.cli import install_service


class CliTests(unittest.TestCase):
    @patch("codexbar_touchbar.cli.subprocess.run")
    @patch("codexbar_touchbar.cli.shutil.which", return_value="/tmp/bin/codexbar-touchbar")
    @patch("codexbar_touchbar.cli.codexbar_path", return_value="/custom/bin/codexbar")
    def test_launch_agent_pins_resolved_codexbar(self, _codexbar, _which, _run) -> None:
        with TemporaryDirectory() as temporary:
            plist = Path(temporary) / "agent.plist"
            with (
                patch("codexbar_touchbar.cli.launch_agent_path", return_value=plist),
                patch("codexbar_touchbar.cli.data_dir", return_value=Path(temporary)),
            ):
                install_service()
            payload = plistlib.loads(plist.read_bytes())
            self.assertEqual(
                payload["EnvironmentVariables"]["CODEXBAR_TOUCHBAR_CODEXBAR"],
                "/custom/bin/codexbar",
            )


if __name__ == "__main__":
    unittest.main()
