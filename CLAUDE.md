# CLAUDE.md: Earmark

For an agent (or the maintainer, months later) picking this up with no memory
of how it was built. Read this first. Then read `docs/PLAN.md` (what's left
to build), `README.md` (what users see) and `branding/BRANDING.md` (the
name, logo and palette). The reasons below matter as much as the rules.

This file becomes public with the repo: no personal details, nothing about
Cody's work setup.

## Status (2026-11-27)

Public (cwilliams5/herdr-earmark), MIT, listed in Herdr's marketplace
through the `herdr-plugin` topic. 1.0.0 released 2026-11-21; 1.1.0 released
2026-11-26 (suspend tabs in place, CLAUDE_CONFIG_DIR read from each Claude
process, after eight strict-review rounds); **1.2.0 released 2026-11-27**
(v1.2.0 = 91cc7a4, its history squashed into that one commit like 1.1):
one-call snapshot, workspace notes and the /herdr-note skill, coloured agent
lines and workspace counts in Herdr's sidebar, the launcher in the config
dir, after strict reviews 9 and 10. Live on the maintainer's Herdr from this
clone (linked). Tests: 857 unit tests (Python 3.14 and 3.9); `tests/mutate.py`
plants the 1,142 one-line regressions in `tests/mutations.md` (our own, plus
the independent sets of the round 2-10 reviewers; all caught 2026-11-27),
each suite run in a scratch HOME of its own, refusing a mutant that doesn't
compile; `--shard i/n` runs it in parallel (6 shards, ~35 min; wait on their
PIDs, never a pgrep of their command). Numbers from re-planting our own list
flatter us, so each review round brings fresh ones. `tests/live_check.sh`
34/34 with Claude Code, Codex and Grok (2026-11-27; run in an isolated HOME,
see "Working on it"). What's left is in docs/PLAN.md (the Later list).

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

Suspend (1.1): an idle agent's tab can be suspended in place to free its
memory. The agent is stopped (SIGTERM), the tab stays, and a placeholder in
its pane shows the agent's last screen (or a notice) with "Press Enter to
resume"; Enter replaces the placeholder with the agent's resume command in
the same pane. Modes: off (shipped default), manual (the key), time, memory,
count. Like a browser's sleeping tabs.

Notes (1.2): one Markdown note per workspace, in a popup (read view, `e`
edits in the user's editor, `u` asks an idle Claude in the workspace to run
the /herdr-note skill, which ships in `skills/herdr-note/`). Sidebar (1.2):
model · effort · context % on each agent's second line (Claude through its
status line, Codex and Grok from their files) and per-state counts on each
workspace's row, coloured by Earmark's settings (hex or the Omarchy theme's
colours), fitted to the sidebar by Earmark. Outside Herdr (Claude's status
line, the skill, Omarchy's theme hook) everything goes through a launcher
Earmark keeps in its config dir (earmark/launcher.py), never the install
folder, which Herdr replaces at every update.

Decided so far (the details and history: `git show v1.1.0:docs/PLAN.md`):
- **No right-click menu entry.** Herdr 0.9.5 has no documented way for a
  plugin to add items to its context menus (plugin UI is terminal panes and
  popups). Retest when Herdr changes; add one if it becomes possible.
- **The sidebar info is opt-in (1.2).** Earmark always reports its
  metadata tokens (workspace counts, agent lines); they only show where the
  user's Herdr sidebar rows use them, either pasted from `earmark.py rows`
  or written by Earmark into Herdr's config.toml when `write_herdr_config`
  is on (off by default). 1.1's `$earmark` ("3 archived") and
  `report_count` are retired, no compatibility shim; an old config's
  `report_count` is ignored, never an error.
- **Suspend is in place and opt-in.** The tab keeps its place and name
  (plus a 💤 mark, display only); nothing moves to a list. The parking
  rule, in every automatic mode: never an agent that's working, blocked,
  in the tab in view, holding unsent prompt text, running a command (a
  shell under it, or anything else in its terminal's foreground group),
  waiting on a Claude timer (ScheduleWakeup / CronCreate since its process
  started), with Remote Control on, started with options Earmark doesn't
  know, or where Earmark can't read the prompt; an unseen result ("done")
  only with `suspend_unseen` (default on, Cody's call 2026-11-25); memory
  and count modes also need 10 quiet minutes. The key may take the tab in
  view; never a working or blocked agent or one with unsent text, nor a
  Codex started without --no-daemon; an unreadable prompt, unknown
  options, a status Herdr can't tell or a Claude folder Earmark can't read
  are asked about in Earmark's message popup (earmark/message.py), and
  only `y` then Enter there confirms (Herdr's notifications follow `[ui.toast]
  delivery`, off by default, so nothing important goes only there).
  `messages = "toast"` (Cody's ask, 2026-11-26: the popup takes the
  keyboard) answers in Herdr's toasts instead, with the old second press
  within 10 s, going by Herdr's own reply: a toast Herdr says it didn't
  show (off, rate limited, busy, no client), or no answer, goes to the
  popup, and only a shown "press again" starts the window.
  The idle clock counts from the agent's last activity or the moment the
  user left its tab.
- **No daemon.** Automatic checks run in a short-lived worker that a hook
  starts at most once a minute (so nothing happens while Herdr is quiet).
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

## Identity

- Name: Earmark. Repo: `cwilliams5/herdr-earmark`.
- Ids:
  - Herdr plugin id `io.github.cwilliams5.earmark`
  - actions `open` (key binding target `io.github.cwilliams5.earmark.open`,
    for example `prefix+a`), `open-workspaces` (for example
    `prefix+shift+a`), `suspend` (for example `prefix+ctrl+s`; `prefix+s` is Herdr's settings)
    and `note` (for example `prefix+i`)
  - settings: `config.toml` in the plugin's config dir
    (`HERDR_PLUGIN_CONFIG_DIR`, see `herdr plugin config-dir <id>`); the
    launcher `earmark` and the skill's copy `skills/herdr-note/` live there
    too (updates and uninstalls leave that folder alone)
  - archive: `archive.json` in the plugin's state dir
    (`HERDR_PLUGIN_STATE_DIR`); suspended records in `index.json`
    (`sessions.<name>.suspended.<pane>`), screen copies in `screens/`,
    Claude timer read offsets in `timers-<hash of the session>.json`, the worker's log in
    `worker.log`; 1.2: notes in `notes/<session>/<workspace>.md`, sent
    workspace tokens in `sidebar.json`, agent lines in
    `rows/<session>/<pane>.json`
  - metadata tokens `$earmark_blocked`, `_working`, `_done`, `_suspended`,
    `_archived`, `_note` (workspaces); `$earmark_model`, `$earmark_effort`,
    `$earmark_ctx_1..5` (agent panes)
  - log prefix `earmark:`
- Branding: `branding/` (`python3 branding/build.py` regenerates it). See
  BRANDING.md for words to avoid in later renames.

## Layout

```
herdr-plugin.toml   the manifest: actions, the popup pane, hooks
earmark.py          entry point: open, open-workspaces, popup, suspend, hook,
                    list, check; for itself: suspended (placeholder), worker
earmark/
  herdr.py          the Herdr CLI calls (through HERDR_BIN_PATH)
  store.py          index.json / archive.json in the state dir, one lock
  core.py           notes on live panes, close detection, archive, prune,
                    reopen, closed workspaces and restore, sidebar counts
  agents.py         resume commands (Herdr's table), Claude transcript facts
  config.py         config.toml (every key documented there)
  ui.py             the curses popup (Sessions / Workspaces views)
  suspend.py        suspend: facts per agent pane, the parking rule, the
                    worker (auto modes, the key, re-arm after a restart),
                    resume on view, the records' lifecycle
  placeholder.py    the placeholder in a suspended tab (raw termios; loads
                    neither curses nor sqlite3, which only Codex facts use)
  message.py        the suspend key's popup: its answers, and "suspend
                    anyway?" which only `y` confirms
  text.py           text helpers shared by the popup and the placeholder
  procs.py          process table, start times, one environment variable,
                    memory (Linux /proc, `ps` elsewhere)
  sidebar.py        the sidebar's width (copied from Herdr's client), count
                    and agent-line fitting, token building and sending
  agentrow.py       agent lines: Claude's from the status line, Codex and
                    Grok readers, the hooks' refit/resend/clear (rows/)
  statusline.py     Claude's status line: the user's command first, then
                    Earmark's part in a process of its own
  launcher.py       the launcher and skill copy in the config dir
  herdrconf.py      the rows block for Herdr's config.toml, the opt-in
                    guarded writer, theme colours, the theme-set hook
  notes.py          workspace notes: files, versions, the `note` CLI
  noteui.py         the note popup (read view, editor, ask Claude)
tests/
  _isolate.py       imported first by every test file: no real Herdr
                    (HERDR_BIN_PATH points nowhere), temp state, settings
                    and agent folders
  test_core.py      unit tests (python3 -m unittest discover tests)
  test_review_fixes.py  one test per pre-release review finding
  test_suspend.py   suspend and CLAUDE_CONFIG_DIR (phases I, J)
  test_review1.py   strict review 1 (R1-R26) and its mutation survivors
  test_review2.py   strict review 2 (R27-R52) and both reviewers' survivors
  test_sidebar.py, test_agentrow.py, test_herdrconf.py, test_notes.py   1.2
  test_review9.py   strict review 9 (R168-R193) and its reviewers' survivors:
                    hooks end to end, the note popup driven, the launcher
  test_review3.py   strict reviews 3-6 (R53-R134) and their reviewers' survivors
  test_flows.py     behaviour tests over whole sequences through the real
                    code (a placeholder started, lost and back; what a hook
                    starts in each mode; the account check; the permission
                    mode at exit; strict reviews 7-8)
  test_surfaces.py  behaviour tests where review 7's mutations got through:
                    the popup driven by keys and clicks, the message popup's
                    keys on a raw pty, the worker's command line, a closed
                    workspace's round trip, each path a record takes
  mutate.py         plants each regression in tests/mutations.md in a copy
                    of the repo and runs the suite (python3 tests/mutate.py
                    [name filter]); a pattern that no longer matches counts
                    as a failure
  live_check.sh     end-to-end against a throwaway named Herdr session
branding/           logo system (build.py), the pick in eartag/, alternatives/
media/              README images: hero.png (1.2), notes.gif, sidebar.png,
                    suspended.png, workspaces.png, reopen.gif, restore.gif,
                    hero-1.0.png (the old one), social-preview.png; shoot/ has the
                    scripts and the method (staged demo session)
skills/herdr-note/  the /herdr-note Claude skill (users link it into ~/.claude/skills)
docs/PLAN.md        what's left, and the limits reviews found and we accepted
                    (the history is in git: v1.1.0's copy has phases A-J)
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
  closes, renames, startup) takes a snapshot (one `herdr api snapshot`:
  panes, workspaces, tabs at one moment) under a lock and compares it with
  `index.json`:
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
- **Suspend** (earmark/suspend.py has the who-does-what): a hook starts
  `earmark.py worker` (detached, its own session, log in worker.log) when a
  check is due, after a restart (`--rearm`) or for the key (`--pane`). The
  worker looks at each candidate (`pane process-info`, the process table,
  the agent's files, `pane read --format ansi` for unsent text), then for
  each chosen pane: writes the record ("stopping"), saves the screen,
  checks the processes' start times, focus and status once more, SIGTERMs
  the agent and its launcher only (`chain_to`: never the whole group;
  anything else in the group made it "busy"), waits for the shell to be
  back, sets
  "suspended", waits for Herdr to stop listing the agent (wait_released;
  see the platform facts), sends Ctrl+C, then Ctrl+E Ctrl+U, and types
  `placeholder && cd <cwd> && [CLAUDE_CONFIG_DIR=...] <resume argv>` with
  `pane run` (arm: only into a bare shell, one arm at a time under a claim,
  not while Herdr still lists the session unless it's the key, backing off
  half an hour after a start that failed; an automatic arm, anything but
  the key or the suspend's own, also needs `untouched`: a fingerprint of
  the screen the same at two looks STABLE seconds apart since Earmark saw
  the shell back (a change after a restart is watched again, otherwise the
  shell is marked used and left to the key); the line carries
  `--state`/`--config`, since a pane's
  shell lacks Herdr's plugin variables), then marks the tab
  (`tab_mark`, display only: `core._unmarked` strips it wherever a name is
  recorded; hooks take stale marks off). The placeholder sets "waking" and
  exits 0, and the shell starts the agent as a new job; any refusal,
  Ctrl+C or hangup exits 1 and the shell starts nothing.
  `core.settle_suspended` ends records: open in another pane → gone; in its
  own pane only once "waking" or after STOP_STALE (Herdr shows a stopped
  session for a moment); pane gone → archived "closed"; waking with no
  session after RESUME_GRACE → archived "exited"; another session in its
  pane → archived "replaced"; a "stopping" record whose worker died →
  "suspended" (the regular re-arm pass starts its placeholder). Missing
  placeholders: a restart sets `rearm` (`--rearm`, rearm_all waits for the
  panes); otherwise a hook starts `--rearm-pass` at most once a minute in
  every mode where no automatic check runs (`suspend.waiting`), and an
  automatic check runs the pass itself. Herdr's agent field isn't proof, so the worker's
  check_pane looks at processes: the agent relaunched by Herdr's restore
  ends the record, a bare shell gets its placeholder back. Enter is only
  ever sent when the placeholder is the pane's foreground (checked right
  before; the placeholder also discards any keys still queued when it
  exits, so a late Enter can't reach the agent starting). The record keeps
  hashed fingerprints of the agent's account settings (`agents.account_env`:
  ANTHROPIC_*, cloud profiles, OPENAI_*, proxies); the placeholder, which
  runs in the shell the resume will, compares its own environment on Enter
  and asks for a second Enter when they differ (a shell's later exports
  aren't in its /proc environ, so the check can't happen at suspend time).
  Notes carry `since`,
  `focused_at`, `status_at` (the idle clock) and `config_dir` between
  snapshots (core.CARRY).
- **Sidebar (1.2):** per workspace, `$earmark_blocked/_working/_done/
  _suspended/_archived/_note` (bare numbers; zeros and what doesn't fit
  cleared) with `workspace report-metadata <id> --source <plugin id>`; per
  agent pane `$earmark_model`, `$earmark_effort` and one of
  `$earmark_ctx_1..5` (the level picks which, so each has its colour) with
  `pane report-metadata`. What was sent lives in sidebar.json (workspaces)
  and rows/<session>/<pane>.json (agents), caches without fsync, so a status
  change doesn't rewrite index.json. 1.1's `$earmark` is cleared once.
  A row's tokens go whole whenever one changed (Herdr keeps only the newest
  report per source and target), and a failed report is sent again.
  Colours only exist in Herdr's config (herdrconf.py writes or prints the
  block; it keeps lines Herdr's settings screen put inside the markers,
  writes through a symlink, backs off when the file changed meanwhile).
  Claude's values come from `<config dir>/earmark statusline -- <cmd>`, run
  by Claude Code as its statusLine (statusline.py: the user's output first,
  Earmark's part forked off); the hooks refit from the cache under its lock,
  resend after a restart (rows/<session>/.boot vs the index's boot) and
  clear gone agents. Each hook does the suspend side first, then the
  sidebar, the config block and the launcher (launcher.ensure).
- **Notes (1.2):** notes/<session>/<workspace>.md; on a close the text goes
  into the closed workspace's record and the file is removed after the
  archive is saved (retire_notes); restore writes it back (put_back). A
  closed workspace holding a note is never pruned by time; a recreated
  session's old workspaces are filed as closed at the restart that spots it.
  `note show --json` gives the skill each agent's last 3 requests, the start
  and end of its last 3 replies and its tools' names (agents.recent_exchange:
  never tool output, nor the user records Claude writes for task results and
  `!` shell output), and the transcript path only with `[notes]
  read_transcripts`. The popup's editor works on a copy, saved back against
  the version it started from.

## Platform facts this depends on (re-check after updates)

Herdr 0.9.5 (Omarchy 4.5.0, Claude Code 2.1.332):

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
- **Notifications:** `herdr notification show` follows `[ui.toast]
  delivery`, which is `"off"` by default (Herdr's CLI and config
  references; `herdr --default-config`), and answers `{"shown": bool,
  "reason": "shown" | "disabled" | "rate_limited" | "no_foreground_client" |
  "busy"}` (`herdr api schema`). Anything the user must see goes through
  Earmark's own popup (`earmark/message.py`) unless Herdr says it showed it.
  Plugin popups have no pane id anyone can find: they're not in `pane list`
  or `api snapshot`, and `plugin pane open` answers only `{"type": "ok"}`
  (checked 2026-11-26), so nothing outside can type into one. A popup
  opened with `--no-focus` leaves the keyboard where it was: the maintainer
  typed on in a pane while one opened, every key reached the pane, and the
  popup closed by itself (checked by hand 2026-11-26; a headless server
  can't show it).
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
- **Suspend facts (verified 2026-11-25 in an isolated Herdr, real Claude
  Code 2.1.332):**
  - `pane read` answers with the text itself (not JSON), lines ending in
    CRLF; `--format ansi` keeps the colours. `--source visible` follows the
    user's scroll position (a pane scrolled up gives the scrolled-to part);
    `--source recent --lines <viewport_rows>` gives the bottom screen, and
    a full-screen program's screen (checked 2026-11-26). Earmark reads that
    way (`suspend.screen_of`).
  - A pane's `revision` moves with its folder and title, not with typing or
    output (checked 2026-11-26): it can't tell whether a shell was used, so
    Earmark compares the screen.
  - `pane process-info` gives `shell_pid`, `foreground_process_group_id` and
    `foreground_processes[{pid, name, argv, cmdline, cwd}]`; a bare shell
    has its own pid as the foreground group.
  - Claude Code exits cleanly on SIGTERM (prints its "Resume this session
    with" hint; transcript intact). Herdr can still show its session in the
    pane for a moment after the process is gone.
  - Claude's prompt box is the text between the last two `─` rules on
    screen, after `❯`; an empty one shows a faint `Try "..."` hint.
  - Claude writes a Shift+Tab permission-mode change to its transcript only
    when it exits (entering auto is written at once; plan and manual
    aren't), re-stamping the mode in force on SIGTERM; its footer shows the
    mode ("⏵⏵ auto mode on", "⏵⏵ bypass permissions on", "⏸ plan mode on",
    "⏸ manual mode on"). Checked live 2026-11-26, Claude Code 2.1.33x.
    Earmark reads the mode again after the stop (`agents.mode_to_resume`).
  - Claude's transcripts record `permission-mode` records
    (`permissionMode`, e.g. "auto") and every tool call with a
    `timestamp` (ScheduleWakeup `delaySeconds`/`stop`, CronCreate,
    CronDelete). `<config>/sessions/<pid>.json` is Claude's registry of
    running processes: `status` (idle / busy / shell), `bridgeSessionId`
    when Remote Control is on. A Claude Bash tool call or Monitor runs
    under it as `bash -c source <config>/shell-snapshots/...`.
  - In a headless server nothing is ever "seen": answers stay `done` until
    a focus command (`tab focus`) marks them seen (`idle`).
  - The action context (`HERDR_PLUGIN_CONTEXT_JSON`) has
    `focused_pane_id`; `herdr plugin action invoke <id>.<action>` runs an
    action from the CLI.
  - Pane ids survive a server restart (the placeholder is re-armed by id).
  - **A command typed into the shell right after the agent exits, before
    Herdr sees the shell's prompt, leaves Herdr listing the stopped agent**
    (`agent` and `agent_session`) indefinitely, and Herdr's restore then
    relaunches it. Waiting until Herdr lets go (about a second) avoids it:
    tested 0 s wait → stale twice, 2 s → clean twice. Claude's Herdr hook
    reports only SessionStart; Herdr notices exits itself.
  - **Never exec the agent in the placeholder's place** (1.1 development,
    found on the maintainer's machine 2026-11-25): the agent kept the
    placeholder's pid and process group, Herdr didn't register it as an
    agent again, and on the next suspend Herdr still listed the session; a
    `claude --resume <id>` line then reached the shell at the same moment as
    Earmark's placeholder line and they ran glued together, so Claude got
    Earmark's command as a first prompt. The shell starting the agent as a
    new job keeps Herdr's view right; Ctrl+E Ctrl+U before typing and the exact
    placeholder match (`is_placeholder`) are the backstops.
  - Once stale, nothing a plugin can call clears `agent_session`:
    `pane release-agent --seq <ns>` and the socket's
    `pane.clear_agent_authority` clear `agent` only; a custom-source
    `report-agent` (from inside or outside the pane) doesn't replace an
    official agent.
  - `pane report-agent-session` from a custom source is accepted but not
    shown as `agent_session`; only an official source (`herdr:claude`) is.
- **The sidebar's width (1.2, copied from Herdr 0.9.5's client code; drift
  risk, re-check before every release and after every Herdr update).**
  Herdr never tells a plugin how wide the sidebar is on screen: the
  server's layout is its own virtual screen (`api snapshot` layouts are
  140x42 at x=0 whatever the client shows), and the client draws the
  sidebar. Earmark fits its sidebar text to the row itself, because
  Herdr's fitting drops a workspace's name first (every text token is
  flexible with a 1-column minimum, and on overflow Herdr adds them back
  from the right: src/ui/sidebar.rs `resolved_token_spans`), so
  earmark/sidebar.py copies Herdr's math: width = a dragged width, which
  the client keeps in `$XDG_STATE_HOME/herdr/client-shell/local-<FNV-1a 64
  of the session's herdr-client.sock path>.json` (`sidebar_width`, set only
  while dragged; src/client/shell/preferences.rs; session.json's field is
  always null in 0.9.5), else `[ui] sidebar_width` (26),
  clamped to `sidebar_min_width`/`sidebar_max_width` (18/36)
  (src/client/shell/state.rs); minus a divider column and a scrollbar
  column (always assumed); workspace lines indented 1 then 3, with 2 kept
  at the right (src/client/shell/sidebar.rs `render_workspace_rows`);
  agent lines indented 1 then 3 (src/client/shell/agent_sidebar.rs); " · "
  between text tokens (src/ui/sidebar/tokens.rs). None of it is an
  official interface: if Herdr changes it, rows get cut again ("Opus 5…")
  or counts drop earlier than needed. A dragged sidebar refits at the next
  Herdr event (a tab switch), not at once. Worktree child workspaces are
  indented more (6/8 columns); the snapshot carries `worktree {repo_key,
  is_linked_worktree}` (src/api/schema/workspaces.rs), but Earmark doesn't
  allow for the deeper indent yet (a README known limit). Text is measured
  close to Herdr's unicode-width (emoji sequences two columns; some Thai and
  Indic marks, Hangul jamo and emoji newer than Python's Unicode differ: a
  README known limit).
- **Sidebar tokens and styles (1.2, Herdr 0.9.5):** metadata token values
  are plain text (an ESC byte is stripped: tested); at most 16 per report,
  names `[A-Za-z0-9_-]{1,32}`, optional `ttl_ms` (24 h max) and `seq`. Pane
  reports also take `display_agent`, a field apart from `agent`. Styles exist
  only in Herdr's config, per token: `fg` (hex only; palette names
  rejected), `bold`, `dim`, `rules` (equals/contains/starts_with/gt/lt +
  hide; numeric ones need a bare number: Herdr's test rejects "90%"). No
  italic, underline or background. A missing token disappears with its
  " · "; an empty row disappears. `rows_by_agent` accepts claude, codex and
  grok (grok through Herdr's agent manifests). `herdr config check` exits 1
  for any issue in the file, so the writer compares issue lines before and
  after. `herdr api snapshot` layouts are the server's virtual screen, not
  the client's.
- **`herdr agent prompt <pane> <text>`** submits a prompt to an agent and
  refuses a blocked one (`agent_blocked`), queueing it into a working one;
  the note popup's `u` uses it, after checking (again right before
  sending) that the agent is idle and the prompt box on its bottom screen
  is empty.
- **Plugin install folders (Herdr 0.9.5):** every GitHub install and update
  goes into a new `plugins/github-installations/<id>/<pid>-<n>/checkout`,
  and Herdr deletes the old one after an install or at server start
  (src/plugin_paths.rs, src/plugin_installations.rs). `herdr plugin
  config-dir <id>` prints the plugin's config dir, which survives both;
  there's no state-dir command. Hence the launcher there.
- **Herdr's own settings screen** (`prefix+s`) edits config.toml line by
  line (src/config/io.rs `upsert_section_raw`): a new key goes right before
  the next table header, so after Earmark's BEGIN marker when Earmark's
  block follows that table; herdrconf keeps such lines, above the block.
- **CLI routing:** a `herdr` call without `--session` goes to
  `HERDR_SOCKET_PATH` (in a hook: the hook's own session), so Earmark
  names every session, `--session default` included (src/session.rs).
- **Report sequence:** Herdr drops a metadata report older (by `seq`) than
  the last one from the same source on that pane or workspace, and still
  answers OK (src/app/api/panes.rs, workspaces.rs).
- **Workspace ids are reused** (src/workspace.rs): an in-memory counter,
  seeded after a restart with the highest surviving id + 1. Anything keyed
  by workspace id must follow `workspace.closed` (notes do).
- **Claude Code's status line** (2.1.332) gets `model.display_name`,
  `effort.level` and `context_window.used_percentage` /
  `context_window_size`, and reruns on model, effort and token changes.
  Hooks don't carry effort ("absent for session-lifecycle hooks"), and a
  UserPromptSubmit hook exiting 2 erases the prompt: why Earmark uses the
  status line, never hooks.
- **Omarchy themes** (4.5): `~/.local/state/omarchy/current/theme/colors.toml`
  with semantic names (red, yellow, green, blue, magenta, orange, accent,
  foreground, dark_foreground, muted...); `omarchy-theme-color --all` prints
  them resolved with each theme's fallbacks; scripts in
  `~/.config/omarchy/hooks/theme-set.d/` run (bash) after a theme switch.
  Omarchy sets Herdr's theme to "terminal".
- **Herdr workspaces** may share a folder (a common setup),
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
- **Testing new code without touching the live Herdr: an isolated HOME.**
  The linked clone runs in every session of the maintainer's Herdr, so
  unfinished code goes in a git worktree (e.g. in a scratch folder) and is
  tested against a Herdr with its own HOME:
  `ET=$(mktemp -d /tmp/et.XXXX)` (short: socket path limit), then with
  `env -i HOME=$ET PATH=<claude's dir>:/usr/bin:/bin TERM=xterm-256color
  LANG=C.UTF-8 SHELL=/bin/bash`: `herdr plugin link <worktree>`, `setsid
  nohup herdr --session t server`. For real Claude sessions, symlink
  `$ET/.claude` to `~/.claude` (auth, the Herdr hook) and copy
  `~/.claude.json` to `$ET` (mode 600; delete afterwards). Earmark's
  Python then runs with `HERDR_SOCKET_PATH=$ET/.config/herdr/sessions/t/herdr.sock
  HERDR_SESSION=t HERDR_PLUGIN_STATE_DIR=... HERDR_PLUGIN_CONFIG_DIR=...`.
  `tests/live_check.sh` runs the same way (`env -i HOME=$ET ...
  XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR bash tests/live_check.sh`).
- `tests/live_check.sh`: about two minutes against a throwaway named session
  (`earmark-live-check`) with real Claude Code sessions (one-word prompts
  in `$XDG_RUNTIME_DIR/earmark-live-check`, a private folder Claude Code is
  told to trust); it removes the session, its transcripts and its archive
  entries afterwards. Never test closes in Cody's own session: his real
  tabs get archived, and the maintainer's real archive is in the same
  state dir: remove only test entries, by their `herdr_session`.

### Pitfalls learned the hard way

- **Hooks run the clone's code live.** When the clone is linked, a
  half-applied edit runs in the maintainer's real Herdr on the next event. Make
  multi-file changes with an all-or-nothing edit script, then run the
  unit tests at once.
- **Running inside Herdr leaks its env.** This shell (an agent in a Herdr
  pane) has `HERDR_SOCKET_PATH`, `HERDR_PANE_ID` etc., so any `herdr`
  command, or Earmark code, talks to the maintainer's real server. For anything
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
  exits; ask the maintainer to stop it (`pkill -f app-server-daemon`).
  A user's own `codex` alias may already add `--no-daemon`, which is why
  Earmark's resume command starts with `command codex`.
- **Screenshots and screen takeovers** need the maintainer's OK first, and no
  scripted keys or mouse into his desktop: drive Herdr through its CLI and
  socket instead (see `media/shoot/README.md`).
- `python3 earmark.py list` / `check` (or the launcher: `<config dir>/earmark
  check`) show the archive and the settings in
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
- Suspend learned from six Herdr sleep/park plugins reviewed 2026-11-25
  (ideas only, no code taken): common-resources/herdr-autopark (frozen
  view, unsent-text check), novarii/claude-hibernate (pending timers from the
  transcript, resume flags and permission mode), 0xArchiviste/herdr-memory-guard
  (MemAvailable thresholds), bengemine/herdr-hibernate, meta-boy/herdr-shelve
  and utkrshm/herdr-rest (records first, re-check before acting; herdr-rest
  has no license, so nothing but the idea).
- Claude Code, Codex and Grok's own session files: read (never written) for
  titles, last activity and whether a session still exists; formats learned
  from the files themselves.
- 1.2's sidebar and notes learned from Herdr plugins read first (ideas
  only, no code taken): pdalinis/herdr-disp-model and herdr-ctx-bar (model
  and context on agent rows; the default sidebar layout), rchougule/
  herdr-agents-info (one token per colour band), dkbo/herdr-model-badge
  (wrapping the user's status line), herdr-ctx-bar's guarded config edit
  (backup, `config check`, rollback), alexarthurs/herdr-notes and
  cyperx84/herdr-notes (a note per workspace; atomic saves, reload on
  outside changes, the editor, a CLI).
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
   changed (`media/shoot/README.md`). Re-check the sidebar width model
   (platform facts, "The sidebar's width") against the installed Herdr's
   source (and where the client keeps a dragged width, and how plugin
   install folders are laid out: the launcher depends on it), then look at
   the real sidebar with Earmark's rows, dragged too: text cut by Herdr, or
   counts dropped while there was room, means it drifted.
4. A fresh correctness review of the changes for anything substantial.
5. The go-public skill's privacy scan (`scripts/privacy-scan.sh`) as the
   last step before pushing.
6. Release notes shown to Cody first, then `gh release create vX.Y.Z
   --title "Earmark X.Y.Z" --notes-file notes.md`.
7. The marketplace needs nothing: Herdr indexes repos with the
   `herdr-plugin` topic every 30 minutes
   (https://assets.herdr.dev/plugins/index.json). The social preview is
   `media/social-preview.png`, uploaded by hand in the repo's settings.
8. Afterwards: status here, `docs/PLAN.md` (tick the release, keep it short),
   the maintainer's dotfiles
   (which mention the version).

## Voice and conventions

Plain, practical, Windows terms where they help, no hype, no emoji.
"Earmark" in sentences; the lowercase wordmark only as a logo. Use Herdr's
own words: workspace, tab, pane, agent, session.
