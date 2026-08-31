"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .btt import (
    bttcli_path,
    data_dir,
    extract_icons,
    install_widgets,
    run_cli,
    uninstall_widgets,
    widget_uuid,
)
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
    invoked = Path(sys.argv[0])
    if invoked.name == "codexbar-touchbar":
        executable = invoked if invoked.is_absolute() else Path(shutil.which(sys.argv[0]) or invoked)
        program_arguments = [str(executable.resolve()), "serve"]
    else:
        program_arguments = [sys.executable, "-m", "codexbar_touchbar", "serve"]
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
            "CODEXBAR_TOUCHBAR_BTTCLI": bttcli_path(),
            "CODEXBAR_TOUCHBAR_DATA_DIR": str(data_dir()),
        },
    }
    target.write_bytes(plistlib.dumps(payload))
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(target)], capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True)


def uninstall_service() -> None:
    target = launch_agent_path()
    result = subprocess.run(
        ["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not any(
        message in result.stderr
        for message in ("Could not find specified service", "No such process")
    ):
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    target.unlink(missing_ok=True)


def bridge_is_healthy() -> bool:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:4317/healthz", timeout=0.5) as response:
                payload = json.loads(response.read())
            if response.status == 200 and payload.get("ok") is True:
                return True
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(0.25)
    return False


def doctor() -> int:
    checks: dict[str, object] = {}
    try:
        checks["codexbar"] = codexbar_path()
    except FileNotFoundError as error:
        checks["codexbar"] = str(error)
    try:
        lookup = run_cli("get_trigger", f"uuid={widget_uuid('Codex usage')}", check=False)
        checks["betterTouchTool"] = (
            bttcli_path()
            and lookup.returncode == 0
            and lookup.stdout.strip() not in {"", "null", "{}", "[]"}
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        checks["betterTouchTool"] = False
    checks["launchAgent"] = launch_agent_path().is_file()
    checks["bridge"] = bridge_is_healthy()
    store = StateStore(usage_ttl=0, sessions_ttl=0)
    store.wait_for_initial_data()
    snapshot = store.snapshot()
    checks["sessionCount"] = len(snapshot["sessions"])
    checks["usageProviders"] = [item.get("provider") for item in snapshot["usage"]]
    checks["errors"] = snapshot["errors"]
    ok = (
        bool(checks.get("betterTouchTool"))
        and bool(checks.get("launchAgent"))
        and bool(checks.get("bridge"))
        and not snapshot["errors"]["sessions"]
        and "codex" not in snapshot["errors"]["usage"]
        and "codex" in checks["usageProviders"]
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
