# CLAUDE.md: Earmark

For an agent (or the maintainer, months later) picking this up with no memory
of how it was built. Read this first. Then read `docs/PLAN.md` (what's left
to build), `README.md` (what users see) and `branding/BRANDING.md` (the
name, logo and palette). The reasons below matter as much as the rules.

This file becomes public with the repo: no personal details, nothing about
Cody's work setup.

## Status (2026-11-21)

1.0.0, released and public (cwilliams5/herdr-earmark), MIT. Listed in
Herdr's marketplace through the `herdr-plugin` topic. Live on Cody's Herdr
from this clone (linked). Tests: 54 unit tests (Python 3.14 and 3.9) and
`tests/live_check.sh` 20/20 with Codex and Grok. Later, not in 1.0: a
right-click menu entry (if Herdr ever allows it), facts for Pi, Copilot and
the other agents, smarter handling when CLAUDE_CONFIG_DIR differs between
the shell and Herdr's server, dropping the Codex `--no-daemon` workaround
once herdrdev/herdr#4649 is fixed.

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

A second view of the same popup (Shift+ the key) lists closed workspaces.
Restoring one brings back exactly the tabs it had when it closed, in order,
with their names and folders, agent tabs resuming their sessions; the rest
of that workspace's archive stays in the archive. Splits are not restored:
each tab comes back with one pane.

Decided so far (details in `docs/PLAN.md`):
- **No right-click menu entry.** Herdr 0.9.5 has no documented way for a
  plugin to add items to its context menus (plugin UI is terminal panes and
  popups). Retest when Herdr changes; add one if it becomes possible.
- **The sidebar count is opt-in.** Earmark can report a workspace metadata
  token (`$earmark`, e.g. "3 archived"); it only shows if the user adds the
  token to their sidebar rows, and a setting turns the reporting off.
- **Cleanup follows the agent:** with `keep_days` unset (the default),
  sessions of agents Earmark can look into (Claude Code, Codex, Grok) stay
  exactly as long as the agent keeps them, whatever retention the user set
  there (Claude Code's `cleanupPeriodDays`, default 30); other agents'
  sessions and closed workspaces go after 30 days. Before listing, Earmark
  checks the agent's files and drops sessions that are gone, so a dead
  session is never offered. Each entry remembers the file it was read from
  and its modification time, and an unchanged file isn't read again (300
  entries: ~0.6 s uncached, under 1 ms cached).

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

## Cody's own setup (what a session needs to know)

- Keys: Ctrl+Space then `a` opens the archive, Ctrl+Space then Shift+A
  the closed workspaces (Herdr's prefix is Ctrl+Space on Omarchy). Both are
  `[[keys.command]]` blocks in his `~/.config/herdr/config.toml`, tracked
  in his dotfiles.
- The `$earmark` sidebar count is off: he tried it and prefers it off.
  `title_first` is the default (`"tab"`): he names his tabs.
- His real archive and notes are in
  `~/.local/state/herdr/plugins/io.github.cwilliams5.earmark/`: never clean
  it up wholesale; remove only test entries by their `herdr_session`.
- He runs the linked clone, not the installed release, while Earmark is
  young (see docs/PLAN.md, "Later").

## Identity

- Name: Earmark. Repo: `cwilliams5/herdr-earmark`.
- Ids:
  - Herdr plugin id `io.github.cwilliams5.earmark`
  - actions `open` (key binding target `io.github.cwilliams5.earmark.open`,
    Cody's Ctrl+Space a) and `open-workspaces` (Ctrl+Space Shift+A)
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
herdr-plugin.toml   the manifest: actions, the popup pane, hooks
earmark.py          entry point: open, open-workspaces, popup, hook, list, check
earmark/
  herdr.py          the Herdr CLI calls (through HERDR_BIN_PATH)
  store.py          index.json / archive.json in the state dir, one lock
  core.py           notes on live panes, close detection, archive, prune,
                    reopen, closed workspaces and restore, sidebar counts
  agents.py         resume commands (Herdr's table), Claude transcript facts
  config.py         config.toml (every key documented there)
  ui.py             the curses popup (Sessions / Workspaces views)
tests/
  test_core.py      unit tests (python3 -m unittest discover tests)
  live_check.sh     end-to-end against a throwaway named Herdr session
branding/           logo system (build.py), the pick in eartag/, alternatives/
media/              README images: hero.png, workspaces.png, reopen.gif,
                    restore.gif, social-preview.png; shoot/ has the
                    scripts and the method (staged demo session)
tests/test_review_fixes.py  one test per pre-release review finding
docs/PLAN.md        the development plan and log
```

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

- **Notes, not events.** Herdr's close events carry only ids, so every hook
  (`pane.focused`, `pane.agent_detected`, `pane.agent_status_changed`,
  closes, renames, startup) takes a snapshot (`pane list`, `workspace
  list`, `tab list`) under a lock and compares it with `index.json`:
  - a noted agent pane that's gone was closed: archive it;
  - a noted pane whose agent was `released` was exited: archive it, unless
    it existed at the startup hook less than `BOOT_GRACE` (60 s) ago (a
    restored pane waiting for its deferred resume);
  - a different session in a noted pane (`/clear`, `/resume`): archive the
    old one;
  - a workspace in the last tab map that's gone was closed: record it in
    `archive["workspaces"]` with its tabs (order, name, folder, agent
    session), separately from the per-session entries;
  - any archived session that's live again leaves the archive.
- **Archive entries** are keyed `agent:session_id` and carry the Herdr
  session name ("default" unless `HERDR_SESSION`), workspace id and label,
  tab name, pane name, tab position, cwd, the agent's title, closed_at and
  last_active. Sessions with nothing to resume (Claude: no transcript, or
  only `/exit`) are never archived.
- **The popup** (`[[panes]]` popup; the `EARMARK_VIEW` env picks the view)
  prunes first (keep_days by last activity; Claude transcripts that are
  gone), lists by workspace label, and reopens with `herdr tab create` +
  `herdr pane run <resume argv>`. Restore creates the workspace (or uses a
  live one with the same name), renames its first tab, adds the rest, and
  resumes agent tabs whose session still exists.
- **Names:** `core.names()` shows the user's pane or tab name first (Herdr's
  default labels, "Initial" or a number, don't count), the agent's title
  dimmed after it; `title_first = "agent"` swaps them.
- **Sidebar count:** after a change, `workspace report-metadata <id>
  --source <plugin id> --token earmark=...` (the id must come first). Shown
  only if the user adds `$earmark` to `ui.sidebar.spaces.rows`.

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
  Earmark hooks `pane.closed`, `tab.closed`, `workspace.closed`,
  `pane.agent_detected`, `pane.agent_status_changed`, `pane.focused`,
  `workspace.renamed`, `tab.renamed`, plus `[[startup]]`.
  `workspace.metadata_updated` does not invoke hooks.
- **Hooks are started by the server, without a shell,** so a hook's parent
  process is the Herdr server (checked: the recorded pid is `herdr
  server`'s). Earmark notices a restart from a new parent pid, whichever
  hook runs first (the restored panes' "released" hooks race the startup
  hook).
- **Herdr's CLI scans the whole argv for its global flags** (`-h`,
  `--help`, `--session[=]`, `--remote[=]`, `--handoff`) before anything
  else, so a tab or workspace name like `-h` passed with `--label` changes
  what the command does. Earmark never passes a name starting with `-`.
- **Session ids** (`agent_session.value`) can be any string up to 512 bytes
  without control characters, reported by any process in a pane. Earmark
  types resume commands into a shell, so ids starting with `-` or holding a
  quote or backslash (fish reads a backslash-quote inside single quotes as
  a quote) are never archived or reopened.
- **Tab order:** `tab list` returns tabs in on-screen order; a tab's
  `number` is fixed at creation and doesn't follow moves.
- **Workspace labels:** a workspace the user hasn't named is labelled
  after its folder (or git repo), so two such workspaces in one folder
  share a label, and Earmark's archive goes by label.
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
- **Python:** standard library only, and it must run on Python 3.9 (macOS's
  built-in `python3`): no `tomllib` without the fallback in `config.py`, no
  3.10+ syntax. Checked 2026-11-21 by running the unit tests and the popup
  under a temporary `mise exec python@3.9`.
- **Codex** (0.171): `~/.codex/state_N.sqlite` (highest N), table `threads`:
  `id`, `rollout_path`, `name` (generated title), `title`/`first_user_message`,
  `updated_at` (seconds). Its terminal title is "<name> | <folder>". Since
  0.157 interactive Codex runs sessions in a shared app-server daemon that
  executes hooks with the environment of the pane that started it, so
  Herdr's Codex integration reports sessions to that pane or nowhere
  (herdrdev/herdr#4649, open). Workaround: `codex --no-daemon`; Earmark's
  resume command for Codex uses it. A daemon started inside a test session
  keeps that session's socket until it exits.
- **Grok** (1.0.92): `~/.grok/sessions/<url-encoded folder>/<id>/summary.json`
  with `session_summary` (generated title, filled in a little after the
  first answer), `last_active_at` (ISO, nanoseconds), `num_messages`. Its
  terminal title is "<title> - grok", or a status like "Waiting for
  response…" while it works. First run in a folder asks to trust it ("y").
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

- The clone is linked: `herdr plugin link ~/Work/herdr-earmark` (re-run
  after editing `herdr-plugin.toml`; code changes apply on the next hook or
  popup, no reload needed).
- `python3 -m unittest discover tests`: fast, never touches Herdr.
- `EARMARK_AGENTS="codex grok" tests/live_check.sh` adds a close, reopen,
  close-again cycle per agent (each must be installed and signed in; 20
  checks pass as of 2026-11-21).
- `tests/live_check.sh`: about two minutes against a throwaway named session
  (`earmark-live-check`) with real Claude Code sessions (one-word prompts
  in `$XDG_RUNTIME_DIR/earmark-live-check`, a private folder Claude Code is
  told to trust); it removes the session, its transcripts and its archive
  entries afterwards. Never test closes in Cody's own session: his real
  tabs get archived, and his real archive is in the same state dir.

### Pitfalls learned the hard way

- **Hooks run the clone's code live.** The plugin is linked, so a
  half-applied edit runs in Cody's real Herdr on the next event. Make
  multi-file changes with an all-or-nothing edit script, then run the
  unit tests at once.
- **Running inside Herdr leaks its env.** This shell (an agent in a Herdr
  pane) has `HERDR_SOCKET_PATH`, `HERDR_PANE_ID` etc., so any `herdr`
  command, or Earmark code, talks to Cody's real server. For anything
  meant to be isolated, use `env -i HOME=... PATH=/usr/bin:/bin`, or target
  a named session (`herdr --session X ...`, or `HERDR_SOCKET_PATH` +
  `HERDR_SESSION` for Earmark's Python).
- **Herdr's socket path must be short** (Unix `sun_path`, ~108 bytes): a
  throwaway `HOME` under the long scratchpad path fails with "local socket
  name length exceeds capacity"; use `mktemp -d /tmp/et.XXXX`.
- **Test servers:** `herdr --session X server` (headless, via `setsid
  nohup`), `herdr --session X server stop`, `herdr session delete X`.
  `HERDR_CONFIG_PATH` points a server and client at another config.
- **Herdr CLI shape:** ids come before options (`workspace report-metadata
  <id> --source ...`); `--opt=value` isn't accepted; `pane process-info
  --pane <id>`; `tab create` returns `.tab.tab_id` and
  `.root_pane.pane_id`; `workspace create` also returns `.workspace`.
  Popups have no pane id: close one with a raw socket request
  `{"method":"popup.close"}`.
- **Agents' first run in a folder:** Claude Code asks to trust it with "No,
  exit" preselected (send Down, Enter); Grok asks (send `y`); Codex
  doesn't. A Claude session without a message writes no transcript.
- **Codex:** always `codex --no-daemon` in tests. A Codex started without
  it inside a test session spawns a shared daemon that keeps that session's
  socket after the test, and Codex sessions then report nowhere until it
  exits. Auto mode won't let an agent kill processes: ask Cody
  (`pkill -f app-server-daemon`). Cody's shell wraps `codex` in a function
  that adds `--no-daemon` once (his dotfiles).
- **Screenshots and screen takeovers** need Cody's OK first, and no
  scripted keys or mouse into his desktop: drive Herdr through its CLI and
  socket instead (see `media/shoot/README.md`).
- `python3 earmark.py list` / `check` show the archive and the settings in
  effect; `debug_log = true` in config.toml logs every hook's event to
  `events.jsonl` in the state dir; hook errors are in `herdr plugin log list
  --plugin io.github.cwilliams5.earmark`.
- The popup needs a person: ask Cody to press the keys and click.

## Credits

Everything Earmark builds on or borrows from. Add each one when it lands,
not at release.

- Herdr's plugin API, CLI and socket API: the whole host surface
  (https://herdr.dev, https://github.com/herdrdev/herdr).
- Herdr's table of resume commands per agent ("Native session restore" in
  its session-state docs): Earmark's defaults copy it.
- Forge's Archived section: the idea and the workflow
  (https://github.com/cwilliams5/Forge).
- `douglascorrea/herdr-agent-inbox`: showed that recording closed chats per
  workspace and reopening them with `claude --resume` works through the
  public plugin API (idea only, no code taken).
- `pedroloch/herdr-undo-close`: documented that `tab.closed` carries no tab
  contents, so state must be indexed before a close (idea only).
- The `codex --no-daemon` workaround documented in herdrdev/herdr#4649.
- Claude Code, Codex and Grok's own session files: read (never written) for
  titles, last activity and whether a session still exists; formats learned
  from the files themselves.
- Python's standard library (curses, sqlite3, tomllib where present).

## Distribution

A Herdr plugin installed from GitHub:
`herdr plugin install cwilliams5/herdr-earmark`, plus one key binding the
user adds to their Herdr config. Herdr's marketplace indexes public repos
with the GitHub topic `herdr-plugin` automatically. It is not an Omarchy
plugin and needs nothing from Omarchy, so it works wherever Herdr does
(Linux and macOS; Windows if Python and Herdr's Windows support allow).

## Releasing

`main` must stay release-quality: `herdr plugin update` installs whatever
is on `main`, not the latest tag. For a release (go-public skill, "Later:
updates"):

1. Version in two places: `herdr-plugin.toml` (`version`) and
   `earmark/__init__.py` (`VERSION`). Update the README's "Tested with".
2. Unit tests (also on Python 3.9: `mise exec python@3.9 -- python -m
   unittest discover tests`, then `mise uninstall python@3.9.<x>`), and
   `EARMARK_AGENTS="codex grok" tests/live_check.sh`.
3. Re-check README claims against the code; re-shoot media if the popup
   changed (`media/shoot/README.md`).
4. A fresh correctness review of the changes for anything substantial.
5. `~/.claude/skills/go-public/scripts/privacy-scan.sh ~/Work/herdr-earmark`
   as the last step before pushing.
6. Release notes shown to Cody first, then `gh release create vX.Y.Z
   --title "Earmark X.Y.Z" --notes-file notes.md`.
7. The marketplace needs nothing: Herdr indexes repos with the
   `herdr-plugin` topic every 30 minutes
   (https://assets.herdr.dev/plugins/index.json). The social preview is
   `media/social-preview.png`, uploaded by hand in the repo's settings.
8. Afterwards: status here, `docs/PLAN.md`'s log, Cody's dotfiles
   (`docs/customizations.md` mentions the version).

## Voice and conventions

Plain, practical, Windows terms where they help, no hype, no emoji.
"Earmark" in sentences; the lowercase wordmark only as a logo. Use Herdr's
own words: workspace, tab, pane, agent, session.
