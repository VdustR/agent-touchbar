"""BetterTouchTool trigger generation and installation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from .core import APP_NAMES, PROVIDERS, find_executable

NAMESPACE = uuid.UUID("f4a5b457-924c-49bc-a878-86034bd43261")
BASE_URL = "http://127.0.0.1:4317"


def bttcli_path() -> str:
    return find_executable(
        "bttcli",
        ("/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli",),
    )


def data_dir() -> Path:
    return Path(os.environ.get("CODEXBAR_TOUCHBAR_DATA_DIR", Path.home() / "Library/Application Support/CodexBarTouchBar"))


def widget_uuid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name)).upper()


def icon_path(provider: str) -> str:
    return str(data_dir() / "icons" / f"{provider}.png")


def slot_state_path() -> Path:
    return data_dir() / "session-slots.json"


def previous_slot_count(default: int = 4) -> int:
    try:
        payload = json.loads(slot_state_path().read_text())
        value = payload.get("sessionSlots")
        return value if isinstance(value, int) and 1 <= value <= 12 else default
    except (OSError, json.JSONDecodeError):
        return default


def validate_slot_count(value: int) -> int:
    if not 1 <= value <= 12:
        raise ValueError("session slots must be between 1 and 12")
    return value


def widget(name: str, script: str, action: str, width: int, order: int, interval: float) -> dict:
    return {
        "BTTUUID": widget_uuid(name),
        "BTTTriggerType": 642,
        "BTTTriggerClass": "BTTTriggerTypeTouchBar",
        "BTTWidgetName": name,
        "BTTEnabled": 1,
        "BTTOrder": order,
        "BTTShellScriptWidgetGestureConfig": "/bin/bash:::-c:::-::::",
        "BTTTriggerConfig": {
            "BTTTouchBarButtonColor": "20, 25, 32, 255",
            "BTTTouchBarFontColor": "235, 241, 248, 255",
            "BTTTouchBarFontSize": 11,
            "BTTTouchBarItemPadding": 6,
            "BTTTouchBarButtonWidth": width,
            "BTTTouchBarButtonHeight": 28,
            "BTTTouchBarShellScriptString": script,
            "BTTTouchBarScriptUpdateInterval": interval,
            "BTTTouchBarAlwaysShowButton": True,
        },
        "BTTActionsToExecute": [{
            "BTTPredefinedActionType": 137,
            "BTTTerminalCommand": action,
        }],
    }


def quota_script(provider: str) -> str:
    return rf'''/usr/bin/curl -sf {BASE_URL}/api/btt | /usr/bin/python3 -c '
import json,os,sys
d=json.load(sys.stdin)
p=next((x for x in d.get("providers",[]) if x.get("provider")=="{provider}"),None)
if p:
 w=p.get("windows",[]); parts=[]; remaining=[]
 for x in w:
  if x.get("usedPercent") is not None:
   r=100-x["usedPercent"]; remaining.append(r); parts.append("{{}} {{:.0f}}%".format(x.get("label","limit"),r))
 low=min(remaining) if remaining else 100
 bg="30, 78, 64, 255" if low>=50 else ("112, 72, 22, 255" if low>=20 else "112, 35, 42, 255")
 result={{"text":" · ".join(parts) or "—","background_color":bg,"font_color":"235, 248, 244, 255","font_size":11}}
 if os.path.isfile("{icon_path(provider)}"): result["icon_path"]="{icon_path(provider)}"
 print(json.dumps(result,ensure_ascii=False))
' '''


def provider_action(provider: str) -> str:
    return f'''/usr/bin/curl -sf -X POST -H 'Content-Type: application/json' --data '{{"provider":"{provider}"}}' {BASE_URL}/api/focus/provider >/dev/null'''


def session_script(index: int) -> str:
    return rf'''/usr/bin/curl -sf {BASE_URL}/api/btt | /usr/bin/python3 -c '
import json,os,sys
d=json.load(sys.stdin); s=d.get("sessions",[]); x=s[{index}] if len(s)>{index} else None
if not x: print("")
else:
 state=x.get("state") or "idle"; dot="●" if state=="active" else "○"
 name=x.get("sessionName") or x.get("projectName") or "session"; provider=x.get("provider") or "agent"
 bg="27, 75, 61, 255" if state=="active" else "27, 32, 40, 255"; fg="230, 250, 242, 255" if state=="active" else "190, 201, 214, 255"
 icon="{data_dir()}/icons/"+provider+".png"
 result={{"text":f"{{dot}} {{name[:16]}}","background_color":bg,"font_color":fg,"font_size":11}}
 if os.path.isfile(icon): result["icon_path"]=icon
 print(json.dumps(result,ensure_ascii=False))
' '''


def session_action(index: int) -> str:
    return rf'''SESSION_ID=$(/usr/bin/curl -sf {BASE_URL}/api/btt | /usr/bin/python3 -c 'import json,sys; s=json.load(sys.stdin).get("sessions",[]); print(s[{index}]["id"] if len(s)>{index} else "")')
if [ -n "$SESSION_ID" ]; then /usr/bin/curl -sf -X POST -H 'Content-Type: application/json' --data "{{\"id\":\"$SESSION_ID\"}}" {BASE_URL}/api/focus/session >/dev/null; fi'''


def definitions(session_slots: int = 4) -> list[dict]:
    validate_slot_count(session_slots)
    result = [
        widget(f"{provider.title()} usage", quota_script(provider), provider_action(provider), 104, 10 + index, 30)
        for index, provider in enumerate(PROVIDERS)
    ]
    result.extend(
        widget(f"Agent session {index + 1}", session_script(index), session_action(index), 132, 20 + index, 2.5)
        for index in range(session_slots)
    )
    return result


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([bttcli_path(), *args], check=check, capture_output=True, text=True)


def install_widgets(session_slots: int = 4) -> list[str]:
    validate_slot_count(session_slots)
    old_slot_count = previous_slot_count()
    results = []
    for definition in definitions(session_slots):
        trigger_id = definition["BTTUUID"]
        existing = run_cli("get_trigger", f"uuid={trigger_id}", check=False).stdout.strip()
        payload = json.dumps(definition, ensure_ascii=False, separators=(",", ":"))
        verb = "update_trigger" if existing not in {"", "null", "{}", "[]"} else "add_new_trigger"
        args = (verb, f"uuid={trigger_id}", f"json={payload}") if verb == "update_trigger" else (verb, f"json={payload}")
        run_cli(*args)
        results.append(f"{verb}: {definition['BTTWidgetName']}")
    for legacy_name in ("Attention session", "Agent usage"):
        legacy_id = widget_uuid(legacy_name)
        existing = run_cli("get_trigger", f"uuid={legacy_id}", check=False).stdout.strip()
        if existing not in {"", "null", "{}", "[]"}:
            run_cli("delete_trigger", f"uuid={legacy_id}")
            results.append(f"delete_trigger: {legacy_name}")
    for index in range(session_slots, old_slot_count):
        name = f"Agent session {index + 1}"
        run_cli("delete_trigger", f"uuid={widget_uuid(name)}", check=False)
        results.append(f"delete_trigger: {name}")
    slot_state_path().parent.mkdir(parents=True, exist_ok=True)
    slot_state_path().write_text(json.dumps({"sessionSlots": session_slots}) + "\n")
    return results


def uninstall_widgets(session_slots: int = 4) -> list[str]:
    session_slots = max(validate_slot_count(session_slots), previous_slot_count())
    names = [f"{provider.title()} usage" for provider in PROVIDERS]
    names.extend(f"Agent session {index + 1}" for index in range(session_slots))
    removed = []
    for name in names:
        trigger_id = widget_uuid(name)
        existing = run_cli("get_trigger", f"uuid={trigger_id}", check=False).stdout.strip()
        if existing not in {"", "null", "{}", "[]"}:
            run_cli("delete_trigger", f"uuid={trigger_id}")
            removed.append(name)
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
            subprocess.run(["/usr/bin/sips", "-s", "format", "png", source, "--out", target], check=True, capture_output=True)
            result[provider] = True
        else:
            target.unlink(missing_ok=True)
            result[provider] = False
    return result
