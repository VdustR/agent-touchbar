#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${AGENT_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/AgentTouchBar}"
DATA_DIR="${AGENT_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}"
BIN_DIR="${AGENT_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
COMMAND="$BIN_DIR/agent-touchbar"
LAUNCHCTL="${AGENT_TOUCHBAR_LAUNCHCTL:-/bin/launchctl}"

VENV_COMMAND="$INSTALL_ROOT/venv/bin/agent-touchbar"
PLIST="$HOME/Library/LaunchAgents/com.vdustr.agent-touchbar.plist"
RENDERER_LABEL=com.vdustr.agent-touchbar.renderer
RENDERER_PLIST="$HOME/Library/LaunchAgents/$RENDERER_LABEL.plist"
RENDERER_APP="${AGENT_TOUCHBAR_APP_PATH:-$HOME/Applications/Agent Touch Bar.app}"
LEGACY_RENDERER_APP="$INSTALL_ROOT/Agent Touch Bar.app"

if ! renderer_output=$("$LAUNCHCTL" bootout "gui/$(id -u)/$RENDERER_LABEL" 2>&1); then
  case "$renderer_output" in
    *"Could not find service"*|*"Could not find specified service"*|*"No such process"*) ;;
    *) echo "$renderer_output" >&2; exit 1 ;;
  esac
fi
renderer_pids=$(/usr/bin/pgrep -u "$(id -u)" -x agent-touchbar-host || true)
if [ -n "$renderer_pids" ]; then
  /bin/kill $renderer_pids
fi
rm -f "$RENDERER_PLIST"
rm -rf "$RENDERER_APP" "$LEGACY_RENDERER_APP"

if [ -x "$COMMAND" ]; then
  "$COMMAND" uninstall "$@"
elif [ -x "$VENV_COMMAND" ]; then
  "$VENV_COMMAND" uninstall "$@"
else
  if ! bootout_output=$("$LAUNCHCTL" bootout "gui/$(id -u)/com.vdustr.agent-touchbar" 2>&1); then
    case "$bootout_output" in
      *"Could not find service"*|*"Could not find specified service"*|*"No such process"*) ;;
      *)
        echo "$bootout_output" >&2
        exit 1
        ;;
    esac
  fi
  rm -f "$PLIST"
fi
rm -f "$COMMAND"
rm -rf "$INSTALL_ROOT/venv"
rm -rf "$INSTALL_ROOT/venv.rollback"
rm -rf "$INSTALL_ROOT/Agent Touch Bar.app.rollback"
rm -f "$INSTALL_ROOT/renderer.plist.rollback"
rm -f "$INSTALL_ROOT/install-transaction.committed"

echo "Removed the bridge, native renderer, command, and isolated Python environment."
echo "Runtime logs and extracted icons remain at: $DATA_DIR"
