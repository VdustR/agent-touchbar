#!/bin/bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
INSTALL_ROOT="${AGENT_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/AgentTouchBar}"
APP_PATH="$INSTALL_ROOT/Agent Touch Bar.app"
LABEL=com.vdustr.agent-touchbar.renderer
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$INSTALL_ROOT/logs"

mkdir -p "$INSTALL_ROOT" "$LOG_DIR" "$(dirname "$PLIST")"
"$REPO_ROOT/native/build-app.sh" "$APP_PATH"

/usr/bin/plutil -create xml1 "$PLIST"
/usr/bin/plutil -insert Label -string "$LABEL" "$PLIST"
/usr/bin/plutil -insert ProgramArguments -json "[\"$APP_PATH/Contents/MacOS/agent-touchbar-host\"]" "$PLIST"
/usr/bin/plutil -insert RunAtLoad -bool true "$PLIST"
/usr/bin/plutil -insert KeepAlive -bool true "$PLIST"
/usr/bin/plutil -insert ProcessType -string Interactive "$PLIST"
/usr/bin/plutil -insert StandardOutPath -string "$LOG_DIR/renderer-stdout.log" "$PLIST"
/usr/bin/plutil -insert StandardErrorPath -string "$LOG_DIR/renderer-stderr.log" "$PLIST"

if ! bootout_output=$(/bin/launchctl bootout "gui/$(id -u)/$LABEL" 2>&1); then
  case "$bootout_output" in
    *"Could not find service"*|*"Could not find specified service"*|*"No such process"*) ;;
    *) echo "$bootout_output" >&2; exit 1 ;;
  esac
fi
/bin/launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Installed native renderer at $APP_PATH"
