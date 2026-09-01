from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class ScriptTests(unittest.TestCase):
    def test_ci_runs_the_declared_static_type_check(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        workflow = (repository / ".github/workflows/ci.yml").read_text()
        project = (repository / "pyproject.toml").read_text()
        self.assertIn("pyright src tests", workflow)
        self.assertIn("'.[dev]'", workflow)
        self.assertIn('pyright==1.1.411', project)

    def test_fallback_uninstall_does_not_suppress_unexpected_bootout_failures(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "uninstall.sh").read_text()
        self.assertIn("Could not find specified service", script)
        self.assertIn("No such process", script)
        self.assertNotIn(
            'bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar" 2>/dev/null || true',
            script,
        )

    def test_renderer_install_does_not_suppress_bootout_failures(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install-renderer.sh").read_text()
        self.assertIn("Could not find specified service", script)
        self.assertNotIn('bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true', script)

    def test_uninstall_removes_venv_and_reports_configured_data_directory(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "uninstall.sh").read_text()
        self.assertIn('rm -rf "$INSTALL_ROOT/venv"', script)
        self.assertIn('DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}"', script)
        self.assertIn('remain at: $DATA_DIR', script)

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
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
