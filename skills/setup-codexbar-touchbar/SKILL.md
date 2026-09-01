---
name: setup-codexbar-touchbar
description: Install, update, diagnose, or uninstall the native CodexBar Touch Bar integration on macOS.
---

# Set Up CodexBar Touch Bar

Operate from the repository root on macOS. The integration requires CodexBar,
Swift 5.10, and Python 3.11 or newer. It does not require BetterTouchTool.

## Install or update

1. Run `skills/setup-codexbar-touchbar/scripts/check.sh` and report missing
   prerequisites before making changes.
2. Run `./scripts/install.sh`. This creates an isolated Python environment and
   native Swift app in `~/Library/Application Support/CodexBarTouchBar` and
   installs the bridge and renderer LaunchAgents.
3. Run `${CODEXBAR_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}/codexbar-touchbar doctor`.
4. Verify `http://127.0.0.1:4317/healthz` and inspect one
   `http://127.0.0.1:4317/api/v1/state` response. Do not print transcripts,
   credentials, cookies, or account identifiers.
5. Compare visible, unarchived Codex Desktop tasks with `/api/v1/state`. Confirm the
   task IDs and titles match and no Claude, Antigravity, CLI, review, or
   subagent records appear as task buttons.
6. Run the native binary with `--self-test`, then capture the physical Touch Bar
   with `screencapture -b` while the test-only auto-present flag is active.
7. Execute one quota action and one task action, verify `healthz.lastAction`,
   and confirm the target desktop app or exact Codex task becomes visible.
8. When a physical Touch Bar is available, verify one quota tap and one task
   tap. Report physical input separately from scripted action verification.

Codex Desktop state is the task-list source. CodexBar is isolated to quota
windows and the active-state overlay. Claude and Antigravity do not appear as
task buttons; their quota buttons open the corresponding apps. Display only
states and quota windows that a source returns. Do not infer approval, error,
completion, or attention states from idle time.

## Uninstall

Run `./scripts/uninstall.sh`. It removes both LaunchAgents, the native app, the
command symlink, and any legacy managed BetterTouchTool widgets. It retains
runtime logs and reports their location.
