#!/bin/bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
INSTALL_ROOT="${AGENT_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/AgentTouchBar}"
VENV="$INSTALL_ROOT/venv"
VENV_BACKUP="$INSTALL_ROOT/venv.rollback"
APP_PATH="${AGENT_TOUCHBAR_APP_PATH:-$HOME/Applications/Agent Touch Bar.app}"
APP_BACKUP="$INSTALL_ROOT/Agent Touch Bar.app.rollback"
OLD_APP_PATH="$INSTALL_ROOT/Agent Touch Bar.app"
BRIDGE_PLIST="$HOME/Library/LaunchAgents/com.vdustr.agent-touchbar.plist"
RENDERER_PLIST="$HOME/Library/LaunchAgents/com.vdustr.agent-touchbar.renderer.plist"
RENDERER_PLIST_BACKUP="$INSTALL_ROOT/renderer.plist.rollback"
COMMIT_MARKER="$INSTALL_ROOT/install-transaction.committed"
BIN_DIR="${AGENT_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
LEGACY_INSTALL_ROOT="$HOME/Library/Application Support/CodexBarTouchBar"
LEGACY_BRIDGE_PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.plist"
LEGACY_RENDERER_PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.renderer.plist"
LEGACY_COMMAND="$BIN_DIR/codexbar-touchbar"
HAD_VENV=0
HAD_APP=0
HAD_RENDERER_PLIST=0
HAD_LEGACY_BRIDGE=0
HAD_LEGACY_RENDERER=0

if OPEN_AT_LOGIN_VALUE=$(/usr/bin/defaults read com.vdustr.agent-touchbar.renderer openAtLogin 2>/dev/null); then
  case "$OPEN_AT_LOGIN_VALUE" in
    0|false|FALSE) OPEN_AT_LOGIN=0 ;;
    *) OPEN_AT_LOGIN=1 ;;
  esac
else
  OPEN_AT_LOGIN=1
fi
export AGENT_TOUCHBAR_OPEN_AT_LOGIN="$OPEN_AT_LOGIN"
export AGENT_TOUCHBAR_APP_PATH="$APP_PATH"

legacy_service_loaded() {
  /bin/launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1
}

migrate_legacy_install() {
  if [ ! -d "$LEGACY_INSTALL_ROOT" ]; then return; fi
  mkdir -p "$INSTALL_ROOT"
  for directory in icons logs; do
    if [ -d "$LEGACY_INSTALL_ROOT/$directory" ] && [ ! -e "$INSTALL_ROOT/$directory" ]; then
      /usr/bin/ditto "$LEGACY_INSTALL_ROOT/$directory" "$INSTALL_ROOT/$directory"
    fi
  done
  if ! /usr/bin/defaults read com.vdustr.agent-touchbar.renderer >/dev/null 2>&1 \
    && /usr/bin/defaults export com.vdustr.codexbar-touchbar.renderer "$INSTALL_ROOT/legacy-renderer-defaults.plist" >/dev/null 2>&1; then
    /usr/bin/defaults import com.vdustr.agent-touchbar.renderer "$INSTALL_ROOT/legacy-renderer-defaults.plist" >/dev/null
    legacy_icon_path=$(/usr/bin/defaults read com.vdustr.agent-touchbar.renderer launcherIconPath 2>/dev/null || true)
    case "$legacy_icon_path" in
      "$LEGACY_INSTALL_ROOT"/*)
        /usr/bin/defaults write com.vdustr.agent-touchbar.renderer launcherIconPath \
          -string "$INSTALL_ROOT/${legacy_icon_path#"$LEGACY_INSTALL_ROOT"/}"
        ;;
    esac
  fi
  rm -f "$INSTALL_ROOT/legacy-renderer-defaults.plist"
}

stop_legacy_services() {
  if legacy_service_loaded com.vdustr.codexbar-touchbar; then HAD_LEGACY_BRIDGE=1; fi
  if legacy_service_loaded com.vdustr.codexbar-touchbar.renderer; then HAD_LEGACY_RENDERER=1; fi
  /bin/launchctl bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar" >/dev/null 2>&1 || true
  /bin/launchctl bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar.renderer" >/dev/null 2>&1 || true
}

restore_legacy_services() {
  if [ "$HAD_LEGACY_BRIDGE" -eq 1 ] && [ -f "$LEGACY_BRIDGE_PLIST" ]; then
    /bin/launchctl bootstrap "gui/$(id -u)" "$LEGACY_BRIDGE_PLIST"
  fi
  if [ "$HAD_LEGACY_RENDERER" -eq 1 ] && [ -f "$LEGACY_RENDERER_PLIST" ]; then
    /bin/launchctl bootstrap "gui/$(id -u)" "$LEGACY_RENDERER_PLIST"
  fi
}

rollback_install() {
  failure_status=$?
  if [ -n "${1:-}" ]; then failure_status=$1; fi
  trap - ERR INT TERM HUP
  set +e
  if [ -f "$COMMIT_MARKER" ]; then exit "$failure_status"; fi
  /bin/launchctl bootout "gui/$(id -u)/com.vdustr.agent-touchbar" >/dev/null 2>&1
  /bin/launchctl bootout "gui/$(id -u)/com.vdustr.agent-touchbar.renderer" >/dev/null 2>&1
  if [ -d "$VENV_BACKUP" ]; then
    rm -rf "$VENV"
    mv "$VENV_BACKUP" "$VENV"
  elif [ "$HAD_VENV" -eq 0 ]; then
    rm -rf "$VENV"
  fi
  if [ -d "$APP_BACKUP" ]; then
    rm -rf "$APP_PATH"
    mv "$APP_BACKUP" "$APP_PATH"
  elif [ "$HAD_APP" -eq 0 ]; then
    rm -rf "$APP_PATH"
  fi
  if [ -f "$RENDERER_PLIST_BACKUP" ]; then
    rm -f "$RENDERER_PLIST"
    mv "$RENDERER_PLIST_BACKUP" "$RENDERER_PLIST"
  elif [ "$HAD_RENDERER_PLIST" -eq 0 ]; then
    rm -f "$RENDERER_PLIST"
  fi
  if [ -f "$RENDERER_PLIST" ]; then
    /bin/launchctl bootstrap "gui/$(id -u)" "$RENDERER_PLIST"
    /bin/launchctl kickstart "gui/$(id -u)/com.vdustr.agent-touchbar.renderer"
  fi
  if [ "$HAD_VENV" -eq 1 ] && [ -x "$VENV/bin/agent-touchbar" ]; then
    ln -sfn "$VENV/bin/agent-touchbar" "$BIN_DIR/agent-touchbar"
    if AGENT_TOUCHBAR_DATA_DIR="${AGENT_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" \
      "$BIN_DIR/agent-touchbar" install; then
      echo "Installation failed; restored the previous installation." >&2
    else
      echo "Installation failed, and the previous bridge could not be restarted." >&2
    fi
  else
    rm -f "$BIN_DIR/agent-touchbar" "$BRIDGE_PLIST"
  fi
  restore_legacy_services
  exit "$failure_status"
}

if [ -n "${AGENT_TOUCHBAR_CODEXBAR:-}" ]; then
  if [ ! -x "$AGENT_TOUCHBAR_CODEXBAR" ]; then
    echo "AGENT_TOUCHBAR_CODEXBAR must point to an executable." >&2
    exit 1
  fi
elif ! command -v codexbar >/dev/null 2>&1; then
  echo "codexbar is required: https://github.com/steipete/CodexBar" >&2
  exit 1
fi
if ! command -v swift >/dev/null 2>&1; then
  echo "Swift is required to build the native Touch Bar host." >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
if [ -f "$COMMIT_MARKER" ]; then
  rm -rf "$VENV_BACKUP" "$APP_BACKUP"
  rm -f "$RENDERER_PLIST_BACKUP" "$COMMIT_MARKER"
elif [ -d "$VENV_BACKUP" ]; then
  rm -rf "$VENV"
  mv "$VENV_BACKUP" "$VENV"
fi
if [ -d "$APP_BACKUP" ]; then
  rm -rf "$APP_PATH"
  mv "$APP_BACKUP" "$APP_PATH"
fi
if [ -f "$RENDERER_PLIST_BACKUP" ]; then
  rm -f "$RENDERER_PLIST"
  mv "$RENDERER_PLIST_BACKUP" "$RENDERER_PLIST"
fi

if [ -n "${AGENT_TOUCHBAR_PYTHON:-}" ]; then
  PYTHON_BIN=$AGENT_TOUCHBAR_PYTHON
elif PYTHON_BIN=$(command -v python3); then
  :
else
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi
"$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
  echo "Python 3.11 or newer is required." >&2
  exit 1
}
PYTHON_BIN=$("$PYTHON_BIN" -c 'import sys; print(sys.executable)')

trap rollback_install ERR
trap 'rollback_install 130' INT
trap 'rollback_install 143' TERM
trap 'rollback_install 129' HUP
migrate_legacy_install
stop_legacy_services
if [ -d "$VENV" ]; then
  HAD_VENV=1
  mv "$VENV" "$VENV_BACKUP"
  case "$PYTHON_BIN" in
    "$VENV"/*) PYTHON_BIN="$VENV_BACKUP/${PYTHON_BIN#"$VENV"/}" ;;
  esac
fi
if [ -d "$APP_PATH" ]; then
  HAD_APP=1
  mv "$APP_PATH" "$APP_BACKUP"
fi
if [ -f "$RENDERER_PLIST" ]; then
  HAD_RENDERER_PLIST=1
  mv "$RENDERER_PLIST" "$RENDERER_PLIST_BACKUP"
fi
"$REPO_ROOT/scripts/install-renderer.sh"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade "$REPO_ROOT"
ln -sfn "$VENV/bin/agent-touchbar" "$BIN_DIR/agent-touchbar"
AGENT_TOUCHBAR_DATA_DIR="${AGENT_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" "$BIN_DIR/agent-touchbar" install "$@"
AGENT_TOUCHBAR_DATA_DIR="${AGENT_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" \
  "$BIN_DIR/agent-touchbar" doctor --installation-only
: >"$COMMIT_MARKER"
trap - ERR INT TERM HUP
rm -rf "$VENV_BACKUP" "$APP_BACKUP"
rm -f "$RENDERER_PLIST_BACKUP" "$COMMIT_MARKER"
rm -f "$LEGACY_COMMAND" "$LEGACY_BRIDGE_PLIST" "$LEGACY_RENDERER_PLIST"
rm -rf "$LEGACY_INSTALL_ROOT"
if [ "$OLD_APP_PATH" != "$APP_PATH" ]; then rm -rf "$OLD_APP_PATH"; fi

echo "Installed agent-touchbar at $BIN_DIR/agent-touchbar"
