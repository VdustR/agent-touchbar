from __future__ import annotations

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

    def test_setup_check_requires_swift_5_10(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "skills" / "setup-agent-touchbar" / "scripts" / "check.sh").read_text()
        self.assertIn('SWIFT_MINOR" -ge 10', script)
        self.assertIn("missing: swift 5.10 or newer", script)

    def test_fallback_uninstall_does_not_suppress_unexpected_bootout_failures(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "uninstall.sh").read_text()
        self.assertIn("Could not find service", script)
        self.assertIn("Could not find specified service", script)
        self.assertIn("No such process", script)
        self.assertNotIn(
            'bootout "gui/$(id -u)/com.vdustr.agent-touchbar" 2>/dev/null || true',
            script,
        )

    def test_renderer_install_does_not_suppress_bootout_failures(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install-renderer.sh").read_text()
        self.assertIn("Could not find service", script)
        self.assertIn("Could not find specified service", script)
        self.assertNotIn('bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true', script)

    def test_installer_stages_renderer_before_replacing_bridge(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install.sh").read_text()
        self.assertLess(
            script.index('"$REPO_ROOT/scripts/install-renderer.sh"'),
            script.index('"$VENV/bin/python" -m pip install'),
        )

    def test_installer_migrates_and_stops_legacy_services_before_install(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install.sh").read_text()
        install = script.index('"$REPO_ROOT/scripts/install-renderer.sh"')
        self.assertLess(script.index("migrate_legacy_install\nstop_legacy_services"), install)
        self.assertLess(script.index("trap rollback_install ERR"), script.index("stop_legacy_services\n", script.index("trap rollback_install ERR")))
        self.assertIn("restore_legacy_services", script)
        self.assertIn('launcherIconPath', script)
        self.assertIn('legacy_icon_path#"$LEGACY_INSTALL_ROOT"/', script)

    def test_installer_removes_legacy_install_only_after_new_doctor(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install.sh").read_text()
        doctor = script.index('agent-touchbar" doctor')
        self.assertGreater(script.index('rm -rf "$LEGACY_INSTALL_ROOT"'), doctor)

    def test_installer_restores_previous_bridge_when_validation_fails(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install.sh").read_text()
        self.assertIn("trap rollback_install ERR", script)
        self.assertLess(script.index("trap rollback_install ERR"), script.index('mv "$VENV" "$VENV_BACKUP"'))
        self.assertLess(script.index('mv "$VENV" "$VENV_BACKUP"'), script.index('"$PYTHON_BIN" -m venv "$VENV"'))
        self.assertIn('mv "$VENV_BACKUP" "$VENV"', script)
        self.assertIn('mv "$APP_BACKUP" "$APP_PATH"', script)
        self.assertIn('mv "$RENDERER_PLIST_BACKUP" "$RENDERER_PLIST"', script)
        self.assertIn('exit "$failure_status"', script)
        self.assertIn('mv "$RENDERER_PLIST" "$RENDERER_PLIST_BACKUP"', script)
        self.assertIn('PYTHON_BIN="$VENV_BACKUP/${PYTHON_BIN#"$VENV"/}"', script)
        self.assertIn("trap 'rollback_install 130' INT", script)
        self.assertIn("trap 'rollback_install 143' TERM", script)
        transaction_start = script.index('mkdir -p "$INSTALL_ROOT" "$BIN_DIR"')
        self.assertLess(
            script.index('mv "$VENV_BACKUP" "$VENV"', transaction_start),
            script.index("trap rollback_install ERR", transaction_start),
        )
        self.assertLess(script.index('agent-touchbar\" doctor'), script.index('rm -rf "$VENV_BACKUP"', script.index('agent-touchbar\" doctor')))

    def test_uninstall_removes_venv_and_reports_configured_data_directory(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "uninstall.sh").read_text()
        self.assertIn('rm -rf "$INSTALL_ROOT/venv"', script)
        self.assertIn('rm -rf "$INSTALL_ROOT/venv.rollback"', script)
        self.assertIn('rm -rf "$INSTALL_ROOT/Agent Touch Bar.app.rollback"', script)
        self.assertIn('rm -f "$INSTALL_ROOT/renderer.plist.rollback"', script)
        self.assertIn('rm -f "$INSTALL_ROOT/install-transaction.committed"', script)
        self.assertIn('DATA_DIR="${AGENT_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}"', script)
        self.assertIn('remain at: $DATA_DIR', script)

if __name__ == "__main__":
    unittest.main()
