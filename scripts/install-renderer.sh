#!/bin/bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
INSTALL_ROOT="${AGENT_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/AgentTouchBar}"
APP_PATH="${AGENT_TOUCHBAR_APP_PATH:-$HOME/Applications/Agent Touch Bar.app}"
OPEN_AT_LOGIN="${AGENT_TOUCHBAR_OPEN_AT_LOGIN:-1}"
LABEL=com.vdustr.agent-touchbar.renderer
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$INSTALL_ROOT/logs"

mkdir -p "$INSTALL_ROOT" "$LOG_DIR" "$(dirname "$PLIST")" "$(dirname "$APP_PATH")"
"$REPO_ROOT/native/build-app.sh" "$APP_PATH"

/usr/bin/plutil -create xml1 "$PLIST"
/usr/bin/plutil -insert Label -string "$LABEL" "$PLIST"
/usr/bin/plutil -insert ProgramArguments -json "[\"$APP_PATH/Contents/MacOS/agent-touchbar-host\"]" "$PLIST"
/usr/bin/plutil -insert RunAtLoad -bool "$OPEN_AT_LOGIN" "$PLIST"
/usr/bin/plutil -insert KeepAlive -json '{"SuccessfulExit":false}' "$PLIST"
/usr/bin/plutil -insert ProcessType -string Interactive "$PLIST"
/usr/bin/plutil -insert StandardOutPath -string "$LOG_DIR/renderer-stdout.log" "$PLIST"
/usr/bin/plutil -insert StandardErrorPath -string "$LOG_DIR/renderer-stderr.log" "$PLIST"

if ! bootout_output=$(/bin/launchctl bootout "gui/$(id -u)/$LABEL" 2>&1); then
  case "$bootout_output" in
    *"Could not find service"*|*"Could not find specified service"*|*"No such process"*) ;;
    *) echo "$bootout_output" >&2; exit 1 ;;
  esac
fi
unload_attempt=0
while /bin/launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; do
  unload_attempt=$((unload_attempt + 1))
  if [ "$unload_attempt" -ge 50 ]; then
    echo "Timed out waiting for the previous renderer LaunchAgent to unload." >&2
    exit 1
  fi
  sleep 0.1
done
/bin/launchctl bootstrap "gui/$(id -u)" "$PLIST"
/bin/launchctl kickstart "gui/$(id -u)/$LABEL"

echo "Installed native renderer at $APP_PATH"
