#!/bin/bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
INSTALL_ROOT="${CODEXBAR_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/CodexBarTouchBar}"
VENV="$INSTALL_ROOT/venv"
BIN_DIR="${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"

if ! command -v codexbar >/dev/null 2>&1; then
  echo "codexbar is required: https://github.com/steipete/CodexBar" >&2
  exit 1
fi
if [ ! -x /Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli ]; then
  echo "BetterTouchTool with its CLI is required." >&2
  exit 1
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

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade "$REPO_ROOT"
ln -sfn "$VENV/bin/codexbar-touchbar" "$BIN_DIR/codexbar-touchbar"
CODEXBAR_TOUCHBAR_DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" "$BIN_DIR/codexbar-touchbar" install "$@"
CODEXBAR_TOUCHBAR_DATA_DIR="${CODEXBAR_TOUCHBAR_DATA_DIR:-$INSTALL_ROOT}" "$BIN_DIR/codexbar-touchbar" doctor

echo "Installed codexbar-touchbar at $BIN_DIR/codexbar-touchbar"
