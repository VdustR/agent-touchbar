from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class ScriptTests(unittest.TestCase):
    def test_fallback_uninstall_reports_uuid_generator_failure(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken_python = root / "broken-python"
            bttcli = root / "bttcli"
            broken_python.write_text("#!/bin/sh\nexit 9\n")
            bttcli.write_text("#!/bin/sh\nexit 0\n")
            broken_python.chmod(0o755)
            bttcli.chmod(0o755)
            environment = {
                **os.environ,
                "HOME": str(root / "home"),
                "CODEXBAR_TOUCHBAR_INSTALL_ROOT": str(root / "missing-install"),
                "CODEXBAR_TOUCHBAR_BIN_DIR": str(root / "missing-bin"),
                "CODEXBAR_TOUCHBAR_PYTHON": str(broken_python),
                "CODEXBAR_TOUCHBAR_BTTCLI": str(bttcli),
            }
            result = subprocess.run(
                ["/bin/bash", str(repository / "scripts" / "uninstall.sh")],
                capture_output=True,
                text=True,
                env=environment,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Failed to remove", result.stderr)


if __name__ == "__main__":
    unittest.main()
