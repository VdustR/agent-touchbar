---
name: setup-agent-touchbar
description: Build, install, update, diagnose, or uninstall the source-only native Agent Touch Bar integration on macOS.
---

# Set Up Agent Touch Bar

Operate from the repository root on macOS. The integration requires CodexBar,
Swift 5.10, and Python 3.11 or newer.

## Install or update

1. Confirm the checkout contains source code. Do not download or substitute a
   prebuilt app or executable.
2. Run `skills/setup-agent-touchbar/scripts/check.sh` and report missing
   prerequisites before making changes.
3. Run `./scripts/install.sh`. This builds the native Swift app from the current
   checkout, creates an isolated Python environment, and installs both under
   `~/Library/Application Support/AgentTouchBar`, with the launchable app at
   `~/Applications/Agent Touch Bar.app`.
4. Run `${AGENT_TOUCHBAR_BIN_DIR:-$HOME/.local/bin}/agent-touchbar doctor`.
5. Verify `http://127.0.0.1:4317/healthz` and inspect one
   `http://127.0.0.1:4317/api/v1/state` response. Do not print transcripts,
   credentials, cookies, or account identifiers.
6. Compare visible session names in Codex, Claude Desktop, and Antigravity with
   `/api/v1/state`. Every displayed title must match its desktop UI exactly;
   omit records that only expose a path, worktree, project, or internal ID.
7. Capture the physical Touch Bar with `screencapture -b` while the test-only
   auto-present flag is active. Confirm items stay on one line and both scroll
   boundaries remain clear of the system controls.
8. Execute one quota action and one task action, verify `healthz.lastAction`,
   and confirm the target desktop app or exact Codex task becomes visible.
9. When a physical Touch Bar is available, verify one quota tap and one task
   tap. Report physical input separately from scripted action verification.

Codex Desktop state is authoritative for Codex titles and exact focus. Claude
Desktop titles are joined to CodexBar runtime IDs. Antigravity titles come from
its visible local sidebar. CodexBar is isolated to quota windows and runtime
enrichment. Claude and Antigravity task actions focus their app when no verified
exact-session link exists. Display only states and quota windows that a source
returns. Do not infer approval, error, completion, or attention from idle time.

## Uninstall

Run `./scripts/uninstall.sh`. It removes both LaunchAgents, the native app, the
command symlink, and the isolated Python environment. It retains runtime logs
and reports their location.
