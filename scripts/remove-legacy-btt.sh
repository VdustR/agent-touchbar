#!/bin/bash
set -euo pipefail

BTTCLI=${CODEXBAR_TOUCHBAR_BTTCLI:-$(command -v bttcli || true)}
if [ -z "$BTTCLI" ]; then
  BTTCLI=/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli
fi
if [ ! -x "$BTTCLI" ]; then
  echo "No BetterTouchTool CLI found; no legacy widgets to remove."
  exit 0
fi

PYTHON_BIN=${CODEXBAR_TOUCHBAR_PYTHON:-$(command -v python3 || true)}
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python is required to identify legacy widget IDs." >&2
  exit 1
fi

trigger_file=$(mktemp)
trap 'rm -f "$trigger_file"' EXIT
"$PYTHON_BIN" - >"$trigger_file" <<'PY'
import uuid

namespace = uuid.UUID("f4a5b457-924c-49bc-a878-86034bd43261")
names = ["Codex usage", "Claude usage", "Antigravity usage", "Attention session", "Agent usage"]
names.extend(f"Agent session {index}" for index in range(1, 13))
for name in names:
    print(str(uuid.uuid5(namespace, name)).upper())
print("E4F85058-56B7-4DBD-9064-3C26F11B8C52")
PY

while IFS= read -r trigger_id; do
  "$BTTCLI" delete_trigger "uuid=$trigger_id" >/dev/null
done < "$trigger_file"
echo "Removed legacy BetterTouchTool widgets."
