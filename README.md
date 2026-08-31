# CodexBar Touch Bar

CodexBar Touch Bar adds live coding-agent sessions and provider usage limits to
the macOS Touch Bar through BetterTouchTool.

It uses CodexBar for provider usage and the session states CodexBar exposes.
Claude desktop titles are joined from Claude's local session metadata, and
Antigravity contributes an app-presence item because it does not expose a
trustworthy desktop session list. The integration does not read transcript
contents, browser cookies, credentials, or account identifiers.

## Display model

The Touch Bar is ordered as follows:

1. Sessions explicitly reported as needing attention.
2. Codex, Claude, and Antigravity usage limits.
3. Active desktop sessions, most recently active first.
4. Antigravity app presence, then idle desktop sessions, newest first.

Only windows returned by CodexBar are displayed. For example, an account with
only a seven-day Codex window does not receive a synthetic five-hour window.
Usage buttons also append nonzero `active` and `idle` session counts when
CodexBar reports sessions for that provider. A missing session source is left
blank rather than displayed as zero.
Session state is limited to values reported by CodexBar; approval or error
states are not inferred from inactivity.

Codex session discovery, state, and focus follow CodexBar metadata. Claude
desktop sessions use CodexBar identity and state plus the matching local Claude
title. Antigravity is displayed as `available` only while its desktop app is
running; this is intentionally app presence rather than a fabricated session.
CLI sessions are excluded because their short terminal titles are not useful
Touch Bar labels and cannot navigate to a desktop conversation.
Project-name fallbacks are prefixed with `⌁` so they are not presented as
conversation titles.

Tapping a usage item opens or focuses its desktop application. Tapping a Codex
desktop session opens its exact `codex://threads/<id>` deep link. Claude asks
CodexBar to focus the matching session and falls back to opening Claude;
Antigravity focuses its app because no reliable session deep link is available.

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
installs three quota widgets plus up to four dynamic session widgets. Empty
session slots are removed. It does not redistribute application icons.

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

The bridge binds only to loopback. Session focus validates the requested ID
against a fresh CodexBar session list, and provider focus accepts only the three
configured providers. The compact BetterTouchTool endpoint omits transcript
paths and account metadata.

## License

[MIT](LICENSE)
