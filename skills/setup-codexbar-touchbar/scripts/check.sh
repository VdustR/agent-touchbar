#!/bin/bash
set -euo pipefail

missing=0
CODEXBAR_BIN=${CODEXBAR_TOUCHBAR_CODEXBAR:-}
if [ -z "$CODEXBAR_BIN" ]; then CODEXBAR_BIN=$(command -v codexbar || true); fi
PYTHON_BIN=${CODEXBAR_TOUCHBAR_PYTHON:-}
if [ -z "$PYTHON_BIN" ]; then PYTHON_BIN=$(command -v python3 || true); fi

if [ -x "$CODEXBAR_BIN" ]; then
  printf 'ok: codexbar (%s)\n' "$CODEXBAR_BIN"
else
  printf 'missing: codexbar\n'
  missing=1
fi

if [ -x "$PYTHON_BIN" ]; then
  printf 'ok: python3 (%s)\n' "$PYTHON_BIN"
else
  printf 'missing: python3\n'
  missing=1
fi

BTTCLI=${CODEXBAR_TOUCHBAR_BTTCLI:-/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli}
if [ -x "$BTTCLI" ]; then
  printf 'ok: BetterTouchTool CLI (%s)\n' "$BTTCLI"
else
  printf 'missing: BetterTouchTool CLI\n'
  missing=1
fi

if [ -x "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" -c 'import sys; print("python:", sys.version.split()[0]); raise SystemExit(sys.version_info < (3, 11))' || missing=1
fi
exit "$missing"
