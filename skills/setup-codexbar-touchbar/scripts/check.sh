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

SWIFT_BIN=$(command -v swift || true)
if [ -x "$SWIFT_BIN" ]; then
  SWIFT_VERSION=$("$SWIFT_BIN" --version | awk '{ for (i = 1; i <= NF; i++) if ($i == "version") { print $(i + 1); exit } }')
  SWIFT_MAJOR=${SWIFT_VERSION%%.*}
  SWIFT_REMAINDER=${SWIFT_VERSION#*.}
  SWIFT_MINOR=${SWIFT_REMAINDER%%.*}
  if [ -n "$SWIFT_VERSION" ] && { [ "$SWIFT_MAJOR" -gt 5 ] || { [ "$SWIFT_MAJOR" -eq 5 ] && [ "$SWIFT_MINOR" -ge 10 ]; }; }; then
    printf 'ok: swift %s (%s)\n' "$SWIFT_VERSION" "$SWIFT_BIN"
  else
    printf 'missing: swift 5.10 or newer (found %s)\n' "${SWIFT_VERSION:-unknown}"
    missing=1
  fi
else
  printf 'missing: swift\n'
  missing=1
fi

if [ -x "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" -c 'import sys; print("python:", sys.version.split()[0]); raise SystemExit(sys.version_info < (3, 11))' || missing=1
fi
exit "$missing"
