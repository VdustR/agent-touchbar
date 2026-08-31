"""BetterTouchTool trigger generation and installation."""

from __future__ import annotations

import json
import base64
import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path

from .core import ATTENTION_STATES, APP_NAMES, PROVIDERS, find_executable, quota_windows

NAMESPACE = uuid.UUID("f4a5b457-924c-49bc-a878-86034bd43261")
BASE_URL = "http://127.0.0.1:4317"
BTT_CLI_TIMEOUT_SECONDS = 5.0


def bttcli_path() -> str:
    return find_executable(
        "bttcli",
        ("/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli",),
    )


def data_dir() -> Path:
    return Path(
        os.environ.get(
            "CODEXBAR_TOUCHBAR_DATA_DIR",
            Path.home() / "Library/Application Support/CodexBarTouchBar",
        )
    ).expanduser().resolve()


def widget_uuid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name)).upper()


def icon_path(provider: str) -> str:
    return str(data_dir() / "icons" / f"{provider}.png")


def icon_data(provider: str) -> str | None:
    path = Path(icon_path(provider))
    return base64.b64encode(path.read_bytes()).decode() if path.is_file() else None


def slot_state_path() -> Path:
    return data_dir() / "session-slots.json"


def slot_action_path(index: int) -> Path:
    return data_dir() / "actions" / f"session-{index + 1}.json"


def previous_slot_count(default: int = 12) -> int:
    try:
        payload = json.loads(slot_state_path().read_text())
        if not isinstance(payload, dict):
            return default
        value = payload.get("sessionSlots")
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 12
            else default
        )
    except (OSError, json.JSONDecodeError):
        return default


def validate_slot_count(value: int) -> int:
    if not 1 <= value <= 12:
        raise ValueError("session slots must be between 1 and 12")
    return value


def widget(name: str, action: str, width: int, order: int) -> dict:
    provider = next((item for item in PROVIDERS if name.lower().startswith(item)), None)
    result = {
        "BTTUUID": widget_uuid(name),
        "BTTTriggerType": 629,
        "BTTTriggerClass": "BTTTriggerTypeTouchBar",
        "BTTTouchBarButtonName": name,
        "BTTEnabled": 1,
        "BTTOrder": order,
        "BTTActionsToExecute": [
            {
                "BTTActionCategory": 0,
                "BTTPredefinedActionType": 206,
                "BTTShellTaskActionScript": action,
                "BTTShellTaskActionConfig": "/bin/bash:::-c:::-:::",
            }
        ],
        "BTTTriggerConfig": {
            "BTTTouchBarButtonColor": "20, 25, 32, 255",
            "BTTTouchBarFontColor": "235, 241, 248, 255",
            "BTTTouchBarButtonFontSize": 11,
            "BTTTouchBarItemPadding": 6,
            "BTTTouchBarButtonWidth": width,
            "BTTTouchBarButtonUseFixedWidth": 1,
            "BTTTouchBarButtonHeight": 28,
            "BTTTouchBarButtonUseFixedHeight": 1,
            "BTTTouchBarAlwaysShowButton": True,
        },
    }
    encoded_icon = icon_data(provider) if provider else None
    if encoded_icon:
        result["BTTIconData"] = encoded_icon
        result["BTTTriggerConfig"]["BTTTouchBarItemIconWidth"] = 18
        result["BTTTriggerConfig"]["BTTTouchBarItemIconHeight"] = 18
    return result


def button_updates(snapshot: dict, session_slots: int = 4) -> list[tuple[str, dict]]:
    updates: list[tuple[str, dict]] = []
    usage = {item.get("provider"): item for item in snapshot.get("usage", [])}
    for provider in PROVIDERS:
        windows = quota_windows(usage.get(provider, {}))
        parts = []
        remaining = []
        for window in windows:
            used = window.get("usedPercent")
            if isinstance(used, (int, float)):
                value = 100 - used
                remaining.append(value)
                parts.append(f"{window.get('label', 'limit')} {value:.0f}%")
        counts = snapshot.get("sessionCounts", {}).get(provider)
        if isinstance(counts, dict):
            for state in ("active", "idle"):
                count = counts.get(state)
                if isinstance(count, int) and count > 0:
                    parts.append(f"{count} {state}")
        low = min(remaining) if remaining else None
        color = "55, 60, 68, 255" if low is None else ("30, 78, 64, 255" if low >= 50 else ("112, 72, 22, 255" if low >= 20 else "112, 35, 42, 255"))
        updates.append((widget_uuid(f"{provider.title()} usage"), {
            "BTTTouchBarButtonName": " · ".join(parts) or "—",
            "BTTTriggerConfig": {"BTTTouchBarButtonColor": color},
        }))
    sessions = display_sessions(snapshot, session_slots)
    for index, item in enumerate(sessions):
        payload: dict = {"BTTEnabled": True}
        active = item.get("state") == "active"
        attention = item.get("state") in ATTENTION_STATES
        session_name = item.get("sessionName")
        project_name = item.get("projectName")
        if isinstance(session_name, str) and session_name:
            name = session_name
        elif isinstance(project_name, str) and project_name:
            name = f"⌁ {project_name}"
        else:
            name = "session"
        payload.update({
            "BTTTouchBarButtonName": f"{'!' if attention else ('●' if active else '○')} {name[:16]}",
            "BTTOrder": -session_slots + index if attention else 20 + index,
            "BTTTriggerConfig": {"BTTTouchBarButtonColor": "112, 35, 42, 255" if attention else ("27, 75, 61, 255" if active else "27, 32, 40, 255")},
        })
        encoded_icon = icon_data(item.get("provider", ""))
        if encoded_icon:
            payload["BTTIconData"] = encoded_icon
            payload["BTTTriggerConfig"].update({
                "BTTTouchBarItemIconWidth": 18,
                "BTTTouchBarItemIconHeight": 18,
            })
        updates.append((widget_uuid(f"Agent session {index + 1}"), payload))
    return updates


def display_sessions(snapshot: dict, session_slots: int) -> list[dict]:
    return [
        item
        for item in snapshot.get("sessions", [])
        if item.get("provider") == "codex"
        and item.get("state") in ATTENTION_STATES | {"active", "idle", "available"}
        and item.get("source") == "desktopApp"
    ][:session_slots]


def update_buttons(
    snapshot: dict, session_slots: int = 4, previous: dict[str, dict] | None = None
) -> dict[str, dict]:
    current = dict(button_updates(snapshot, session_slots))
    sessions = display_sessions(snapshot, session_slots)
    session_ids = {widget_uuid(f"Agent session {index + 1}") for index in range(session_slots)}
    for index, session in enumerate(sessions):
        current[widget_uuid(f"Agent session {index + 1}")] = {
            **current[widget_uuid(f"Agent session {index + 1}")],
            "_sessionId": session["id"],
        }
    for index in range(session_slots):
        trigger_id = widget_uuid(f"Agent session {index + 1}")
        if trigger_id not in current and (previous is None or trigger_id in previous):
            existing = trigger_payload(trigger_id)
            if existing not in {"", "null", "{}", "[]"}:
                run_cli("delete_trigger", f"uuid={trigger_id}")
            slot_action_path(index).unlink(missing_ok=True)
    for trigger_id, payload in current.items():
        visible_payload = {key: value for key, value in payload.items() if not key.startswith("_")}
        session_index = (
            next(i for i in range(session_slots) if widget_uuid(f"Agent session {i + 1}") == trigger_id)
            if trigger_id in session_ids
            else None
        )
        changed = previous is None or previous.get(trigger_id) != payload
        if changed:
            if session_index is not None:
                existing = trigger_payload(trigger_id)
                if existing not in {"", "null", "{}", "[]"}:
                    # Partial update_trigger payloads are interpreted as generic
                    # mouse triggers by BTT 6.x. Replace the full Touch Bar
                    # definition whenever the rendered presentation changes.
                    run_cli("delete_trigger", f"uuid={trigger_id}")
                definition = session_definition(
                    session_index, sessions[session_index]["id"]
                )
                definition.update(visible_payload)
                definition["BTTTriggerConfig"] = {
                    **session_definition(
                        session_index, sessions[session_index]["id"]
                    )["BTTTriggerConfig"],
                    **visible_payload.get("BTTTriggerConfig", {}),
                }
                run_cli("add_new_trigger", f"json={json.dumps(definition, ensure_ascii=False, separators=(',', ':'))}")
                continue
            run_cli(
                "update_trigger",
                f"uuid={trigger_id}",
                f"json={json.dumps(visible_payload, separators=(',', ':'))}",
            )
    return current


def trigger_payload(trigger_id: str) -> str:
    lookup = run_cli("get_trigger", f"uuid={trigger_id}", check=False)
    if lookup.returncode != 0:
        raise subprocess.CalledProcessError(
            lookup.returncode, lookup.args, lookup.stdout, lookup.stderr
        )
    return lookup.stdout.strip()


def session_definition(index: int, session_id: str) -> dict:
    definition = widget(
        f"Agent session {index + 1}",
        session_action(session_id),
        132,
        20 + index,
    )
    # BTT 6.x dispatches dynamically added Touch Bar buttons through these
    # legacy top-level fields. Static quota buttons work with the action array,
    # but physical taps on runtime-added session buttons do not.
    definition["BTTPredefinedActionType"] = 137
    definition["BTTTerminalCommand"] = session_action(session_id)
    return definition


def provider_action(provider: str) -> str:
    return f'''/usr/bin/curl -sf -X POST -H 'Content-Type: application/json' --data '{{"provider":"{provider}"}}' {BASE_URL}/api/focus/provider >/dev/null'''


def session_action(session_id: str) -> str:
    payload = shlex.quote(json.dumps({"id": session_id}, separators=(",", ":")))
    return rf'''/usr/bin/curl -sf -X POST -H 'Content-Type: application/json' --data {payload} {BASE_URL}/api/focus/session >/dev/null'''


def definitions(session_slots: int = 4) -> list[dict]:
    validate_slot_count(session_slots)
    result = [
        widget(f"{provider.title()} usage", provider_action(provider), 172, 10 + index)
        for index, provider in enumerate(PROVIDERS)
    ]
    return result


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bttcli_path(), *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=BTT_CLI_TIMEOUT_SECONDS,
    )


def install_widgets(session_slots: int = 4) -> list[str]:
    validate_slot_count(session_slots)
    results = []
    for definition in definitions(session_slots):
        trigger_id = definition["BTTUUID"]
        existing = trigger_payload(trigger_id)
        payload = json.dumps(definition, ensure_ascii=False, separators=(",", ":"))
        if existing not in {"", "null", "{}", "[]"}:
            # BTT merges action arrays during update_trigger, which can leave a
            # leading No Action entry that intercepts physical Touch Bar taps.
            run_cli("delete_trigger", f"uuid={trigger_id}")
        run_cli("add_new_trigger", f"json={payload}")
        results.append(f"replace_trigger: {definition['BTTTouchBarButtonName']}")
    for index in range(12):
        name = f"Agent session {index + 1}"
        trigger_id = widget_uuid(name)
        existing = trigger_payload(trigger_id)
        if existing not in {"", "null", "{}", "[]"}:
            run_cli("delete_trigger", f"uuid={trigger_id}")
            results.append(f"delete_trigger: {name}")
    for legacy_name in ("Attention session", "Agent usage"):
        legacy_id = widget_uuid(legacy_name)
        existing = trigger_payload(legacy_id)
        if existing not in {"", "null", "{}", "[]"}:
            run_cli("delete_trigger", f"uuid={legacy_id}")
            results.append(f"delete_trigger: {legacy_name}")
    run_cli("delete_trigger", "uuid=E4F85058-56B7-4DBD-9064-3C26F11B8C52")
    slot_state_path().parent.mkdir(parents=True, exist_ok=True)
    slot_state_path().write_text(json.dumps({"sessionSlots": session_slots}) + "\n")
    return results


def uninstall_widgets(session_slots: int = 4) -> list[str]:
    validate_slot_count(session_slots)
    session_slots = 12
    names = [f"{provider.title()} usage" for provider in PROVIDERS]
    names.extend(("Attention session", "Agent usage"))
    names.extend(f"Agent session {index + 1}" for index in range(session_slots))
    removed = []
    for name in names:
        trigger_id = widget_uuid(name)
        lookup = run_cli("get_trigger", f"uuid={trigger_id}", check=False)
        if lookup.returncode != 0:
            raise subprocess.CalledProcessError(
                lookup.returncode, lookup.args, lookup.stdout, lookup.stderr
            )
        existing = lookup.stdout.strip()
        if existing not in {"", "null", "{}", "[]"}:
            run_cli("delete_trigger", f"uuid={trigger_id}")
            removed.append(name)
    legacy_id = "E4F85058-56B7-4DBD-9064-3C26F11B8C52"
    lookup = run_cli("get_trigger", f"uuid={legacy_id}", check=False)
    if lookup.returncode != 0:
        raise subprocess.CalledProcessError(
            lookup.returncode, lookup.args, lookup.stdout, lookup.stderr
        )
    if lookup.stdout.strip() not in {"", "null", "{}", "[]"}:
        run_cli("delete_trigger", f"uuid={legacy_id}")
        removed.append("Legacy agent usage")
    slot_state_path().unlink(missing_ok=True)
    return removed


def extract_icons() -> dict[str, bool]:
    sources = {
        "codex": "/Applications/ChatGPT.app/Contents/Resources/icon-chatgpt.png",
        "claude": "/Applications/Claude.app/Contents/Resources/electron.icns",
        "antigravity": "/Applications/Antigravity.app/Contents/Resources/icon.icns",
    }
    destination = data_dir() / "icons"
    destination.mkdir(parents=True, exist_ok=True)
    result = {}
    for provider, source in sources.items():
        target = destination / f"{provider}.png"
        if Path(source).is_file():
            subprocess.run(
                ["/usr/bin/sips", "-s", "format", "png", "-z", "36", "36", source, "--out", target],
                check=True,
                capture_output=True,
            )
            result[provider] = True
        else:
            target.unlink(missing_ok=True)
            result[provider] = False
    return result
