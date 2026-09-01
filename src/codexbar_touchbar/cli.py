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

from .core import StateStore, codexbar_path
from .server import serve

LABEL = "com.vdustr.codexbar-touchbar"
RENDERER_LABEL = f"{LABEL}.renderer"


def data_dir() -> Path:
    return Path(
        os.environ.get(
            "CODEXBAR_TOUCHBAR_DATA_DIR",
            Path.home() / "Library/Application Support/CodexBarTouchBar",
        )
    ).expanduser().resolve()


def launch_agent_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def renderer_launch_agent_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{RENDERER_LABEL}.plist"


def stop_service() -> None:
    result = subprocess.run(
        ["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not any(
        message in result.stderr
        for message in (
            "Could not find service",
            "Could not find specified service",
            "No such process",
        )
    ):
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )


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
            "CODEXBAR_TOUCHBAR_DATA_DIR": str(data_dir()),
        },
    }
    target.write_bytes(plistlib.dumps(payload))
    stop_service()
    subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True)


def start_service() -> None:
    subprocess.run(
        ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(launch_agent_path())],
        check=True,
    )


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
        except urllib.error.HTTPError as response:
            try:
                payload = json.loads(response.read())
            except json.JSONDecodeError:
                payload = None
            finally:
                response.close()
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("service") == "codexbar-touchbar":
            return True
        time.sleep(0.25)
    return False


def launch_agent_loaded(label: str = LABEL) -> bool:
    result = subprocess.run(
        ["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def doctor() -> int:
    checks: dict[str, object] = {}
    codexbar_available = False
    try:
        checks["codexbar"] = codexbar_path()
        codexbar_available = True
    except FileNotFoundError as error:
        checks["codexbar"] = str(error)
    checks["launchAgentConfigured"] = launch_agent_path().is_file()
    checks["launchAgentLoaded"] = launch_agent_loaded()
    checks["rendererLaunchAgentConfigured"] = renderer_launch_agent_path().is_file()
    checks["rendererLaunchAgentLoaded"] = launch_agent_loaded(RENDERER_LABEL)
    checks["bridge"] = bridge_is_healthy()
    checks["nativeRenderer"] = native_renderer_is_healthy()
    store = StateStore(usage_ttl=0, sessions_ttl=0)
    store.wait_for_initial_data()
    snapshot = store.snapshot()
    checks["sessionCount"] = len(snapshot["sessions"])
    checks["usageProviders"] = [item.get("provider") for item in snapshot["usage"]]
    checks["errors"] = snapshot["errors"]
    ok = (
        bool(checks.get("launchAgentConfigured"))
        and bool(checks.get("launchAgentLoaded"))
        and bool(checks.get("rendererLaunchAgentConfigured"))
        and bool(checks.get("rendererLaunchAgentLoaded"))
        and bool(checks.get("bridge"))
        and bool(checks.get("nativeRenderer"))
        and not snapshot["errors"]["sessions"]
        and "codex" not in snapshot["errors"]["usage"]
        and "codex" in checks["usageProviders"]
        and codexbar_available
    )
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def native_renderer_is_healthy() -> bool:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:4317/healthz", timeout=0.5) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as response:
            try:
                payload = json.loads(response.read())
            except json.JSONDecodeError:
                payload = None
            finally:
                response.close()
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            payload = None
        renderer = payload.get("nativeRenderer", {}) if isinstance(payload, dict) else {}
        capabilities = renderer.get("capabilities", {})
        if (
            renderer.get("alive") is True
            and isinstance(capabilities, dict)
            and capabilities.get("systemModal") is True
        ):
            return True
        time.sleep(0.25)
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codexbar-touchbar")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve")
    commands.add_parser("install")
    commands.add_parser("uninstall")
    commands.add_parser("doctor")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        serve("127.0.0.1", 4317)
    elif args.command == "install":
        restore_service = launch_agent_path().is_file()
        stop_service()
        try:
            install_service()
        except Exception as error:
            if restore_service:
                try:
                    start_service()
                except (OSError, subprocess.SubprocessError) as restore_error:
                    error.add_note(
                        f"Failed to restore the previous service: {type(restore_error).__name__}"
                    )
            raise
        print(json.dumps({"bridge": "installed"}))
    elif args.command == "uninstall":
        uninstall_service()
    elif args.command == "doctor":
        raise SystemExit(doctor())


if __name__ == "__main__":
    main()
