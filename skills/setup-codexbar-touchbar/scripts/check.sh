#!/bin/bash
set -euo pipefail

missing=0
for command_name in codexbar python3; do
  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'ok: %s (%s)\n' "$command_name" "$(command -v "$command_name")"
  else
    printf 'missing: %s\n' "$command_name"
    missing=1
  fi
done

BTTCLI=/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli
if [ -x "$BTTCLI" ]; then
  printf 'ok: BetterTouchTool CLI (%s)\n' "$BTTCLI"
else
  printf 'missing: BetterTouchTool CLI\n'
  missing=1
fi

python3 -c 'import sys; print("python:", sys.version.split()[0]); raise SystemExit(sys.version_info < (3, 11))' || missing=1
exit "$missing"
