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
      rename, pruning, config (and since strict review 1, `herdr.py`
      itself against a fake `HERDR_BIN_PATH` program), against a fake that serves
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
      Pi and Copilot have no sessions on the maintainer's machine, so not tested.
- [x] H3 keep_days unset follows each agent's own retention; 30 days
      only where Earmark can't look.
- [x] H4 Speed: cache per entry (file + mtime); 300 entries under 1 ms.
- [x] H5 A reopened session is noted in its new pane at once (Codex
      reports only after the next prompt); "Restoring…" shows before it
      runs; restore leaves out sessions already open.
- [x] H6 Codex daemon bug (herdrdev/herdr#4649): resume uses
      `--no-daemon`; README notes for users.

### Release prep (go-public)

- [x] CLAUDE.md current: status, rules, platform facts, Credits
- [x] Then run the `go-public` skill: 1.0.0 public and released
      2026-11-21; listed in Herdr's marketplace index
      (assets.herdr.dev/plugins/index.json) the same day.

### I. Suspend tabs in place (1.1, decided 2026-11-25)

The maintainer runs dozens of Claude Code sessions (~300 MB each). Some he's
working with, some wait on him while he's away for hours or days, and some
are done. Herdr shows the first two, Earmark's archive holds the last. The
middle group (waiting, but not soon) sat in memory, and archiving them would
bury the one unfinished session among the finished ones. Suspend keeps the
tab where it is, ends the agent to free its memory, and leaves a tiny
placeholder showing what was on screen (or a notice) with a prominent
"Enter to resume", which runs the agent's resume command in that same pane.
Like Edge's sleeping tabs.

Cody's calls:
- **In place:** the tab stays, with its name; not a separate list.
- **Settings** (`[suspend]` in config.toml; names are ours):
  `when = "off" | "manual" | "time" | "memory" | "count"` (shipped default
  "off"), `idle_minutes = 60` (time),
  `memory_below = 20` (percent of memory available; memory mode, Linux),
  `keep_awake = 8` (count: the N most recently used agents stay awake),
  `resume_on = "enter" | "view"` (default enter), `show = "frozen" |
  "notice"` (default frozen). Both views show "Enter to resume"
  prominently.
- **Manual key** (`suspend` action; Cody: Ctrl+Space Ctrl+S, since Ctrl+Space
  s is Herdr's settings and z is zoom; first Shift+S, changed the same
  evening) works in every mode but off; on a suspended tab it resumes.
- **The parking rule:** never suspend an agent that's working, or that has a
  program running under it (tests, builds, background commands), in every
  automatic mode.
- **Loops:** a Claude waiting on a /loop wake-up or a scheduled task stays
  awake (read from its transcript). Other agents' timers are a known limit.

What the review of six existing plugins taught (2026-11-25; herdr-autopark,
herdr-memory-guard, herdr-hibernate, avocado-park, claude-hibernate,
herdr-shelve, herdr-rest, herdr-agent-hibernate; ideas only, no code):
- Borrowed: frozen view from `pane read --format ansi` taken before the
  agent stops, replayed on the alternate screen with the agent's own input
  box cut off (autopark); draft detection inside Claude's prompt box with
  faint/italic placeholder text dropped (autopark, claude-hibernate);
  pending wake-ups and crons from the transcript, counted only since the
  process started (autopark, claude-hibernate); shell children
  (`shell-snapshots`) mean background work, MCP servers don't; write the
  record before stopping, clear it only when the session is seen live again
  (shelve, rest); re-check everything right before acting, identity by pid
  + start time, SIGTERM, never SIGKILL, back off after a failed stop (rest,
  memory-guard); placeholder is a child of the pane's shell (hibernate),
  typed as `placeholder && resume command` so the shell starts the agent; MemAvailable with 20/25 % hysteresis
  (memory-guard); resume keeps launch flags and the last permission mode
  (claude-hibernate); re-arm placeholders after a Herdr restart only into a
  bare shell in the same pane (autopark, rest).
- Avoided: typing `/exit` or keys into the agent (lands in drafts, dialogs,
  the agents panel); daemons and systemd units that outlive Herdr (checks run
  from Earmark's existing hooks instead, at most once a minute, in a
  short-lived worker); waking on every focus flick (view mode needs the pane
  to stay focused ~1 s); suspending `done` agents (the unseen-result badge
  would vanish; later reversed by Cody, R26: `suspend_unseen`, default on);
  killing whole process trees; acting on a stale decision.

- [x] I1 Settings: `[suspend]` table, validated, documented in config.py and
      `earmark.py check`; shipped default off.
- [x] I2 Facts per agent pane: pid + start time, launch argv, CLAUDE_CONFIG_DIR
      (from the process), last activity (transcript, subagents, focus,
      status changes, start), busy children, draft text, pending timers,
      Claude's own registry (status, Remote Control).
- [x] I3 The worker: eligibility per mode (time / memory / count), the
      re-check, record first, screen capture, SIGTERM to the agent (and its
      launcher; never its process group: R2), wait, placeholder typed into
      the bare shell. Manual path with clear refusals (Earmark's popup or
      Herdr's toasts: R64, R69).
- [x] I4 The placeholder (`earmark.py suspended`): frozen view or notice,
      Enter resumes (the shell runs the resume line, in the saved folder,
      with options and permission mode), Ctrl+C leaves (the session goes to the archive), resize, a
      session opened elsewhere is never resumed twice.
- [x] I5 Hooks: no archiving of a session Earmark suspended; a closed
      suspended tab is archived; closed workspaces remember suspended tabs;
      live again clears the record; a resume that never came back is
      archived; resume on view; re-arm after a Herdr restart.
- [x] I6 Unit tests for each of the above; isolated live test (a throwaway
      HOME running its own Herdr, so Cody's sessions are never touched).
- [x] I7 README, CLAUDE.md, version 1.1.0; Cody tried manual, then time
      (time mode from 2026-11-26). Released as 1.1.0 on 2026-11-26.

### J. CLAUDE_CONFIG_DIR differing between the shell and Herdr's server

- [x] J1 Read CLAUDE_CONFIG_DIR from the running agent's own environment
      (Linux `/proc/<pid>/environ`, macOS `ps eww`) when its session is first
      noted; keep it with the note and the archive entry; every look into
      Claude's files uses it. README's known-limit note updated.

### Strict review 1 (2026-11-25)

Reports (kept outside the repo): `earmark-review1-safety.md` and
`earmark-review1-fit.md` (bar: `BRIEF.md`, `REPORT.md` there, the
strict-review checklist). Both reviewers found the engine's design sound
(SIGTERM only, record first, last look, Enter only into the placeholder, no
daemon) and the tests weak where it matters: 27 of 27 and 14 of 36 of their
own mutations survived; our 35 "all caught" were re-plants of fixed bugs.
Every finding below was checked against the code; most were reproduced by
the reviewers' harnesses. Time mode paused on the maintainer's machine (manual) until
these are fixed.

- [x] R1 high: the idle clock counts from arriving at a tab, not leaving it
      (`focused_at` only on that pane's focus event): a tab read for an hour
      is suspended a minute after switching away. Stamp the focused pane on
      every hook and the pane that loses focus. (safety F1, fit M1)
- [x] R2 high: processes in the agent's process group that aren't its
      descendants (a `nohup … &` server) aren't counted busy, and `killpg`
      signals them. Count anything in the foreground group outside the
      agent's chain and descendants as busy; signal only the chain from the
      group leader to the agent, never the whole group. (safety F2, F13)
- [x] R3 high: tests don't cover the facts the parking rule rests on
      (`look()` mocked everywhere; `wait_for_key`, hook scheduling,
      `herdr.py` never run; count-mode numbers inside the slack; fakes
      that flip both halves of a condition; the plain-shell rule untested).
      Test each; add the reviewers' surviving mutations to
      `tests/mutations.md` with a runner in the repo. (fit H1, safety T1-T6)
- [x] R4 high (release blocker): development commits carried private
      details, so the 1.1 history was squashed into one commit before it was
      pushed, then the go-public privacy scan ran over every commit.
- [x] R5 medium: forgetting a Herdr session quiet for 30 days deletes its
      suspended records unarchived. (safety F3)
- [x] R6 medium: a stale Claude registry file whose pid was reused counts as
      "open elsewhere", and the record is dropped unarchived: check the start
      time; never drop a record without archiving it. (safety F4)
      Round 2 found three more paths that dropped a record after the signal
      (R31, R41, R42), fixed there.
- [x] R7 medium: "never resumed twice" goes ahead when Herdr can't be asked:
      fail closed, and let the placeholder retry. (safety F5)
- [x] R8 medium: the key suspends where it can't read the prompt (Grok, Pi,
      Claude's `!` mode), losing unsent text; the suite asserted that as
      intended. Ask for a second press within seconds. (safety F6, fit
      claim 3)
- [x] R9 medium: the placeholder finds its state only through a hard-coded
      folder (panes don't get HERDR_PLUGIN_STATE_DIR; XDG_STATE_HOME); a
      placeholder that never comes up is retyped every minute (also shells
      that can't run `a && b`: nushell, elvish, csh). Pass the dirs on the
      line, refuse unsupported shells before stopping, back off after a
      failed start. (safety F7, fit M3, M4)
- [x] R10 medium: resume keeps 14 whitelisted Claude flags and drops the
      rest (`--disallowedTools`, `--append-system-prompt`, Codex's
      `--sandbox`), and inline environment. Keep every known flag; refuse
      automatic suspends (key: second press) for unknown flags Earmark
      can't bring back. (safety F8, fit M2) The launch-environment half was
      never built (round 2, C1): inline variables other than
      CLAUDE_CONFIG_DIR stay a documented limit; wrappers are refused (R36).
- [x] R11 medium: an arm can race Herdr's own restore, and two arms
      (`claim=False`) can race each other. Always claim; don't arm while
      Herdr still lists the agent; after a stop whose release timed out,
      leave the placeholder to the next check. (safety F9, fit L6)
- [x] R12 medium: cost: memory mode looks at every agent before knowing it
      can act; each look reads the transcript tail twice (title, permission
      mode) though the decision needs neither; on macOS the timer cache
      never hits (start time from etime) and memory mode runs a worker
      every minute that can never act. (fit M5)
- [x] R13 medium (docs): time mode can't act while Herdr is quiet, then acts
      at the first event when you come back. Say so in Known limits. (fit
      M6, safety F17)
- [x] R14 low: `unmark_tab` passes a user label starting with `-` to
      Herdr's argv (its global-flag scan); an empty label gets a mark with
      no space that never comes off. (safety F10, fit L1, L2)
- [x] R15 low: a stale "suspended" record over a running agent swallows the
      user's `/exit` (not archived). (safety F11)
- [x] R16 low: reopening from the archive or restoring a workspace ignores
      the entry's CLAUDE_CONFIG_DIR. (safety F12)
- [x] R17 low: the Python 3.9/3.10 settings parser mangles non-ASCII
      (`unicode_escape` on UTF-8; arrays unescaped). (fit L3)
- [x] R18 low: the placeholder wakes every second and repaints every 30 s.
      (fit L4)
- [x] R19 low: one-shot CronCreate tasks keep an agent awake for the life of
      its process; timers fail open if the start time can't be read.
      (fit L7, safety F18)
- [x] R20 low: a failed worker start loses the re-arm request; settings are
      read once per worker. (fit L8, L9)
- [x] R21 low: missing suspended panes right after a restart (a partial
      snapshot) are archived as closed. (safety F19)
- [x] R22 low: a stop with no placeholder reports "can't suspend this tab".
      (safety F16)
- [x] R23 low: tests read the user's real Earmark config (and could read
      real agent folders); `unittest.main()` mid-file; an index rewrite and
      fsync on every hook. (safety T7, fit L11, L12) Only partly: note `seen`
      and focus stamps still rewrote it every hook (round 2, R40).
- [x] R24 low: dead code (`exec_argv` and its test, `herdr.time_ns`),
      duplicates (`ago`, column width, `fit`, meminfo, the session-record
      literal, `current()`). (fit design)
- [x] R26 Cody's ask (2026-11-25, mid-review): automatic modes also take
      "done" agents (an unseen result) unless `suspend_unseen = false`; the
      placeholder says the answer wasn't read.
- [x] R25 claims: README "only its own two folders", "the flags it was
      started with", "never ... unsent text", "your last look", "read on
      from where it stopped", "acts like manual" elsewhere, "about 25 ms";
      CLAUDE.md test and mutation counts, "never passes a name starting
      with `-`"; PLAN I4 still describes exec; F1's fake Herdr binary
      doesn't exist; README's live_check instructions skip the isolated
      HOME; "a session is never lost", "only the agent's own process".
      Also known limits: a second attached client's tab in view isn't
      protected; macOS process names (README: an npm-installed Claude may
      show up as `node` there; added in round 2). (both)

### Strict review 2 (2026-11-25)

Reports (kept outside the repo): `earmark-review2-safety.md` and
`earmark-review2-fit.md`. Both found most of R1-R26 really fixed and the
design careful; both found the tests still thin where it counts (21 of 60
and 45 of 58 of their own mutations survived; the repo's 83 are re-plants).
Checked against the code; most reproduced in the reviewers' harnesses.
`suspend_unseen = true` by default is Cody's call (R26), a deliberate
deviation from the audit bar, documented.

- [x] R27 high: after a restart, re-arm can race Herdr's own deferred
      restore (the session isn't listed while it waits) and type into a
      starting agent; the key's force path could create the condition.
      Wait while the pane's note shows the same session until the boot grace
      passes or the agent is seen; the key no longer types while Herdr lists
      the agent. (safety F1)
- [x] R28 high: tests. Both reviewers' survivors: signal is SIGTERM; the
      30-day forget keeps an active session; note_config_dirs through apply
      to the archive; a hang counts as a failure (EarlyKeyTests); popup
      keys and mouse; the draft parser's box choice and style reset; real
      /proc parsing; shells deeper under the agent; the shell-safety
      checks; Ctrl+C to the archive through placeholder.main; a mode change
      mid-check; the under-lock re-check; no resume command; rearm once per
      restart; the key's suspended branch; wake_on_view's state guard;
      MAX_PER_CHECK; the terminal put back. Their survivors join
      tests/mutations.md. (fit H1, safety tests) Done: both reviewers' 118
      mutations are in tests/mutations.md (66 survived at first), plus one
      per fix R27-R51; tests/test_review2.py; all 230 caught.
- [x] R29 medium: a split beside the pane in use is on screen too: stamp
      every pane of the tab in view, and all of a tab's panes when it's
      left. (safety F2)
- [x] R30 medium: kept option values with control characters, quotes or
      backslashes are typed unchecked: treat them as options Earmark can't
      bring back. (safety F3)
- [x] R31 medium: an agent slower than 15 s to exit after SIGTERM lost its
      record; after a signal a record is never removed (a hook finishes it).
      (safety F4)
- [x] R32 medium: a `claude` alias (bypass) could widen the resumed
      session's permissions: resume with `command claude`. (safety F5)
- [x] R33 medium: an agent started from a nested shell (`nix develop`,
      `bash` in zsh) was stopped and stranded: refuse it. (safety F6)
- [x] R34 medium: the first event after a laptop sleep or a long quiet spell
      suspended every idle agent: no automatic suspends for a few minutes
      after Herdr comes back from a long silence. (safety F10)
- [x] R35 medium: Ctrl+U and the placeholder line could go into a tab the
      user switched to meanwhile (after a stop, after a restart); the bare
      shell wasn't re-checked after the claim. Skip the tab in view (the key
      excepted) and look again after claiming. (fit M2, safety F9)
- [x] R36 medium: an agent started through a wrapper (`aws-vault exec --
      claude`) was signalled and resumed without it: a wrapper Earmark can't
      bring back counts like an unknown option. Inline environment stays a
      documented limit (PLAN R10's "refuse launch environment" was never
      implemented: claim corrected). (fit M3, safety C1)
- [x] R37 medium: placeholders were re-armed by pane id alone: also check
      the tab still matches, else archive the record. (fit M6)
- [x] R38 medium: a session Claude deleted while suspended still offered
      "Enter to resume": the placeholder says it's gone and resumes nothing.
      (fit M5)
- [x] R39 medium: any tab named "💤 …" was renamed on every hook, suspend
      off or not: only tabs Earmark marked are unmarked. (fit M1)
- [x] R40 medium: index.json was still rewritten on every hook (note
      `seen`, focus stamps): throttle them. (fit M4, R23's claim)
- [x] R41 medium-low: a new claude in a pane Herdr stale-lists ended the old
      record unarchived: Claude's registry tells the session; a different
      one archives the old record. (safety F7)
- [x] R42 medium-low: the worker signalled after a hook had ended its
      "stopping" record: re-read the record right before the signal.
      (safety F8)
- [x] R43 low-medium: manual mode never noticed an agent Herdr relaunched;
      the key now does. (safety F11)
- [x] R44 low: the key re-checks status right before the signal. (F12)
- [x] R45 low: archive reopen and workspace restore check Claude's registry
      (never resumed twice). (F13)
- [x] R46 low: restore brings a suspended tab back with its record's options
      and mode. (F14)
- [x] R47 low: a Claude whose folder Earmark can't read isn't suspended
      automatically (timers unknown). (F15)
- [x] R48 low: for agents Earmark can't name, the key refuses unless the
      foreground leader is that agent. (F16)
- [x] R49 low: the restart grace also covers notes and closed-workspace
      records. (F17)
- [x] R50 low: timers.json per Herdr session, written under the lock. (F18)
- [x] R51 low: a broken config.toml keeps working settings (no pruning, no
      automatic suspends until fixed); cost (chunked transcript reads, no
      look at agents that can't qualify yet, placeholder imports); dead code.
      Also the placeholder line's own paths (Python, Earmark's folder, state
      and settings folders, session name) checked before anything is
      stopped (L9). (fit lows)
- [x] R52 claims: README's Herdr prefix (Ctrl+B by default), "right before
      acting", a command after the agent (`claude; exit`), restart wording;
      config.py's docstring on unseen results; CLAUDE.md counts; PLAN R6,
      R10, R23 wording. (both)

### Strict review 3 (2026-11-26)

Reports (kept outside the repo): `earmark-review3-safety.md` and
`earmark-review3-fit.md`. Both: the engine beats the eight audited plugins
on stopping agents, keeping sessions and typing into panes; not yet on fit
and honesty. Three round 2 fixes don't hold (R27, R35, R51); 15 of the
safety reviewer's 31 and 22 of the fit reviewer's 83 own mutations
survived. Checked against the code and Herdr's docs.

- [x] R53 high: R27's guard reads the pane's note, which the first hook
      after a restart deletes (apply's own-stop branch), and the key and the
      automatic check's re-arm pass skip it. Keep the evidence on the record
      (Herdr listed the stopped session in its own pane) and refuse every
      arm during the boot grace while it's there. Test with the real hook
      sequence. (safety F1)
- [x] R54 medium: opening the popup prunes with defaults while config.toml
      is broken; an unreadable or dangling config counts as no config; top
      level values (`keep_days = "0"`, `-1`, a mistyped key) are never
      flagged. No pruning anywhere while broken; only a missing file means
      defaults; every key and value checked. (safety F2, fit M1)
- [x] R55 medium: arm doesn't look at the tab in view again after its
      claim. (safety F3)
- [x] R56 medium: the key stops an agent whose status is `unknown`, and a
      Claude whose folder Earmark can't read (no timer, status or Remote
      Control check) on the first press: both ask for a second press.
      (safety F4)
- [x] R57 medium: a failed CLAUDE_CONFIG_DIR lookup records "" (forces
      ~/.claude) and never retries; it should record nothing and ask again.
      (safety F5, fit L4)
- [x] R58 medium: a Codex started without --no-daemon may be listed under
      another tab's session (herdrdev/herdr#4649): never suspend it.
      (safety F6)
- [x] R59 low: a transcript line longer than the 8 MB read window stalls
      the timer reader for good: skip it. (safety F7)
- [x] R60 low: the placeholder takes marks off another named session's
      list: use its own session. (safety F8, fit L2)
- [x] R61 low (nits): arm types only into a pane whose foreground process
      is a supported shell; mark_tab lists the tab before renaming it;
      config docstring and README's `[resume]` example keep `command`.
      (safety nits)
- [x] R62 tests: the safety reviewer's 31 mutations join
      tests/mutations.md (15 survived: in-view by tab, the launcher's start
      time, CLAUDE_CONFIG_DIR quoting, Enter into this placeholder only, the
      return grace's length, drafts starting with "Try", rearm_all's
      deadline, check_pane's restart, "resumed" needing the session,
      drop_screen's folder check, screen file modes, the key with suspending
      off, STOP_STALE); mutate.py confirms a timeout like any other kill.
      (safety tests)
- [x] R64 high: every message from the key goes through `herdr
      notification show`, which follows `[ui.toast] delivery`, off by
      default: on a default Herdr refusals never show, and a second press
      confirms a warning nobody saw. Messages and the confirmation go
      through a small Earmark popup instead; confirming takes `y` there.
      (fit H1) Done: earmark/message.py, a second `[[panes]]` entry; the
      second-press window is gone. Live: the key on a plain shell opened
      the popup with its message, which closed by itself; an unanswered
      question closed after a minute and suspended nothing. Herdr can't
      send keys into a plugin popup, so `y` itself is tested on a pty, not
      live. Cody (2026-11-26): the popup takes the keyboard; keep it the
      default, but `[suspend] messages = "toast"` gives Herdr's toasts and
      the second press, used only where Herdr's toasts aren't known to be
      off (`earmark.py check` says when it falls back).
- [x] R65 medium: tests for the fit reviewer's 22 survivors (the last
      look's "blocked", R42's state comparison, the key with suspending
      off, restore and Claude's registry, layouts keeping config_dir, the
      real MemAvailable reading, TIMER_GRACE, `behind` through look(), the
      memory threshold, the 30-day forget, last_active, closed workspaces
      ageing, ...); their list joins tests/mutations.md. (fit M2)
- [x] R66 low: index.json still rewritten on every hook while a tab is
      suspended (`seen_at`), and the timers file on every check: throttle
      and skip unchanged writes; the R40 test gets a suspended tab. (fit L1)
- [x] R67 low: popup clicks on the bottom rule or help line act on rows
      that aren't on screen. (fit L3)
- [x] R68 low (design): the shell-unsafe character class defined three
      times; the placeholder still loads sqlite3 (through session_facts).
      Later: one-call `herdr api snapshot`, `layout.export/apply` for
      splits, restart detection by parent pid. (fit design)
- [x] R63 claims: README "a minute" for Herdr's restore (true once R53 is
      fixed), "not busy" right before the signal (Herdr's status), "about 15
      seconds" per tab (about 30), the key and timers; PLAN R27, R35, R51
      ("keeps working settings": a syntax error means defaults meanwhile);
      core.py's "1.0 behaviour" comment; README "the key asks / says so"
      (R64), "with the options it was started with" (the ones Earmark
      knows); PLAN R40; CLAUDE.md's "loads neither curses nor sqlite3".
      Before publishing: private details out of PLAN (done with R4).
      (safety claims, fit claims)

### Strict review 4 (2026-11-26)

Reports (kept outside the repo): `earmark-review4-safety.md` and
`earmark-review4-fit.md`. Safety: beats the eight on how it stops agents,
where it types and lifecycle; not yet on Claude's timers, the permission
mode on resume (R70), and resumes that can come back; 3 of its 30
mutations survived. Fit: no high; the engine
passes every class in the audit; short of "better than all" on an opt-in
setting, one permission case, a steady per-minute cost and tests around
the parking rule (41 of 54 of the reviewer's own mutations survived).

- [x] R69 medium: toast mode guesses from Herdr's config whether a toast
      showed; Herdr's `notification.show` reply says (`shown`, `reason`).
      Read it: not shown (or no reply) falls back to the popup, and a
      second-press window starts only after a toast that was shown.
      (fit F1)
- [x] R70 medium: the permission mode is read from the transcript's last
      256 KB only; a session switched out of bypass came back bypassing
      when the last mode record was further back. Track the mode in the
      timers' full incremental read; unknown with a bypass launch resumes
      without bypass (`--allow-dangerously-skip-permissions`). (fit F2)
- [x] R71 low: index.json still rewritten on every hook at the documented
      rate (the tab in view restamped every 30 s; `last_event` with
      suspend off). The tab in view needs no periodic stamp (stamped when
      left); `last_event` only with an automatic mode. (fit F3)
- [x] R72 low: the minute check asks Herdr about every suspended tab
      (`rearm_pass`) and scans /proc even when nothing can qualify: remember
      each placeholder's pid and start time and check it locally; build the
      process table only when a look is needed. (fit F4)
- [x] R73 low: restart detection by the hook's parent pid: if hooks ever
      get a new parent each time, fall back to the startup hook alone.
      (fit F5)
- [x] R74 low: after `y` the popup holds Herdr's UI for the whole suspend:
      hand it to a worker and close; the hint goes first, the body is cut
      to fit small popups. (fit F6)
- [x] R75 low: README's `[resume]` example without `command` (R61 not
      done); an unreadable environment still recorded as "" (R57 half
      done); macOS `ps eww` values with spaces. (fit F7, F8)
- [x] R76 low: `report_count = false` leaves the last tokens shown; the
      boot grace ignores Herdr's `startup_per_agent_delay_ms`; Known
      limits: a suspended tab leaves Herdr's agent panel and notifications;
      an MCP server kept behind a shell makes its agent always busy. (fit F9)
- [x] R77 tests: the reviewer's 54 mutations join tests/mutations.md (41
      survived: the popup's Enter written before raw mode, no-rewrite tests
      without a tab in view, R22 with the record mocked away, the worker
      lock, the arm claim's length, keep_days = 0 applied, the curses
      popup's keys, memory mode's loop, the placeholder start wait, the
      reused-pid tolerance, AWAY_GAP's length, report_count, tab_mark's
      length, ...). (fit tests)
- [x] R78 claims and design: README "permission mode it was last in"
      (R70), "memory mode looks at nobody" (R72), "300 sessions open in
      under a millisecond" (checked, not opened); PLAN I3, Shift+S, "done
      agents avoided"; pre-1.1 mark migration removed (deployed); aliases;
      a double import. (fit claims, design) Done, except a few aliases
      (`suspend.session_state`, `placeholder.width/fit/ago`, `ui.ago`); R77: the reviewer's 61
      mutations (one equivalent dropped) and one per fix joined
      tests/mutations.md; every survivor got a test (one survivor was our
      own R29 test running on a clock in the future).

- [x] R79 high: Herdr's listed session is trusted over Claude's own
      registry for the process: with Herdr stale-listing session A while the
      claude there runs B (waiting on a /loop), A's transcript is read, B
      is stopped, A is resumed, B is lost. A registry session that differs
      from Herdr's refuses both modes. (safety F1)
- [x] R80 medium: toast mode: a double tap (0.3 s) confirms; a question
      goes by toast only with Herdr's in-app delivery (a terminal or system
      notification may not be seen), and a second press must come at least
      a second after. (safety F3)
- [x] R81 medium-low: a CronDelete cancelled whichever task; match the
      deleted task to a create (its result names the id), an unmatched
      delete counts as nothing (the agent stays awake). (safety F4)
- [x] R82 medium-low: a Claude folder (or a folder) that can't be typed
      safely was dropped from the resume line and the resume failed:
      refuse both modes. (safety F5)
- [x] R83 low-medium: an empty or partial pane list (tabs without panes)
      archived every live session and suspended record: such a snapshot
      closes nothing. (safety F6)
- [x] R84 low: the automatic re-arm could type over a half-typed line (Ctrl+U
      kills only before the cursor): Ctrl+E first, and the periodic re-arm
      types only into a shell idle for a whole check (Herdr's pane
      `revision` unchanged); the key always may. (safety F7)
- [x] R85 low: a stray Enter could reach the resuming agent: the
      placeholder flushes pending input before it exits; the message popup
      flushes keys typed before its question. (safety F8, nit)
- [x] R86 low: a running check ignored a clock jump (laptop asleep
      mid-check) and a config.toml broken mid-check: both stop it. A /loop
      wake-up due while Herdr was quiet counts the quiet time as not
      passed (Claude's timers stop while the machine sleeps). (safety F9,
      F10, unverified risk)
- [x] R87 low: a missing Claude registry file read as "all clear": refuse
      automatic, ask on the key; a start time that can't be read fails the
      identity check. (safety F12, nit)
- [x] R88 low (nits): a damaged index renamed outside the lock; toast asks
      never pruned; wall-clock deadlines in the session wait and the
      restart re-arm get iteration bounds. (safety nits)
- [x] R89 tests: the safety reviewer's 30 mutations join the list (3
      survived: the record's `at` identity, `last_event` refresh, the
      placeholder's accepted states). (safety tests) Its list wasn't kept;
      the 3 survivors were written down from its report, with tests.
- [x] R90 claims: README "clears anything left unsent", "types only into a
      shell at its prompt" (R84), "Enter only into the placeholder" (R85),
      "never ... a /loop" (R79, R81), toast mode vs `y`; Known limits:
      `command claude` needs Claude Code on PATH (an alias-only install
      isn't resumed). (safety claims, unverified risk)
- [x] R91 live check: does Claude draw a pasted-text chip in faint or
      italic (which the draft parser skips)? Paste into a real prompt in the
      isolated Herdr. (safety unverified risk) Checked 2026-11-26: Claude
      2.1.332 draws "[Pasted text #1 +5 lines]" unstyled, so the draft
      reader sees unsent text and nothing is suspended.
- [x] R92 tooling: tests/mutate.py caps each suite run's memory (a
      reviewer's hung mutant grew to 13.7 GB on the maintainer's machine when its own
      guard blocked the timeout). (safety incident)

### Strict review 5 (2026-11-26)

Reports (kept outside the repo): `earmark-review5-safety.md` and
`earmark-review5-fit.md`. Safety: the claim mostly holds; one high
(recreated sessions), three classes partly present (pane ids trusted,
timers after a sleep, accidental confirmation); 2 of its 56 mutations
survived. Fit: no high; the engine clears every class; short on test
quality (33 of 85 of its own mutations survived; the suite read the real
Herdr config) and a few quiet failures.

- [x] R93 high: a recreated named session reuses pane and tab ids, and
      the restart re-arm typed an old placeholder into the user's new
      shell (R37 checked the tab id only). Records keep their tab's name,
      number and workspace name current; a placeholder goes back only into
      a tab that matches, else the session goes to the archive. (safety F1)
- [x] R94 medium: a /loop wake-up pushed back by a sleep during the wait
      (not only one due inside it) counted as over; the key never applied
      the rule. Count the machine's suspended time since the wake-up was
      read (Linux: CLOCK_BOOTTIME - CLOCK_MONOTONIC) and any quiet spell
      since it was scheduled; the key uses the same look. (safety F2)
- [x] R95 medium-low: toast mode: the second press's time came from its
      worker, not the key: pass the press time; a press before the toast
      never confirms. (safety F3)
- [x] R96 low: a record dropped (unarchived) because another pane listed
      its session, which can be stale; same for a "stop failed" listing:
      for Claude, Claude's registry must confirm the session runs. (safety F4)
- [x] R97 low: an unknown Claude folder resolved differently in the worker
      and the placeholder, which then dropped the record: the placeholder's
      "conversation gone" check needs a known folder. (safety F5)
- [x] R98 low: a user's own /exit during the last look became a suspend:
      an agent gone before Earmark signalled it exited on its own (archived
      as exited). (safety F6)
- [x] R99 low: with no pane reporting focus, the in-view rule failed open
      for stops: no automatic stop when Earmark can't tell what's in view.
      (safety F7)
- [x] R100 low: a NOT_YET stop didn't mark the record `herdr_listed`.
      (safety F8)
- [x] R101 low: in manual (and off) mode a placeholder that missed the
      restart window stayed missing until the key; a recent failed start
      blocked the restart re-arm: hooks start a re-arm pass at most once a
      minute while a placeholder is missing; restarts ignore the backoff.
      (safety F9)
- [x] R102 low (nits): the popup ignores keys for a moment after its
      question appears; the unsent-text check is repeated right before the
      signal; a transcript rewritten to the same size or larger is read
      again; the missing-registry doubt names Remote Control. (safety nits)
- [x] R103 tests: the sleep rule through look(); the stop-failed guard's
      `agent`; both ids reused; the press time. (safety tests)
- [x] R104 claims: README "never ... /loop" (R94), suspend.py "never
      dropped without a trace" (R96, R97), PLAN R37/R80/R86, README's order
      of the screen copy. (safety claims)

- [x] R105 medium: the suite read the user's real Herdr config
      (`HERDR_CONFIG_PATH` not isolated): one toast test passed only because
      of the maintainer's own setting. `_isolate` points it at a temp path.
      (fit F1)
- [x] R106 medium: the command-line layer and several UI paths untested
      (`--rearm`, `--accept`, the startup default, Shift+A's view, Delete
      in the Workspaces view, ...): the reviewer's 85 mutations join the
      list, each survivor gets a test. (fit F2)
- [x] R107 medium: short unsent replies ("y", "ok") untested. (fit F3)
- [x] R108 low-medium: a typo in config.toml stopped automatic suspends and
      pruning with nothing where the user looks: the hook logs it once per
      problem, and the archive popup says so. (fit F4)
- [x] R109 low: NOT_YET promised "the next check" in manual mode (R101 makes
      it true; the wording says "shortly"). (fit F5)
- [x] R110 low: a closed tab's mark stayed listed; a reused tab id lost a
      user's own "💤" name: marks of tabs Herdr no longer has are dropped.
      (fit F6)
- [x] R111 low: an answer arriving long after the press popped up and took
      a keystroke: after a few seconds, a toast Herdr shows is enough.
      (fit F7)
- [x] R112 low: Codex suspend never ran live: README says so. (fit F8)
- [x] R113 claims, cost, nits: README nested shell (refused, not asked),
      the screen copy's order, `messages` with terminal/system delivery,
      `keep_awake`; CLAUDE.md Ctrl+U, test_review3's range, the status
      date; restart clears empty tokens; the popup prunes on every
      keystroke; settle_now loads the archive with nothing suspended; an
      unused parameter; the restore delay's default (100 ms); a missing
      `revision` fails closed; CODEX_HOME read from the server. (fit)

### Strict review 6 (2026-11-26)

Reports (kept outside the repo): `earmark-review6-fit.md` and
`earmark-review6-safety.md`. Neither reviewer found a critical or high.
Fit: the engine clears every class; 26 of its 50 own mutations survived.
Safety: beats the eight on most classes; three partly present (unsent
text, Claude's timers, pane ids across a recreated session); 6 of its 35
own mutations survived. Round 6 meets "no critical or high"; its mediums
touch unsent text, so they're fixed and a round 7 confirms.

- [x] R114 medium: the unsent-text parser read an extended colour's operands
      (`38;5;3`, truecolor 2 or 3) as faint or italic, so typed text in such
      a colour read as an empty prompt. Parse SGR properly. (fit M1)
- [x] R115 medium: the key refused big Claude sessions ("hasn't read its
      whole transcript yet": 8 MB a press; a 72 MB one needed nine): read
      on until caught up, within a time budget. (fit M2)
- [x] R116 low: parent-pid restart detection, once off, never came back:
      it comes back after six hours. (fit L1)
- [x] R117 low: vi-mode shells keep text after the cursor (Ctrl+E is no
      motion there): Known limits. (fit L2)
- [x] R118 low: a late answer on a default Herdr (toasts off) took the
      keyboard: a late popup doesn't take focus. (fit L3)
- [x] R119 low (cost): memory mode starts a worker every minute while memory
      is fine; placeholders redraw every minute even when nothing changed.
      (fit L4)
- [x] R120 low: the message popup wrapped by characters, not columns (CJK
      overflowed). (fit L5)
- [x] R121 low: killed test runs leaked temp folders: stale ones are
      removed at the next run. (fit L7)
- [x] R122 tests: the reviewer's 50 mutations join the list (26 survived:
      colour codes in drafts, the view-resume dwell, workspace renames and
      the closed-workspaces view across named sessions, the restart
      thresholds, the cursor restored, keep_days from last activity,
      report-metadata's seq, a source-string test). (fit tests)
- [x] R123 claims: CLAUDE.md `timers.json` (one per session), `suspend.unmarked`
      (`core._unmarked`); README "no background process" (placeholders);
      PLAN R63 (its "before publishing" part is a release step), R78's
      aliases (partly). (fit claims)

- [x] R124 medium: a typed Claude draft shaped `Try "..."` read as an empty
      prompt (a fallback for a hint whose styling was lost): such unstyled
      text is now a doubt (automatic modes refuse, the key asks). (safety F1)
- [x] R125 medium: durable scheduled tasks (CronCreate's persist option,
      `<project>/.claude/scheduled_tasks.json`) survive restarts, but only
      this process's calls were counted: tasks in that file keep the agent
      awake. (safety F2)
- [x] R126 medium: R93 matched a recreated session's tab with Herdr's
      default names: also compare the shell's folder recorded when the
      placeholder was typed, and after a restart that brought back few of
      the session's panes, archive rather than re-arm. (safety F3)
- [x] R127 low: the periodic re-arm typed into a shell the user used and
      left: only a shell untouched since it first came back (Herdr's
      revision) gets the placeholder automatically. (safety F4)
- [x] R128 low: the popup's `y` could come from ongoing typing: `y` then
      Enter. (safety F5)
- [x] R129 low: a real /exit inside the restart grace wasn't archived while
      the tab stayed open: after the grace, an agentless boot pane is
      archived as exited. (safety F7; F6 is R116)
- [x] R130 low: odd Herdr replies (empty, reshaped) raised TypeError or
      KeyError past the error handling, once between the record and the
      signal: they're HerdrError. (safety F8)
- [x] R131 low: with no pane in focus, re-arms still typed: the check stops
      before them. (safety F9)
- [x] R132 low: the last look didn't re-read the processes or Claude's
      registry, and checked start times before slow calls: it does, start
      times last. (safety F10)
- [x] R133 low: a Codex draft whose first line is blank read as empty.
      (safety F11)
- [x] R134 nits and limits: settings changed during a restart re-arm,
      `--permission-mode bypassPermissions` with an unknown mode, option
      values starting with `=` or `%` (zsh, fish), Known limits for a Claude
      waiting on another session's reply and the key's instant before
      typing; the safety reviewer's 35 mutations join the list (6
      survived). (safety nits, tests)

### Strict review 7 (2026-11-26)

Reports (kept outside the repo): `earmark-review7-safety.md` and
`earmark-review7-fit.md`. Neither found a critical or high (the second
round running). Safety: the engine clears nearly every class; 12 of its
146 own mutations survived. Fit: fit and cost hold up; 24 of its 51 own
mutations survived (popup keys and mouse, the message popup, the argv
layer, records). Cody's call: one cleanup round, then round 8 to confirm;
stop if it's clean. Time mode on the maintainer's machine from now.

The re-arm area (may Earmark type its placeholder line into this pane
now?) has drawn findings in rounds 2, 3, 5, 6 and 7 (R27, R53, R93, R101,
R126, R127, R131, and three here), and this round found two of its fixes
undoing each other. Per the strict-review rule, R138 replaces the patches
with one rule instead of adding a fourth.

- [x] R135 low-medium: after a placeholder's first start, `arm()` leaves
      `first_rev = None`, which `rearm_pass` reads as "the shell was used",
      so a placeholder lost later (outside a restart) never comes back by
      itself. R101 and R127 undo each other. (safety F2)
- [x] R136 medium-low: memory mode with memory fine starts no worker, and
      the re-arm pass runs only in manual and off modes: a missing
      placeholder waits for low memory or the key. (fit F1)
- [x] R137 low: the `--rearm` worker started after a slow stop or a failed
      worker start types without the untouched-shell rule; a shell left on
      a continuation line (trailing `\`) gets Earmark's line appended to
      the pending command (Ctrl+E Ctrl+U clears only the current line).
      (safety F5)
- [x] R138 redesign: one rule, "Earmark types its line only into a bare
      shell untouched since Earmark last saw it come back, in the record's
      own tab, not in view, when Herdr won't relaunch the agent (only the
      user's own key skips the untouched wait)", applied by `arm()` for
      every caller. Two triggers: a restart (`rearm_all`, waits for the
      panes and Herdr's restore) and one regular pass in every mode at most
      once a minute while a placeholder is missing. Removes the
      manual-only branch, the slow-stop `--rearm` door and the
      `first_rev = None` reset; Ctrl+C before Ctrl+E Ctrl+U cancels a
      continuation line. Fixes R135-R137 by construction.
- [x] R139 medium: automatic suspends drop environment set only for the
      agent (`ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, Bedrock/Vertex
      switches, `AWS_PROFILE`, proxies): Enter resumes under the shell's
      account or endpoint. A difference in such variables between the
      agent and its shell is an unknown launch option (automatic modes
      refuse, the key asks). (safety F1)
- [x] R140 low: the last look before the signal reads an unreadable prompt
      as empty (the first look refuses it). (safety F3)
- [x] R141 low: hooks and `settle_now` save index.json before archive.json;
      a failed archive write (disk full) loses a closed or replaced
      session from both. Archive first. (safety F4)
- [x] R142 low: a late "suspend anyway?" question still takes the keyboard
      and doesn't name the tab. (safety F6, fit F5)
- [x] R143 low: a Claude folder lookup that failed counts as `~/.claude`
      when filing or pruning, so a session in another folder is silently
      never archived. Unknown folder: keep, as for an unreadable one.
      (safety F7)
- [x] R144 low (cost): `focused_at`, `status` and `status_at` rewrite and
      fsync index.json on every tab switch and status change even with
      suspending off (the shipped default). Only the automatic modes read
      them. (fit F2)
- [x] R145 low: the Workspaces view's forget question loses its Keep
      button and hint below about 90 columns, and all buttons below 72,
      while clicks elsewhere are ignored. (fit F3)
- [x] R146 low: on an 80x24 terminal the message popup cuts the doubt it
      asks about to one line. (fit F4)
- [x] R147 low: a plain message closes on the first key with no settle
      time, so typing on after the press hides it. (fit F6)
- [x] R148 low: `check` and `list` ignore `XDG_CONFIG_HOME` /
      `XDG_STATE_HOME` when Herdr's plugin variables are unset. (fit F7)
- [x] R149 nit: a rewritten transcript keeps the old permission mode in
      the timer cache. (fit F8)
- [x] R150 low-medium (was an unverified safety nit; confirmed live):
      `pane read --source visible` returns the scrolled-to part of a pane,
      so a Claude tab scrolled up and left was read from an old, empty
      prompt box (unsent text missed). Both looks of a suspend read
      `--source recent --lines <viewport_rows>`, the bottom screen (also a
      full-screen program's).
- [x] R154 medium (found by our own live check): Herdr's pane `revision`
      moves with the folder and the title, never with typing or output, so
      the untouched-shell rule (R84, R127, R138 as first built) never saw a
      shell being used. It compares a fingerprint of the screen at two
      looks instead; a change outside a restart marks the shell used (the
      `used` flag, so hooks don't start a worker for it every minute). The
      platform fact is in CLAUDE.md. Lesson for the checklist: a fix that
      rests on a platform field's meaning needs a live check of that
      meaning, not a test that fakes it.
- [x] R151 design: the parking rule's conditions written twice (`refusal()`
      and `suspend_pane`'s doubts); the 256 KB tail permission-mode
      fallback left beside the whole-transcript reader;
      `placeholder_running` duplicating `placeholder_pid`; stale
      docstrings (`earmark.py` worker options, the placeholder's timer);
      finding IDs in two code comments. (fit design)
- [x] R152 claims: README's untouched-minute re-arm and R101's claim (true
      again after R138); `suspend.py` "never dropped without a trace";
      NOT_YET's "within a minute" when Herdr's listing is stale;
      `mark_waking`'s "never twice" for agents other than Claude; R118's
      unfocused popup (check live that Herdr doesn't take focus anyway);
      README count mode and the popup's start time. (both)
- [x] R153 tests: behaviour-level tests where the survivors cluster
      (the curses popup driven by a key and mouse script, the message
      popup's keys, the argv layer end to end into the worker, close to
      restore as a round trip, arm then loss then pass in sequence), then
      both reviewers' 36 survivors join tests/mutations.md, all caught.
- Accepted: a second key press just after a resume suspends again (the key
  toggles; nothing lost); a suspended pane moved to another tab is
  archived as "its tab is gone" (not lost); `claude; cmd` typed by the
  user runs `cmd` when the agent stops (Known limits).
- Release (with R4 and R63): test paths that read like a second account
  renamed; done at the 1.1 release.
- Weight (code, earmark/ and earmark.py): +305 / -178 lines (64 of the
  added are comments and docstrings). State: `base` {screen, at, used}
  replaces `first_rev`; records gain `account` (hashed fingerprints),
  archive entries `folder_unknown`. Removed: the slow-stop `rearm` door,
  the manual-only re-arm branch, the doubts list written twice,
  `placeholder_running`, the 256 KB permission-mode reader. Tests: 616 →
  650ish (tests/test_flows.py, tests/test_surfaces.py); mutations 715 → 954
  (both reviewers' lists, one per fix).

### Strict review 8 (2026-11-26, night)

Reports (kept outside the repo): `earmark-review8-safety.md` and
`earmark-review8-fit.md`. Neither found a critical or high, the third round
running: per Cody's rule the review stops here, with these fixed. Safety:
49 of its 51 own mutations caught; two mediums on the resume side. Fit:
fit and cost clear every class; 14 of 44 own mutations survived (timing
constants asserted against themselves, state carried between hooks).

- [x] R155 medium (confirmed live 2026-11-26): Claude records a Shift+Tab
      to plan or manual mode only when it exits (entering auto is written at
      once), so a session taken from auto to manual and left resumed in
      auto. Earmark reads the mode again after the stop (Claude re-stamps it
      on SIGTERM) and rebuilds the resume line; without an exit record it
      never resumes in auto or bypass unless the captured footer shows that
      mode. (safety M1)
- [x] R156 medium: a Herdr restart during a stop (or right after Enter)
      skipped the "Herdr's restore goes first" guard: `herdr_listed` was set
      only on "suspended" records. Set it whenever Herdr lists the session
      in its pane, whatever the state; rearm_all leaves a fresh "waking"
      record alone. (safety M2)
- [x] R157 low: after `y`, a suspend that stopped the agent was reported as
      "Earmark kept it running", in a focused popup up to 30 s later: the
      confirm path answers through tell(). (safety L1)
- [x] R158 low: a paste into a placeholder resumed it (any newline counted
      as Enter): bracketed paste on, pasted text ignored. (safety L2)
- [x] R159 low: the suite read the real ~/.claude (HOME not pinned).
      (safety L3)
- [x] R160 nits: the screen copy written outside the guarded section; the
      mark_waking fallback and the restart grace for missing panes
      untested. (safety N1, T1, T2)
- [x] R161 tests: timing constants asserted against themselves (the view
      dwell, the message's first moment), the return grace and a failed
      stop's back-off never through a hook, restart and restore boundaries;
      both reviewers' mutations join the list, and exact duplicates in it
      go (783 distinct of 953). (fit 1)
- [x] R162 low: the question popup kept a lone `n` up for a minute and never
      showed what was typed: any key but `y` closes it, a typed `y` shows.
      (fit 4)
- [x] R163 low: a double-click on a row's × reopened the session. (fit 5)
- [x] R164 low: a scheduled_tasks.json of an unknown shape read as "no
      tasks": unknown is a doubt. (fit 6)
- [x] R165 low (cost): count mode looked at every agent every minute: the
      recent-activity prefilter applies to it too. (fit 7)
- [x] R166 low (cost): notes' `seen` aged one by one, so index.json was
      rewritten on a third of quiet hooks: refreshed together. (fit 8)
- [x] R167 claims and nits: the STABLE comment, the key's garbled "not
      yet" answer, README's quiet-hook and count-mode claims and the late
      toast, Known limits for "open elsewhere" (Codex and others, and
      reopening from the archive), the test count, popups' pane ids
      (checked: not in pane list, the CLI gives none). (both)
- Accepted: one lock held across Herdr calls (hooks take ~60 ms; a stuck
  process is a machine fault; safety L4); a broken config.toml shown in
  worker.log, `check`, the popup and the key's answer only (fit 9); "open
  elsewhere" decided per path (documented; fit design); arm()'s flags.
- R155 checked end to end live (isolated Herdr, real Claude): started in
  auto, Shift+Tab to manual, the key; the transcript said auto before the
  stop and default after it, and the record resumes without auto.
- Mutations: both reviewers' lists joined (82 not already listed), one per
  fix, 76 exact duplicates removed, six equivalents left out with a note.
- Checked by Cody 2026-11-26: a popup opened with `--no-focus` leaves the
  keyboard where it was (he typed on in micro in a pane as Earmark's message
  popup opened; every key reached micro and the popup closed by itself), so
  R118 and R142 hold on the real platform.

### Later (not scheduled)

- [ ] Switch Cody's Herdr from the linked clone to the installed release
      once changes slow (`herdr plugin unlink`, `herdr plugin install`,
      and tools.yaml in the dotfiles). Until then main must stay
      release-quality: `herdr plugin update` follows main, not tags.
- [ ] When herdrdev/herdr#4649 is fixed: drop `--no-daemon` (and
      `command`) from the Codex resume command, the README's Codex note,
      and Cody's `codex` shell function in his dotfiles.
- [ ] After Herdr updates: re-run tests/live_check.sh, retest whether
      plugin actions can appear in Herdr's right-click menus (A4), and
      re-check the platform facts in CLAUDE.md.
- [ ] Facts (title, last activity, still there) for Pi, Copilot and other
      agents, once there are real sessions of theirs to read.
- [ ] A per-tab "keep awake" switch, if the automatic protections (busy
      children, Claude's timers) turn out not to be enough.
- [ ] Suspended tabs marked in Herdr's Agents panel (a pseudo-agent report
      or display metadata), if Cody wants them listed there.
- [ ] 1.2 (Cody, 2026-11-26): one `herdr api snapshot` instead of `pane
      list` + `workspace list` + `tab list` in `herdr.snapshot()`. Not for
      speed (5 ms vs 3 ms measured) but for one consistent moment: three
      calls can straddle a rename or close. Also gives `focused_pane_id`.
- Not planned (Cody, 2026-11-26): restoring splits with `layout.export` /
  `layout.apply`. Not worth the complexity (layouts saved before each
  close, panes matched to sessions); stays a Known limit in the README.

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
- 2026-11-21: Cody tried G (works). Plan items A-G ticked. Fixed: restoring a
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
- 2026-11-21: go-public stage 3. Two independent read-only reviews
  (correctness; security and trust). Confirmed and fixed: /goal-style
  Claude sessions skipped; rename + close in one snapshot kept the old
  label; a tab name lost in a snapshot race; restarts noticed only by the
  startup hook (now also by a new server pid); restore used creation order
  (now tab-list order); sidebar seq taken after the lock; keep_days = true;
  fallback parser (quotes in comments, multi-line arrays, bad lines);
  popup with wide or control characters, selection on empty lists; unsafe
  session ids (leading "-", quotes for fish) and names starting with "-"
  (Herdr's global-flag scan); unescaped agent folders and the sqlite URI;
  Antigravity's agent name "agy"; durable writes, unique .damaged names,
  malformed entries, private debug log, stale index sessions; the entry's
  `source` field doubling as the file cache (now `file`); live_check's
  shared /tmp folder. README: archives go by workspace name (unnamed
  workspaces in one folder share one), titles can be prompt text,
  CLAUDE_CONFIG_DIR, keep_days = 0. Deferred: smarter handling when
  CLAUDE_CONFIG_DIR differs between the shell and Herdr's server.
  20 new tests, each failing on the old code; 54 unit tests pass on 3.14
  and 3.9; live check 20/20 with Codex and Grok.
- 2026-11-21 (handoff): 1.0.0 public and in Herdr's marketplace index.
  Development continues in a fresh session: start with CLAUDE.md (status,
  "Cody's own setup", "Pitfalls learned the hard way", "Releasing"), then
  the "Later" list above. Media method and scripts: media/shoot/.
- 2026-11-25: Cody asked for a middle bucket between "working with" and
  "done": sessions waiting on him that he won't get to soon, which hold
  memory (several GB across his sessions). Six existing sleep/park plugins
  reviewed (phase I has what was borrowed and avoided); built phase I
  (suspend in place) and phase J (CLAUDE_CONFIG_DIR from the process) on
  branch `suspend`, in a worktree, tested against an isolated Herdr (its own
  HOME) with real Claude Code: manual suspend, frozen and notice views,
  Enter and view resume (with `--permission-mode auto` restored), unsent
  text refused, restart re-arms the placeholder, closing archives, Ctrl+C
  archives, time mode skips the tab in view and unseen results. Found
  live: Herdr can still show a stopped Claude's session in its pane for a
  moment (the record now ends only on "waking" or after a minute), and a
  resume may come with no Herdr event at all (the worker and key settle
  records themselves). live_check.sh gains step 6 (suspend); 18/18 and 99
  unit tests pass. Next: the fresh review, then Cody tries manual mode on
  his own Herdr, then time mode.
- 2026-11-25 (later): fresh correctness review of the branch (no build
  context): 14 findings. Fixed, each with a test: Enter only into the
  placeholder (it could reach an agent or a shell); a failed stop never
  drops a record if the agent is gone; another session's /exit archived; a
  stalled stop finished; the hook path guarded (an odd process-info reply
  could have stopped archiving); count mode with turned-down panes; resume
  keeps the session's CLAUDE_CONFIG_DIR and drops bypass after a switch to
  default; the prompt box needs the prompt; one rearm per server; open in
  another terminal counts (Claude's registry). The review's 8 surviving
  mutations, plus 20 more, all caught now (28/28). Found live while
  re-testing: typing the placeholder before Herdr saw the shell's prompt
  left Herdr listing the stopped agent, and its restore relaunched it after
  a restart; Earmark now waits for Herdr to let go, and a relaunch ends the
  record (CLAUDE.md platform facts). 144 unit tests (3.14 and 3.9),
  live_check 18/18, time mode and three restart rounds clean. Next: merge to
  the linked clone (local), Cody tries manual mode, then time mode.
- 2026-11-25 (evening): Cody tried manual mode. Most tabs fine; on one
  the key "did nothing". Cause, from Earmark's, Herdr's and the
  transcript's logs: the frozen view looked so like Claude that the first
  suspend went unnoticed; Enter resumed it by exec in the placeholder's
  place, which kept the process group, so Herdr lost track of the agent;
  the second press then suspended it with Herdr's view stale, a `claude
  --resume` line reached the shell together with Earmark's placeholder line,
  and Claude got "/usr/bin/python3" as a stray first message (harmless). The
  same record could also have sent Enter into Claude (removed by hand at
  once; suspending paused with `when = "off"` meanwhile). Fixed: the shell
  starts the agent (`placeholder && resume`), Ctrl+U before typing, exact
  placeholder match, only the agent's own process is ever stopped, the key
  presses Enter whenever the placeholder is up, a vanished record doesn't
  strand a session. Cody's asks: a 💤 tab mark (display only, never
  recorded) and the frozen view dimmed, so a suspended tab is obvious; key
  Ctrl+Space Ctrl+S instead of Shift+S. 162 unit tests, 35/35 mutations
  caught, live_check 18/18, four key suspend/resume rounds on an agent
  Herdr's restore relaunched (that tab's shape) clean.
- 2026-11-25 (night): strict review 1 (two fresh reviewers; reports kept
  outside the repo). Their own mutations: 27/27 and 14/36 survived;
  ours had only re-planted fixed bugs. Recorded R1-R25 (+R26, Cody's
  "suspend unseen too"), fixed all but R4's history squash (a release
  step), each with a test; tests/mutate.py and tests/mutations.md (81
  mutations, the reviewers' survivors included) now in the repo, all
  caught; 215 unit tests. Time mode paused on the maintainer's machine (manual)
  until the fixes are deployed. Next: isolated live test, deploy, round 2.

- 2026-11-25 (late night): strict review 2 (fresh reviewers again;
  earmark-review2-{safety,fit}.md). One high in the engine (R27, re-arm
  racing Herdr's deferred restore), one in the tests (R28: 21 of 60 and 45
  of 58 of their own mutations survived; round 1's "all caught" was our own
  list re-planted). Recorded R27-R52, all fixed, each with a test; both
  reviewers' 118 mutations and one per fix joined tests/mutations.md (233,
  all caught); tests/test_review2.py; 310 unit tests. Marks put by earlier
  1.1 builds (no list of marked tabs then) are taken as Earmark's once. Also fit L9 (the
  placeholder line's own paths checked before stopping) and `check` now
  says a problem pauses automatic suspends and pruning. The isolated live
  check first failed at step 5: R49's restart grace held back a workspace
  closed right after a restart; Herdr's own close events (workspace, tab,
  pane) now end the doubt at once; then 18/18. Next: deploy to the live
  clone, round 3.
- 2026-11-26 (small hours): strict review 3. Both reviewers: the engine
  beats the eight audited plugins on stopping agents, keeping sessions and
  typing into panes; not yet on fit and honesty. One high each: R27's
  restart guard read a note the first hook after a restart deletes (R53),
  and the key's answers went through Herdr toasts, off by default (R64).
  Recorded R53-R68, all fixed with tests; the reviewers' 114 mutations (31
  survived at first) and one per fix joined tests/mutations.md (377, all
  caught); 393 unit tests. The key now answers in Earmark's own popup
  (`y` confirms); Cody asked for `messages = "toast"` too (Herdr's toasts
  and the second press, only where Herdr's toasts aren't off). Live in an
  isolated HOME: 18/18; the popup opens with the key's message and closes
  by itself; a bare shell's process-info lists the shell itself. Next:
  deploy, round 4.
- 2026-11-26 (night): strict review 4. Fit: no high; the engine passes
  every class in the audit. Safety: two highs, Herdr's listed session
  trusted over Claude's own record of the process (R79), and the permission
  mode read from the transcript's tail only (R70, found by both). Recorded
  R69-R92, all fixed with tests; the fit reviewer's 61 mutations (41
  survived at first) and the safety reviewer's 3 survivors joined
  tests/mutations.md with one per fix. Live: 18/18 (three runs; one earlier
  run under heavy load had Herdr slow to let go, so the key's placeholder
  came later, as designed); Claude's pasted-text chip reads as unsent text.
  Cody went to bed: keep running rounds until one has no critical or high.
- 2026-11-26 (small hours, autonomous): strict review 5. Safety: one high,
  a recreated named session reusing pane and tab ids got an old placeholder
  typed into its new shell (R93: records now keep their tab's identity and a
  placeholder goes back only into a matching tab); timers after a sleep, the
  toast double tap and stale listings fixed too. Fit: no high; the suite had
  been reading the real Herdr config (R105), and the command-line layer was
  untested. Recorded R93-R113, all fixed with tests; both reviewers' lists
  (132 new mutations) and one per fix joined tests/mutations.md.
- 2026-11-26 (early morning, autonomous): strict review 6. Neither reviewer
  found a critical or high: the first round to meet that bar. Its mediums
  touched unsent text (an extended colour, a typed `Try "..."`), durable
  scheduled tasks and R93's default-named tabs, so they were fixed (R114-
  R134, each with a test) and a round 7 confirms before stopping. Both
  reviewers' lists and one per fix joined tests/mutations.md.
- 2026-11-26 (afternoon): round 6's fixes finished. Full sharded mutation
  run (715) all caught after the last 8 survivors got tests (the run had
  finished in about 30 minutes; the wait loop around it matched its own
  command line and sat for hours); live_check 18/18; deployed 3c395d1.
  Cody asked to wind down before round 7. Open: a round 7 to confirm round
  6's fixes, or stop the review here (Cody's call); then time mode on his
  machine; then the 1.1 release (R4 squash, R63's PLAN scrub, I7).
- 2026-11-26 (evening): strict review 7. Neither reviewer found a critical
  or high (the second round running), but the re-arm area drew three
  findings, two earlier fixes undoing each other among them (R135), so it
  was rebuilt around one rule in `arm()` instead of patched (R138), with
  Cody's OK; his Herdr went to time mode the same hour.
  Our own live checks in an isolated Herdr then found two platform facts
  wrong: Herdr's pane revision doesn't move with typing (R154: the
  untouched rule compares the screen now) and `--source visible` follows
  scrolling (R150: screens are read from the bottom). Also the account
  check at resume (R139), the lows R140-R149, one list of what Earmark
  can't check (R151), docs (R152), and both reviewers' 198 mutations with
  behaviour tests where 38 got through (R153; tests/test_flows.py,
  tests/test_surfaces.py). 651 unit tests; live_check 18/18; the round's
  live harness 10/10; a dry run on a copy of the live state changed
  nothing (58 archived, 9 suspended kept). Next: deploy, round 8.
- 2026-11-26 (night): strict review 8. Neither reviewer found a critical
  or high, the third round running, so the review stops here (Cody's
  rule). Fixed anyway: Claude's permission mode read again after the stop
  (R155, the one that mattered: auto to manual and walking away resumed in
  auto; checked live end to end), restarts during a stop or a resume
  (R156), the confirm answer (R157), pastes (R158), the suite's HOME
  (R159), and the lows and tests (R160-R167). 679 unit tests; 971
  mutations, no duplicates. Next: the full mutation run, the live checks,
  deploy, then the 1.1 release (R4 squash first, with Cody).
- 2026-11-26 (night): 1.1.0 released. The 1.1 history squashed into one
  commit (R4), private details out of the plan and tests, the go-public
  privacy scan over every commit, 679 unit tests on Python 3.14 and 3.9,
  live_check 26/26 with Claude Code, Codex 0.172 and Grok, the popup's
  `--no-focus` checked by hand.
