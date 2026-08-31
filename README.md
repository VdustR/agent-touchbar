# CodexBar Touch Bar

CodexBar Touch Bar adds Codex Desktop tasks and coding-agent usage limits to the
macOS Touch Bar through BetterTouchTool.

It reads the same local task registry used by Codex Desktop and overlays the
active runtime state reported by CodexBar. CodexBar remains isolated behind the
quota adapter for Codex, Claude, and Antigravity usage windows. The integration
does not read transcript contents, browser cookies, credentials, or account
identifiers.

## Display model

The Touch Bar is ordered as follows:

1. Tasks explicitly reported as needing attention, when a task source supports
   that state.
2. Codex, Claude, and Antigravity usage limits.
3. Active Codex tasks, most recently active first.
4. Idle Codex tasks, newest first.

Only windows returned by CodexBar are displayed. For example, an account with
only a seven-day Codex window does not receive a synthetic five-hour window.
Usage buttons also append nonzero `active` and `idle` session counts when
CodexBar reports sessions for that provider. A missing session source is left
blank rather than displayed as zero.
Tasks that are visible and unarchived in Codex Desktop are displayed. CodexBar
can promote a matching task to active; otherwise it is explicitly idle.
Approval, error, completion, and attention states are not inferred from
inactivity. The current Codex Desktop source exposes active and idle tasks, so
no attention row is displayed today; the ordering is reserved for a future
source that can report that state explicitly.

Only Codex tasks appear as session buttons. Claude and Antigravity remain quota
and app-launch controls because neither integration currently has a verified,
complete desktop task list and exact task focus contract. Internal exec,
review, subagent, archived, and CLI records are excluded.
Project-name fallbacks are prefixed with `⌁` so they are not presented as
conversation titles.

Tapping a usage item opens or focuses its desktop application. Tapping a Codex
task opens the exact `codex://threads/<id>` link produced by Codex Desktop's own
Copy deeplink command. Physical Touch Bar validation remains distinct from
scripted BTT dispatch.

## Capability sources

| Provider | Task list | Exact task focus | Quota and reset |
| --- | --- | --- | --- |
| Codex | Codex Desktop state | Codex Desktop deeplink | CodexBar adapter |
| Claude | Not exposed | Not exposed | CodexBar adapter |
| Antigravity | Not exposed | Not exposed | CodexBar adapter |

Missing capabilities are omitted rather than simulated. A future native quota
adapter can replace CodexBar without changing the task or Touch Bar layers.

## Requirements

- macOS with a Touch Bar or BetterTouchTool Touch Bar simulator
- [CodexBar](https://github.com/steipete/CodexBar)
- [BetterTouchTool](https://folivora.ai/)
- Python 3.11 or newer

Enable BetterTouchTool's Accessibility permission, Touch Bar support, and CLI
socket before installation.

## Install

```bash
git clone https://github.com/VdustR/codexbar-touchbar.git
cd codexbar-touchbar
./scripts/install.sh
```

The installer creates an isolated virtual environment under
`~/Library/Application Support/CodexBarTouchBar`, installs a per-user
LaunchAgent, extracts icons from locally installed desktop applications, and
installs three quota widgets plus up to four dynamic Codex task widgets. Empty
task slots are removed. It does not redistribute application icons.

Verify the installation:

```bash
~/.local/bin/codexbar-touchbar doctor
curl --fail http://127.0.0.1:4317/healthz
```

To update, pull the latest `main` branch and run `./scripts/install.sh` again.

## Uninstall

```bash
./scripts/uninstall.sh
```

The uninstaller retains logs and extracted icons and reports their location.

## Agent setup skill

The repository includes `skills/setup-codexbar-touchbar`. Ask Codex to use that
skill from this repository to install, update, diagnose, or uninstall the
integration with the required readback checks.

## Security

The bridge binds only to loopback. Task focus validates the requested ID
against the current Codex Desktop task registry, and provider focus accepts
only the three configured providers. The compact BetterTouchTool endpoint omits
transcript paths and account metadata.

## License

[MIT](LICENSE)
