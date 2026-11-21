# Earmark: development plan

Written 2026-11-20 after naming and setup. It's the source of truth for what's
left: a session that starts cold (after a context compaction, or a
different Claude) reads CLAUDE.md, then this, and carries on from the first
unchecked item. Update it as you go: tick items, add what you learn, and
keep the log at the end.

## Goal

Closing a tab that runs a coding agent files its session under the Herdr
workspace it came from; one key (or the mouse) opens that workspace's
archive and reopens any session in a new tab. Ready to release when it does
that reliably for Claude Code, has resume commands for the other agents
Herdr reports sessions for, cleans up after itself, is tested, and the
`go-public` skill has a README to build on.

## Decisions already made (don't re-litigate)

- **A Herdr plugin from GitHub,** Python standard library only, no build
  step. Not an Omarchy plugin. Repo `cwilliams5/herdr-earmark`, plugin id
  `io.github.cwilliams5.earmark`.
- **Scope by Herdr workspace, recorded at close time,** never by folder:
  workspaces can share a folder (Cody's all start in `~/Work`).
- **The popup is the UI,** opened by one key binding, fully usable with the
  mouse (click, double-click to reopen, wheel, × to forget) and the keyboard.
- **No right-click menu entry** unless Herdr adds a way (A3 tests it once).
- **The sidebar count is opt-in:** shown only if the user adds the
  `$earmark` token to their sidebar rows; a setting turns reporting off.
  Cody wants to see it before deciding if he likes it.
- **Cleanup:** `keep_days` (default 30) from the session's last activity,
  plus a check that the agent's saved conversation still exists, where
  Earmark knows where to look. Earmark never deletes agent data. To keep a
  longer archive, the user raises the agent's own retention (Claude Code's
  `cleanupPeriodDays`).
- **Reopen goes into a new tab in the same workspace,** labeled with the
  session's title, and the entry leaves the archive (it's live again; it
  comes back when closed again).

## Phases

### A. Skeleton and platform checks

Nothing here is guessed: each check records what Herdr actually does in the
Log, and CLAUDE.md's platform facts are corrected from it.

- [x] A1 `herdr-plugin.toml` with the id, an `open` action and a popup pane
      that says hello; `herdr plugin link ~/Work/herdr-earmark`; a
      `[[keys.command]]` binding in Herdr's `config.toml` (pick a free key
      with Cody; Omarchy's prefix is Ctrl+Space). Check: the key opens the
      popup over the current tab, mouse clicks reach it, Esc closes it.
- [x] A2 Event recorder: hooks on `pane.closed`, `pane.exited`,
      `tab.closed`, `workspace.closed`, `pane.agent_detected`,
      `pane.updated`, `workspace.renamed` that append the raw
      `HERDR_PLUGIN_EVENT_JSON` and env to a log in the state dir. Then, in a
      scratch workspace: start `claude`, close its pane; start it, close
      its tab; `/exit` Claude but keep the tab; close the workspace. Record
      what each event carries (does `pane.closed` still name the session?).
- [x] A3 Server restart and shutdown: with the recorder on, run
      `herdr server stop` and start again (or ask Cody to log out and in).
      Do close events fire? A restart must not archive sessions Herdr is
      about to restore.
- [x] A4 Context menus: give the action `contexts = ["workspace"]` and ask
      Cody to right-click a workspace and a tab once. If the action appears,
      the right-click entry is back on the table.
- [x] A6 Hook rate: `pane.agent_status_changed`, `pane.focused`,
      `tab.focused`, `workspace.focused`, `tab.renamed`, `pane.moved`,
      `tab.moved`, `workspace.created` are valid hooks (link accepted them,
      2026-11-20). Record a normal stretch of use and count how often each
      fires, to choose the index refresh triggers (B1).
- [x] A5 Metadata token: report `$earmark` on a scratch workspace with
      `herdr workspace report-metadata`, add the token to a test sidebar row,
      and show Cody what it looks like.

### B. Recording

- [x] B1 Index: keep `index.json` in the state dir, one record per pane
      that has an `agent_session`, keyed by Herdr session name (from
      `HERDR_SESSION`, "default" when unset) + pane id: workspace id and
      label, tab id and label, agent, session source/kind/value, cwd,
      terminal title, last seen. Every hook refreshes it from `pane list`
      (A2: closes can't be read after the fact). `agent_detected` without
      `released` polls a few seconds until the session id appears (it
      arrives just after detection). Rebuild in the `[[startup]]` hook.
      Writes are atomic (temp file + rename) and locked (several hook
      processes run at once). Measure the hook rate (A6) before deciding
      which events refresh it.
- [x] B2 Archive on close: `pane.closed` archives that pane's record;
      `tab.closed` every record with that tab id; `workspace.closed` every
      record with that workspace id (its payload has the final label). File
      them under session name + workspace (label + id; follow
      `workspace.renamed`). One entry per session: closing a
      reopened session updates its entry instead of adding a second.
- [x] B3 Agent gone, tab kept (`/exit`): A2 showed `pane.agent_detected`
      with `released: true` and the session already cleared, so archive the
      pane's indexed record on it.
- [x] B4 Restart safety from A3: the restored panes get `released: true`
      right after `startup`, the same shape as `/exit`. The startup hook
      writes a boot stamp per Herdr session; ignore releases for panes
      that existed at boot until their deferred resume brings the agent
      back (or a grace period passes). Retest in a named session. Also: a session that becomes live again
      (reopened by Earmark, by hand, or restored by Herdr) leaves the
      archive.
- [x] B5 Title and last activity: the title from the agent's session name
      (Claude Code: the terminal title without its status glyph, or the
      transcript's summary/title line), last activity from the transcript
      file's modification time.

### C. The archive popup

- [x] C1 A `curses` TUI (stdlib): the current workspace's entries, newest
      first, each with title, agent and "last active 3 days ago". Keys:
      arrows, Enter reopen, Delete forget (with a one-key confirm), `/`
      filter, `a` toggles all workspaces, Esc/q close. Mouse: click selects,
      double-click reopens, wheel scrolls, a × on each row forgets. Works in
      a narrow popup and follows the terminal's colors (no hard-coded
      palette).
- [x] C2 Reopen: `herdr tab create --workspace <id> --cwd <cwd> --label
      <title> --focus`, then run the resume command in its pane; remove the
      entry. The workspace that was closed altogether: reopen into the
      current one, or recreate it (decide with Cody).
- [x] C3 Empty state: "Nothing archived in <workspace> yet" with one line on
      how entries get there.

### D. Cleanup and settings

- [x] D1 `config.toml` (read with `tomllib`; Python 3.11+): `keep_days =
      30`, `report_count = true`, and a `[resume]` table of commands per
      agent (`claude = ["claude", "--resume", "{id}"]`, codex, pi, ...).
      Missing file = defaults. Document every key.
- [x] D2 Pruning: drop entries past `keep_days` (by last activity),
      sessions with nothing to resume (Claude: no transcript, or one with
      only local commands such as `/exit`), and entries whose saved
      conversation is gone (Claude Code:
      `~/.claude/projects/*/<id>.jsonl`; add others where known). Runs when
      the popup opens and at startup.
- [x] D3 Resume commands for the other agents Herdr integrates (check each
      agent's real CLI; never guess a flag).

### E. Sidebar count (opt-in)

- [x] E1 Report `$earmark` ("3 archived", empty when none) per workspace
      after each archive change, unless `report_count = false`.
- [x] E2 Show Cody with the token added to his sidebar rows; he decides
      whether it stays in his own config.

### F. Tests and docs

- [x] F1 Unit tests (`python3 -m unittest`): index, archive, dedupe,
      rename, pruning, config, against a fake `HERDR_BIN_PATH` that serves
      canned JSON.
- [x] F2 A live check script for a scratch workspace (open, close, reopen,
      forget), safe to run beside Cody's real sessions.
- [x] F3 CLAUDE.md filled in: layout, how it works, working on it, platform
      facts corrected by phase A.
- [x] F4 Cody's dotfiles: `tools.yaml` entry (clone + link), the key
      binding in Herdr's tracked `config.toml`, docs.

### G. Closed workspaces (decided 2026-11-21)

- [x] G1 Keep a tab map per workspace (order, name, folder, agent
      session), plain tabs included; when a workspace disappears, record it
      as a unit in `archive["workspaces"]`. Its agent sessions are archived
      on their own too, as before.
- [x] G2 A Workspaces view in the same popup (Tab or click to switch),
      opened directly by the `open-workspaces` action: Ctrl+Space Shift+A.
      Enter or double-click restores: into a live workspace of that name,
      else a new one; tabs in order with their names and folders; agent
      tabs resume their sessions; then the record goes. × forgets only the
      grouping (its sessions stay archived).
- [x] G3 Restore brings back exactly the tabs open at close (Banana: 5 live
      and 70 archived comes back as 5 tabs, the 70 stay in its archive).
      Splits are not restored. Closed workspaces age out with keep_days.
- [x] G4 Unit tests and live_check step 5 (close + restore Gamma).
- [x] G5 Cody tries it (Ctrl+Space Shift+A).

### H. Pre-release review (2026-11-21)

- [x] H1 Python 3.9 (macOS): settings parser fallback; tests and popup pass
      under a temporary 3.9.
- [x] H2 Codex and Grok tested live (close, reopen, close again); facts
      (title, last activity, still there) for Claude Code, Codex, Grok.
      Pi and Copilot have no sessions on Cody's machine, so not tested.
- [x] H3 keep_days unset follows each agent's own retention; 30 days
      only where Earmark can't look.
- [x] H4 Speed: cache per entry (file + mtime); 300 entries under 1 ms.
- [x] H5 A reopened session is noted in its new pane at once (Codex
      reports only after the next prompt); "Restoring…" shows before it
      runs; restore leaves out sessions already open.
- [x] H6 Codex daemon bug (herdrdev/herdr#4649): resume uses
      `--no-daemon`; README notes for users.

### Release prep (go-public)

- [ ] CLAUDE.md current: status, rules, platform facts, Credits
- [ ] Then run the `go-public` skill

## Testing

- Never close or reopen Cody's real tabs. Make a scratch workspace
  (`herdr workspace create --label earmark-test`) and close it afterwards.
- A linked plugin is active in every Herdr session at once, so a bug can
  misfile real closes. The archive is Earmark's own file and never touches
  agent data; still, back up `archive.json` before risky changes.
- Unit tests use a fake `HERDR_BIN_PATH`; they never touch the running
  server.
- Popup checks need Cody's hands (real keys and clicks): ask, and say
  exactly what to press.

## Log

- 2026-11-20: Named (Earmark), branded (ear tag, Copper palette), repo set
  up. Review of existing Herdr plugins before building: herdr-agent-inbox
  is the closest (auto history per workspace, reopen with `claude
  --resume`) but stale since July and does much more; the rest are
  undo-close, park-a-tab or transcript search, which group by folder.
  Next: A1.
- 2026-11-20 late: A1 skeleton linked (popup action, recorder hooks), key
  Ctrl+Space a bound in Cody's Herdr config. A2 and A3 run in a scratch
  workspace and a named test session (`herdr --session earmark-test
  server`, deleted after): close events carry only ids, `/exit` and a
  restart both show up as `released`, plugin state is shared across
  sessions. Facts are in CLAUDE.md. The one test transcript (an `/exit`)
  was moved out of `~/.claude/projects`. Waiting on Cody: A1 (press the
  key, click in the popup) and A4 (right-click a workspace and a tab).
- 2026-11-21: Cody tested the popup (works). The sidebar count had never
  reached Herdr (CLI wants the workspace id first; fixed). Tried in Cody's
  Herdr config as a trial, not yet in dotfiles. Names: entries now keep the
  tab name, pane name and tab position; the list shows the user's name in
  bold with the agent's title dimmed beside it (`title_first = "tab"` or
  "agent"); filter matches both; reopen restores the tab's own name, or
  leaves Herdr's default label. Next: Cody's look at both. Then phase G
  (restoring a closed workspace) to discuss: with 5 live and 70 archived
  sessions, restoring the workspace should bring back the 5 as tabs and
  leave the 70 in its archive, so a workspace close must be remembered as a
  unit, separate from sessions closed one by one.
- 2026-11-21: Sidebar count trial turned off (Cody: default off is right;
  it stays opt-in through the sidebar rows). Built G (closed workspaces);
  12/12 live checks and 24 unit tests pass.
- 2026-11-22: Cody tried G (works). Plan items A-G ticked. Fixed: restoring a
  workspace no longer resumes a session that's already open elsewhere.
  Pre-release review in progress (see the release prep list).
- 2026-11-21 (later): pre-release review H1-H6 done (see phase H). Unit
  tests 35, live check 20/20 with Codex and Grok. Found that a Codex
  app-server daemon my first Codex test started still carries the test
  session's socket; stopping it was left to Cody.
- 2026-11-21: go-public stage 2. README written; media shot in a staged
  named session (`earmark-demo`, HERDR_CONFIG_PATH pointing at a copy of
  Cody's Herdr config without the hostname in the tab bar; demo project in
  /tmp/demo with real one-exchange Claude/Codex/Grok sessions; Claude's
  status line hidden with a project .claude/settings.json; Claude
  transcripts and closed-workspace times backdated for realistic ages).
  All driven by Herdr's CLI and socket API (popup.close), no scripted
  input. The shoot found popup layout bugs (titles running into details,
  a doubled "Earmark", details dropped when narrow, help cut mid-word,
  space before …), fixed in ui.py; popup size now 90% x 70%. Codex reopen
  is `command codex --no-daemon resume`, so a user's codex alias or
  function can't double the flag.
