#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${CODEXBAR_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/CodexBarTouchBar}"
DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}"
BIN_DIR="${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
COMMAND="$BIN_DIR/codexbar-touchbar"

VENV_COMMAND="$INSTALL_ROOT/venv/bin/codexbar-touchbar"
BTTCLI=${CODEXBAR_TOUCHBAR_BTTCLI:-$(command -v bttcli || true)}
if [ -z "$BTTCLI" ]; then
  BTTCLI=/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli
fi
PYTHON_BIN=${CODEXBAR_TOUCHBAR_PYTHON:-$(command -v python3 || true)}
PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.plist"

if [ -x "$COMMAND" ]; then
  "$COMMAND" uninstall "$@"
elif [ -x "$VENV_COMMAND" ]; then
  "$VENV_COMMAND" uninstall "$@"
else
  if ! bootout_output=$(/bin/launchctl bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar" 2>&1); then
    case "$bootout_output" in
      *"Could not find specified service"*|*"No such process"*) ;;
      *)
        echo "$bootout_output" >&2
        exit 1
        ;;
    esac
  fi
  rm -f "$PLIST"
  cleanup_failed=0
  if [ -x "$BTTCLI" ] && [ -x "$PYTHON_BIN" ]; then
    trigger_file=$(mktemp)
    if "$PYTHON_BIN" - >"$trigger_file" <<'PY'
import uuid

namespace = uuid.UUID("f4a5b457-924c-49bc-a878-86034bd43261")
names = ["Codex usage", "Claude usage", "Antigravity usage", "Attention session", "Agent usage"]
names.extend(f"Agent session {index}" for index in range(1, 13))
for name in names:
    print(str(uuid.uuid5(namespace, name)).upper())
print("E4F85058-56B7-4DBD-9064-3C26F11B8C52")
PY
    then
      while IFS= read -r trigger_id; do
        if ! "$BTTCLI" delete_trigger "uuid=$trigger_id" >/dev/null 2>&1; then
          cleanup_failed=1
        fi
      done < "$trigger_file"
    else
      cleanup_failed=1
    fi
    rm -f "$trigger_file"
  else
    cleanup_failed=1
  fi
  if [ "$cleanup_failed" -ne 0 ]; then
    echo "Failed to remove one or more BetterTouchTool widgets." >&2
    exit 1
  fi
fi
rm -f "$COMMAND"
rm -rf "$INSTALL_ROOT/venv"

echo "Removed the service, command, and BetterTouchTool widgets."
echo "Runtime logs and extracted icons remain at: $DATA_DIR"
