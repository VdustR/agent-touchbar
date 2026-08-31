"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .btt import data_dir, extract_icons, install_widgets, uninstall_widgets
from .core import StateStore, codexbar_path
from .server import serve

LABEL = "com.vdustr.codexbar-touchbar"


def launch_agent_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def install_service() -> None:
    target = launch_agent_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    log_dir = data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("codexbar-touchbar")
    program_arguments = (
        [str(Path(executable).resolve()), "serve"]
        if executable
        else [sys.executable, "-m", "codexbar_touchbar", "serve"]
    )
    payload = {
        "Label": LABEL,
        "ProgramArguments": program_arguments,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "stdout.log"),
        "StandardErrorPath": str(log_dir / "stderr.log"),
        "ProcessType": "Interactive",
        "EnvironmentVariables": {
            "CODEXBAR_TOUCHBAR_CODEXBAR": codexbar_path(),
            "CODEXBAR_TOUCHBAR_DATA_DIR": str(data_dir()),
        },
    }
    target.write_bytes(plistlib.dumps(payload))
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(target)], capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True)


def uninstall_service() -> None:
    target = launch_agent_path()
    if target.exists():
        subprocess.run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(target)], capture_output=True)
        target.unlink()


def doctor() -> int:
    checks: dict[str, object] = {}
    try:
        checks["codexbar"] = codexbar_path()
    except FileNotFoundError as error:
        checks["codexbar"] = str(error)
    checks["betterTouchTool"] = Path("/Applications/BetterTouchTool.app").is_dir()
    checks["launchAgent"] = launch_agent_path().is_file()
    store = StateStore(usage_ttl=0, sessions_ttl=0)
    store.wait_for_initial_data()
    snapshot = store.snapshot()
    checks["sessionCount"] = len(snapshot["sessions"])
    checks["usageProviders"] = [item.get("provider") for item in snapshot["usage"]]
    checks["errors"] = snapshot["errors"]
    ok = (
        bool(checks.get("betterTouchTool"))
        and bool(checks.get("launchAgent"))
        and not snapshot["errors"]["sessions"]
        and "Required" not in str(checks["codexbar"])
    )
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codexbar-touchbar")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve")
    install_parser = commands.add_parser("install")
    install_parser.add_argument("--session-slots", default=4, type=int)
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("--session-slots", default=4, type=int)
    commands.add_parser("doctor")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        serve("127.0.0.1", 4317)
    elif args.command == "install":
        icons = extract_icons()
        for result in install_widgets(args.session_slots):
            print(result)
        install_service()
        print(json.dumps({"icons": icons}))
    elif args.command == "uninstall":
        for name in uninstall_widgets(args.session_slots):
            print(f"removed: {name}")
        uninstall_service()
    elif args.command == "doctor":
        raise SystemExit(doctor())


if __name__ == "__main__":
    main()
