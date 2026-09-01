# CodexBar Touch Bar

CodexBar Touch Bar adds Codex Desktop tasks and coding-agent usage limits to the
macOS Touch Bar with an open-source native Swift host. BetterTouchTool is not
required.

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
scripted action verification.

## Capability sources

| Provider | Task list | Exact task focus | Quota and reset |
| --- | --- | --- | --- |
| Codex | Codex Desktop state | Codex Desktop deeplink | CodexBar adapter |
| Claude | Not exposed | Not exposed | CodexBar adapter |
| Antigravity | Not exposed | Not exposed | CodexBar adapter |

Missing capabilities are omitted rather than simulated. A future native quota
adapter can replace CodexBar without changing the task or Touch Bar layers.

## Requirements

- macOS 13 or newer with a Touch Bar
- [CodexBar](https://github.com/steipete/CodexBar)
- Python 3.11 or newer
- Swift 5.10 or newer

The native host uses a runtime-detected private macOS Touch Bar API for the
global Control Strip item and system modal. Unsupported systems retain the menu
bar status item but cannot provide the global Touch Bar surface.

## Install

```bash
git clone https://github.com/VdustR/codexbar-touchbar.git
cd codexbar-touchbar
./scripts/install.sh
```

The installer creates an isolated Python environment and native app under
`~/Library/Application Support/CodexBarTouchBar` and installs separate per-user
LaunchAgents for the local bridge and renderer. Icons are loaded at runtime from
the installed desktop applications and are never redistributed.

Verify the installation:

```bash
~/.local/bin/codexbar-touchbar doctor
curl --fail http://127.0.0.1:4317/healthz
```

### Typography

The renderer uses the macOS system font at 11 pt by default. Set any installed
font family or PostScript name through the renderer's user defaults, then wait
up to one second for the Touch Bar to refresh:

```bash
defaults write com.vdustr.codexbar-touchbar.renderer fontName -string "Your Font Family"
defaults write com.vdustr.codexbar-touchbar.renderer fontSize -float 11
```

Supported sizes are 8–18 pt. An unavailable font or out-of-range size falls
back to the default system typography. Restore both defaults with:

```bash
defaults delete com.vdustr.codexbar-touchbar.renderer fontName
defaults delete com.vdustr.codexbar-touchbar.renderer fontSize
```

### Launcher appearance

The Control Strip launcher defaults to a compact `terminal.fill` SF Symbol on
the system indigo background. Choose `icon`, `text`, or `iconAndText`, and set
an installed SF Symbol or local PNG, PDF, TIFF, or ICNS file, a label of up to
12 characters, and a six-digit RGB background color. A local icon takes
precedence over the SF Symbol and is rendered as a monochrome template:

```bash
defaults write com.vdustr.codexbar-touchbar.renderer launcherContent -string "iconAndText"
defaults write com.vdustr.codexbar-touchbar.renderer launcherSymbol -string "terminal.fill"
defaults write com.vdustr.codexbar-touchbar.renderer launcherIconPath -string "$HOME/Pictures/agent-icon.png"
defaults write com.vdustr.codexbar-touchbar.renderer launcherText -string "Agents"
defaults write com.vdustr.codexbar-touchbar.renderer launcherColor -string "#4F46E5"
```

Changes refresh within one second. Invalid values fall back to the compact
terminal icon and system indigo. Delete any key above to restore its default.

To update, pull the latest `main` branch and run `./scripts/install.sh` again.

## Uninstall

```bash
./scripts/uninstall.sh
```

The uninstaller removes the native app and both LaunchAgents. It also removes
legacy widgets created by older BetterTouchTool-based versions when the BTT CLI
is available. Logs remain in the data directory for diagnosis.

## Agent setup skill

The repository includes `skills/setup-codexbar-touchbar`. Ask Codex to use that
skill from this repository to install, update, diagnose, or uninstall the
integration with the required readback checks.

## Security

The bridge binds only to loopback. Task focus validates the requested ID
against the current Codex Desktop task registry, and provider focus accepts
only the three configured providers. The renderer endpoint omits
transcript paths and account metadata.

## License

[MIT](LICENSE)
