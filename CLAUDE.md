# CLAUDE.md: Earmark

For an agent (or the maintainer, months later) picking this up with no memory
of how it was built. Read this first. Then read `docs/PLAN.md` (what's left
to build), `README.md` (what users see) and `branding/BRANDING.md` (the
name, logo and palette). The reasons below matter as much as the rules.

This file becomes public with the repo: no personal details, nothing about
Cody's work setup.

## Status (2026-11-20)

Identity done (name, logo, palette in `branding/`), development starting at
phase A of `docs/PLAN.md`. Nothing is built yet. The repo is private until
the `go-public` skill publishes it. Waiting on Cody: nothing.

## What Earmark is

A [Herdr](https://herdr.dev) plugin that keeps an archive of closed
coding-agent sessions per Herdr workspace. When a tab or pane running an
agent (Claude Code first; Codex, Pi and the other agents Herdr reports
sessions for) is closed, Earmark files that session under the workspace it
came from. One key opens a popup listing the current workspace's archive:
each session's title and when it was last active. Enter (or a double-click)
reopens it in a new tab in that workspace with the agent's resume command;
Delete (or a click on its ×) forgets it. The popup is fully usable with the
mouse.

It replaces the per-project "Archived" section of Forge, Cody's Windows
session manager (`cwilliams5/Forge`), where closing a session moved it to an
archive it could be reopened from. Herdr workspaces play the role of Forge's
projects and tabs the role of its sessions; without Earmark, a closed tab is
gone from Herdr, and the agent's own resume picker groups sessions by
folder, which doesn't separate workspaces that share one. Earmark does not
touch live sessions, does not manage the agents' transcripts, and does not
replace Herdr's own restore-after-restart.

Decided so far (details in `docs/PLAN.md`):
- **No right-click menu entry.** Herdr 0.9.5 has no documented way for a
  plugin to add items to its context menus (plugin UI is terminal panes and
  popups). Retest when Herdr changes; add one if it becomes possible.
- **The sidebar count is opt-in.** Earmark can report a workspace metadata
  token (`$earmark`, e.g. "3 archived"); it only shows if the user adds the
  token to their sidebar rows, and a setting turns the reporting off.
- **Cleanup:** `keep_days`, default 30, counted from a session's last
  activity (the clock Claude Code's own `cleanupPeriodDays` uses, default
  30). Before listing, Earmark checks that the agent's saved conversation
  still exists where it knows where to look, and drops entries that are
  gone, so a dead session is never offered.

## The people and the projects around it

- **Maintainer: Cody** (GitHub `cwilliams5`). Came to Linux from Windows and
  knows Windows deeply. Explain Linux things plainly, with Windows
  comparisons where they help. Cody reviews anything outward-facing
  (publishing, posting, filing upstream) before it happens, and writes any
  upstream bug report in his own words.
- **Sister projects:** Forge (`cwilliams5/Forge`, Windows, Electron), whose
  Archived section this reproduces. Cody's Omarchy tools (Transom, Sash,
  Locus, Latch) are unrelated in code; Earmark is not an Omarchy project.
- **On Cody's laptop:** the working copy is `~/Work/herdr-earmark`, linked
  into Herdr with `herdr plugin link`. Cody's dotfiles (`~/Work/dotfiles`,
  chezmoi; its CLAUDE.md has the rules) track Herdr's `config.toml`, where
  the key binding lives, and will list Earmark in
  `home/.chezmoidata/tools.yaml` once the plugin has a manifest.
- **Origin:** a new project, no spike. The review of existing Herdr plugins
  that led to building it is summarized under Credits.

## Identity

- Name: Earmark. Repo: `cwilliams5/herdr-earmark`.
- Ids:
  - Herdr plugin id `io.github.cwilliams5.earmark`
  - action `open` (key binding target `io.github.cwilliams5.earmark.open`)
  - settings: `config.toml` in the plugin's config dir
    (`HERDR_PLUGIN_CONFIG_DIR`, see `herdr plugin config-dir <id>`)
  - archive: `archive.json` in the plugin's state dir
    (`HERDR_PLUGIN_STATE_DIR`)
  - workspace metadata token `$earmark`
  - log prefix `earmark:`
- Branding: `branding/` (`python3 branding/build.py` regenerates it). See
  BRANDING.md for words to avoid in later renames.

## Layout

```
branding/       logo system (build.py), the pick in eartag/, alternatives/
icon.svg        the app tile
docs/PLAN.md    the development plan
```

(Development fills this in.)

## Rules that must not be broken (and why)

1. **Python standard library only, no build step.** `herdr plugin install`
   should work on any machine with `python3`; anything else is a dependency
   users would have to install.
2. **Call Herdr through `HERDR_BIN_PATH`,** not a hard-coded `herdr` or a
   raw socket: it's the documented, portable plugin API.
3. **Never lose a live session, never resurrect a deleted one.** Earmark
   only reads the agents' data; it never deletes or edits a transcript.
4. **State lives in the plugin's own dirs** (`HERDR_PLUGIN_STATE_DIR`,
   `HERDR_PLUGIN_CONFIG_DIR`), never in the plugin root: GitHub-installed
   plugin roots are managed checkouts that updates replace.

## How it works, in one screen

(Development fills this in. The planned shape: event hooks keep a record of
each pane's agent session as Herdr reports it; when a pane or tab closes,
its last record moves into the archive under its workspace; the `open`
action shows a popup pane listing the current workspace's archive and opens
a new tab running the resume command for the chosen one.)

## Platform facts this depends on (re-check after updates)

Herdr 0.9.5 (Omarchy 4.5.0, Claude Code 2.1.330):

- **Plugin API v1:** a `herdr-plugin.toml` manifest declares `[[actions]]`,
  `[[events]]` (hooks on named events, payload in
  `HERDR_PLUGIN_EVENT_JSON`), `[[panes]]` (`placement = "popup"` opens a
  modal terminal popup that gets all input), `[[startup]]` hooks and link
  handlers. Commands are argv arrays (no shell). Herdr injects
  `HERDR_BIN_PATH`, `HERDR_PLUGIN_STATE_DIR`, `HERDR_PLUGIN_CONFIG_DIR`,
  `HERDR_PLUGIN_CONTEXT_JSON` and the current workspace/tab/pane ids.
  "Native non-terminal plugin UI" and runtime action registration are not
  in v1. Keys bind to actions with `[[keys.command]]`,
  `type = "plugin_action"` in the user's Herdr `config.toml`.
- **Session references:** `pane.list` / `pane.get` expose
  `agent_session = { source, agent, kind, value }` when an integration has
  reported one (for Claude Code, `value` is the session id), plus `cwd`,
  `foreground_cwd`, `label`, `terminal_title`, `workspace_id`, `tab_id`.
- **What close events carry (verified 2026-11-20, phase A2):** by the time
  a hook runs, the closed panes are already gone from `pane list`, so
  Earmark must have recorded each pane's session before the close.
  - `pane.closed`: `{pane_id, workspace_id}` only.
  - `tab.closed`: `{tab_id, workspace_id}` only, and no `pane.closed` for
    the panes it held.
  - `workspace.closed`: `{workspace_id, workspace: {label, ...}}`, and no tab
    or pane events for what it held.
  - `/exit` in Claude Code (tab kept): `pane.agent_detected` with
    `released: true, final_status`; the pane's `agent_session` is already
    cleared.
  - A new agent: `pane.agent_detected {agent}` can arrive about a second
    before the integration reports the session id.
- **Restarts (verified, phase A3, in a named test session):** `herdr server
  stop` fires no close events. On start, the `[[startup]]` hook runs, then
  each restored agent pane gets `pane.agent_detected` with `released: true`
  (its resume is deferred) — the same shape as a user's `/exit`. Earmark
  must not archive those.
- **Hook events:** `pane.updated` is not a valid plugin hook (`plugin link`
  warns "unknown event"); it exists only for `events.subscribe` streams.
  Valid and used: `pane.created/closed/exited/agent_detected`,
  `tab.created/closed`, `workspace.closed/renamed`. `workspace.metadata_
  updated` does not invoke hooks either.
- **Hook environment:** `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID`,
  `HERDR_PANE_ID` (pane events), `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, the
  plugin dirs, and `HERDR_SESSION` for a named session (unset for the
  default one).
- **One plugin, every session:** plugins are global, and the config and
  state dirs (`~/.config/herdr/plugins/config/<id>`,
  `~/.local/state/herdr/plugins/<id>`) are shared by all named sessions,
  whose workspace ids repeat (`w1` in each). Key everything by session name
  as well as workspace.
- **Workspace metadata tokens** (`workspace.report_metadata`) render in the
  Space sidebar only where the user's `ui.sidebar.spaces.rows` includes the
  token.
- **Claude Code** keeps transcripts at
  `~/.claude/projects/<cwd-slug>/<session-id>.jsonl` and deletes them after
  `cleanupPeriodDays` (default 30) of inactivity. Resume: `claude --resume
  <id>`. A session that never got a message writes no transcript at all,
  and one that only ran `/exit` writes only local-command records: neither
  has anything to resume, so Earmark skips them.
- **Herdr workspaces** may share a folder (all of Cody's start in `~/Work`),
  so a session's folder can't identify its workspace; the workspace must be
  recorded at close time.

## Working on it

(Development fills this in: `herdr plugin link`, the test setup, logs via
`herdr plugin log list --plugin io.github.cwilliams5.earmark`.)

## Credits

Everything Earmark builds on or borrows from. Add each one when it lands,
not at release.

- Herdr's plugin API and CLI: the whole host surface (https://herdr.dev).
- Forge's Archived section: the idea and the workflow
  (https://github.com/cwilliams5/Forge).
- `douglascorrea/herdr-agent-inbox`: showed that recording closed chats per
  workspace and reopening them with `claude --resume` works through the
  public plugin API (idea only, no code taken).
- `pedroloch/herdr-undo-close`: documented that `tab.closed` carries no tab
  contents, so state must be indexed before a close (idea only).

## Distribution

A Herdr plugin installed from GitHub:
`herdr plugin install cwilliams5/herdr-earmark`, plus one key binding the
user adds to their Herdr config. Herdr's marketplace indexes public repos
with the GitHub topic `herdr-plugin` automatically. It is not an Omarchy
plugin and needs nothing from Omarchy, so it works wherever Herdr does
(Linux and macOS; Windows if Python and Herdr's Windows support allow).

## Releasing

1. CLAUDE.md current (status, rules, platform facts, Credits).
2. The `go-public` skill: README and media, independent reviews, the privacy
   scan last, then publish and distribute.

## Voice and conventions

Plain, practical, Windows terms where they help, no hype, no emoji.
"Earmark" in sentences; the lowercase wordmark only as a logo. Use Herdr's
own words: workspace, tab, pane, agent, session.
