#!/bin/bash
set -euo pipefail

BTTCLI=${AGENT_TOUCHBAR_BTTCLI:-$(command -v bttcli || true)}
if [ -z "$BTTCLI" ]; then
  BTTCLI=/Applications/BetterTouchTool.app/Contents/SharedSupport/bin/bttcli
fi
if [ ! -x "$BTTCLI" ]; then
  echo "No BetterTouchTool CLI found; no legacy widgets to remove."
  exit 0
fi

PYTHON_BIN=${AGENT_TOUCHBAR_PYTHON:-$(command -v python3 || true)}
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python is required to identify legacy widget IDs." >&2
  exit 1
fi

"$PYTHON_BIN" - "$BTTCLI" <<'PY'
import subprocess
import sys
import uuid

namespace = uuid.UUID("f4a5b457-924c-49bc-a878-86034bd43261")
names = ["Codex usage", "Claude usage", "Antigravity usage", "Attention session", "Agent usage"]
names.extend(f"Agent session {index}" for index in range(1, 13))
trigger_ids = [str(uuid.uuid5(namespace, name)).upper() for name in names]
trigger_ids.append("E4F85058-56B7-4DBD-9064-3C26F11B8C52")
for trigger_id in trigger_ids:
    subprocess.run(
        [sys.argv[1], "delete_trigger", f"uuid={trigger_id}"],
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=5,
    )
PY
echo "Removed legacy BetterTouchTool widgets."
