---
name: setup-codexbar-touchbar
description: Install, update, diagnose, or uninstall CodexBar Touch Bar on macOS. Use when configuring the BetterTouchTool widgets, local bridge, app icons, or launch service for this repository.
---

# Set Up CodexBar Touch Bar

Operate from the repository root on macOS. The integration requires CodexBar,
BetterTouchTool, and Python 3.11 or newer. Do not install or purchase missing
third-party applications without explicit user authorization.

## Install or update

1. Run `skills/setup-codexbar-touchbar/scripts/check.sh` and report missing
   prerequisites before making changes.
2. Run `./scripts/install.sh`. This creates an isolated virtual environment in
   `~/Library/Application Support/CodexBarTouchBar`, installs or updates the
   LaunchAgent, extracts icons from installed desktop applications, and
   upserts the BetterTouchTool widgets.
3. Run `${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}/codexbar-touchbar doctor`.
4. Verify `http://127.0.0.1:4317/healthz` and inspect one
   `http://127.0.0.1:4317/api/btt` response. Do not print transcripts,
   credentials, cookies, or account identifiers.
5. Inspect the managed triggers with BetterTouchTool CLI. Confirm every visible
   session is a `BTTTriggerTypeTouchBar` trigger with type `629`, a nonempty
   name, and a terminal action. Execute one stored quota action and one stored
   session action, then verify `healthz.lastAction.outcome` is `succeeded`.
6. When a physical Touch Bar is available, verify one quota tap and one session
   tap. Report physical input separately from scripted action verification.

CodexBar is the source of truth for quota windows and normalized session state.
Claude titles may be joined from its local desktop session metadata.
Antigravity app presence may be reported when its process is running, but do
not present it as a conversation. Display only states and quota windows that a
source returns. Do not infer approval, error, completion, or attention states
from idle time.

## Uninstall

Run `./scripts/uninstall.sh`. It removes the LaunchAgent, command symlink, and
managed BetterTouchTool widgets. It intentionally retains runtime logs and
extracted icons and prints their location so removal remains recoverable.
