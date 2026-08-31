#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${CODEXBAR_TOUCHBAR_INSTALL_ROOT:-$HOME/Library/Application Support/CodexBarTouchBar}"
BIN_DIR="${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}"
COMMAND="$BIN_DIR/codexbar-touchbar"

if [ -x "$COMMAND" ]; then
  "$COMMAND" uninstall "$@"
fi
rm -f "$COMMAND"

echo "Removed the service, command, and BetterTouchTool widgets."
echo "Runtime logs and extracted icons remain at: $INSTALL_ROOT"
