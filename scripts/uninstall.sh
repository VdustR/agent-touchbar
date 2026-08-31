#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${CODEXBAR_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/CodexBarTouchBar}"
BIN_DIR="${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
COMMAND="$BIN_DIR/codexbar-touchbar"

VENV_COMMAND="$INSTALL_ROOT/venv/bin/codexbar-touchbar"
BTTCLI=/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli
PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.plist"

if [ -x "$COMMAND" ]; then
  "$COMMAND" uninstall "$@"
elif [ -x "$VENV_COMMAND" ]; then
  "$VENV_COMMAND" uninstall "$@"
else
  /bin/launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  if [ -x "$BTTCLI" ]; then
    python3 - <<'PY' | while IFS= read -r trigger_id; do
import uuid

namespace = uuid.UUID("f4a5b457-924c-49bc-a878-86034bd43261")
names = ["Codex usage", "Claude usage", "Antigravity usage", "Attention session", "Agent usage"]
names.extend(f"Agent session {index}" for index in range(1, 13))
for name in names:
    print(str(uuid.uuid5(namespace, name)).upper())
PY
      "$BTTCLI" delete_trigger "uuid=$trigger_id" >/dev/null 2>&1 || true
    done
  fi
fi
rm -f "$COMMAND"

echo "Removed the service, command, and BetterTouchTool widgets."
echo "Runtime logs and extracted icons remain at: $INSTALL_ROOT"
