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
5. Ask the user to tap one quota widget and one session widget because software
   checks cannot prove physical Touch Bar input.

CodexBar is the source of truth. Display only states and quota windows it
returns. Do not infer approval, error, completion, or attention states from
idle time.

## Uninstall

Run `./scripts/uninstall.sh`. It removes the LaunchAgent, command symlink, and
managed BetterTouchTool widgets. It intentionally retains runtime logs and
extracted icons and prints their location so removal remains recoverable.
