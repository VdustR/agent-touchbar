#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${CODEXBAR_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/CodexBarTouchBar}"
DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}"
BIN_DIR="${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
COMMAND="$BIN_DIR/codexbar-touchbar"
LAUNCHCTL="${CODEXBAR_TOUCHBAR_LAUNCHCTL:-/bin/launchctl}"

VENV_COMMAND="$INSTALL_ROOT/venv/bin/codexbar-touchbar"
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.plist"
RENDERER_LABEL=com.vdustr.codexbar-touchbar.renderer
RENDERER_PLIST="$HOME/Library/LaunchAgents/$RENDERER_LABEL.plist"
RENDERER_APP="$INSTALL_ROOT/Agent Touch Bar.app"

if ! renderer_output=$("$LAUNCHCTL" bootout "gui/$(id -u)/$RENDERER_LABEL" 2>&1); then
  case "$renderer_output" in
    *"Could not find service"*|*"Could not find specified service"*|*"No such process"*) ;;
    *) echo "$renderer_output" >&2; exit 1 ;;
  esac
fi
rm -f "$RENDERER_PLIST"
rm -rf "$RENDERER_APP"

if [ -x "$COMMAND" ]; then
  "$COMMAND" uninstall "$@"
elif [ -x "$VENV_COMMAND" ]; then
  "$VENV_COMMAND" uninstall "$@"
else
  if ! bootout_output=$("$LAUNCHCTL" bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar" 2>&1); then
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
"$REPO_ROOT/scripts/remove-legacy-btt.sh"
rm -f "$COMMAND"
rm -rf "$INSTALL_ROOT/venv"
rm -rf "$INSTALL_ROOT/venv.rollback"
rm -rf "$INSTALL_ROOT/Agent Touch Bar.app.rollback"
rm -f "$INSTALL_ROOT/renderer.plist.rollback"
rm -f "$INSTALL_ROOT/install-transaction.committed"

echo "Removed the bridge, native renderer, command, and legacy BetterTouchTool widgets."
echo "Runtime logs and extracted icons remain at: $DATA_DIR"
