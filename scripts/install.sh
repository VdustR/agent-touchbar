#!/bin/bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
INSTALL_ROOT="${CODEXBAR_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/CodexBarTouchBar}"
VENV="$INSTALL_ROOT/venv"
VENV_BACKUP="$INSTALL_ROOT/venv.rollback"
APP_PATH="$INSTALL_ROOT/Agent Touch Bar.app"
APP_BACKUP="$INSTALL_ROOT/Agent Touch Bar.app.rollback"
BRIDGE_PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.plist"
RENDERER_PLIST="$HOME/Library/LaunchAgents/com.vdustr.codexbar-touchbar.renderer.plist"
RENDERER_PLIST_BACKUP="$INSTALL_ROOT/renderer.plist.rollback"
BIN_DIR="${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
HAD_VENV=0
HAD_APP=0
HAD_RENDERER_PLIST=0

rollback_install() {
  failure_status=$?
  if [ -n "${1:-}" ]; then failure_status=$1; fi
  trap - ERR INT TERM HUP
  set +e
  /bin/launchctl bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar" >/dev/null 2>&1
  /bin/launchctl bootout "gui/$(id -u)/com.vdustr.codexbar-touchbar.renderer" >/dev/null 2>&1
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
  fi
  if [ "$HAD_VENV" -eq 1 ] && [ -x "$VENV/bin/codexbar-touchbar" ]; then
    ln -sfn "$VENV/bin/codexbar-touchbar" "$BIN_DIR/codexbar-touchbar"
    if CODEXBAR_TOUCHBAR_DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" \
      "$BIN_DIR/codexbar-touchbar" install; then
      echo "Installation failed; restored the previous installation." >&2
    else
      echo "Installation failed, and the previous bridge could not be restarted." >&2
    fi
  else
    rm -f "$BIN_DIR/codexbar-touchbar" "$BRIDGE_PLIST"
  fi
  exit "$failure_status"
}

if [ -n "${CODEXBAR_TOUCHBAR_CODEXBAR:-}" ]; then
  if [ ! -x "$CODEXBAR_TOUCHBAR_CODEXBAR" ]; then
    echo "CODEXBAR_TOUCHBAR_CODEXBAR must point to an executable." >&2
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
if [ -d "$VENV_BACKUP" ]; then
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

if [ -n "${CODEXBAR_TOUCHBAR_PYTHON:-}" ]; then
  PYTHON_BIN=$CODEXBAR_TOUCHBAR_PYTHON
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
ln -sfn "$VENV/bin/codexbar-touchbar" "$BIN_DIR/codexbar-touchbar"
CODEXBAR_TOUCHBAR_DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" "$BIN_DIR/codexbar-touchbar" install "$@"
CODEXBAR_TOUCHBAR_DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" "$BIN_DIR/codexbar-touchbar" doctor
trap - ERR INT TERM HUP
rm -rf "$VENV_BACKUP" "$APP_BACKUP"
rm -f "$RENDERER_PLIST_BACKUP"
"$REPO_ROOT/scripts/remove-legacy-btt.sh"

echo "Installed codexbar-touchbar at $BIN_DIR/codexbar-touchbar"
