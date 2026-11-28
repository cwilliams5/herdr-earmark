# Earmark: plan

What's left to do, and what was decided not to do. Read CLAUDE.md first:
it has how Earmark works, the decisions and the reasons behind them.

The history is in git, not here: `git show v1.1.0:docs/PLAN.md` has the
plan through 1.1 (phases A to J, the pre-release review, strict reviews 1
to 8, every finding and its fix). 1.2 (phases K to N: the one-call snapshot,
workspace notes, the coloured sidebar, strict reviews 9 and 10, findings
R168 to R210) is summed up in CLAUDE.md and the 1.2 release notes; its
review reports are kept outside the repo.

## Released: 1.2.0 (2026-11-27)

v1.2.0 = 91cc7a4 (squashed; the unsquashed history is backed up outside the
repo). Live check 34/34 with Claude Code, Codex and Grok; 857 unit tests on
Python 3.14 and 3.9; installed from GitHub in a throwaway home (the launcher
pointed into Herdr's install folder and worked).

- [x] Cody: upload `media/social-preview.png` (repo Settings > Social
      preview; GitHub has no API for it). Done 2026-11-28.

## Later (not scheduled)

- [ ] Switch the maintainer's Herdr from the linked clone to the installed
      release once changes slow (`herdr plugin unlink`, `herdr plugin
      install`, tools.yaml in his dotfiles). Until then `main` must stay
      release-quality: `herdr plugin update` follows `main`, not tags.
- [ ] When herdrdev/herdr#4649 is fixed: drop `--no-daemon` (and `command`)
      from the Codex resume command, the README's Codex note, and the
      maintainer's `codex` shell function.
- [ ] After Herdr updates: re-run tests/live_check.sh, retest whether plugin
      actions can appear in Herdr's right-click menus, and re-check
      CLAUDE.md's platform facts, the sidebar width model and the install
      layout above all.
- [ ] Facts (title, last activity, still there) for Pi, Copilot and other
      agents, once there are real sessions of theirs to read.
- [ ] A per-tab "keep awake" switch, if the automatic protections (busy
      children, Claude's timers) turn out not to be enough.
- [ ] Suspended tabs marked in Herdr's Agents panel, if Cody wants them
      listed there.
- Not planned (Cody, 2026-11-26): restoring splits with `layout.export` /
  `layout.apply`; a README known limit.

## Accepted limits (found by reviews, decided not to fix)

Rare, cosmetic, or not worth the code. A review that finds one again can
point here; most are also in the README's Known limits.

- The suspend key toggles: pressed again right after a resume, it suspends
  again (nothing lost).
- A suspended pane moved to another tab is archived as "its tab is gone"
  (not lost); `claude; cmd` typed by the user runs `cmd` when the agent is
  stopped.
- One lock is held across Herdr calls (hooks take ~60 ms; a stuck process
  is a machine fault).
- A broken config.toml is reported in worker.log, `check`, the popup and the
  key's answer only.
- A pane moved to another workspace keeps its old ids in its environment:
  `/herdr-note` writes the old workspace's note and its agent line goes to
  a dead id, until the agent restarts.
- The `note` CLI and the status line take XDG folders from the pane's
  environment, Herdr from its server's.
- The milliseconds between `u`'s last check and Herdr's `agent prompt`.
- Report sequence numbers come from the wall clock: a clock stepped back
  mid-session leaves a line stale until its next change.
- A workspace closing as Herdr dies, its id reused within the boot grace,
  shows its note on the new workspace (a recreated session is handled).
- Text widths close to Herdr's unicode-width, not exact (some Thai and Indic
  marks, Hangul jamo, emoji newer than Python's Unicode); worktree child
  workspaces' extra indent; clients started with their own socket
  variables or over ssh keep a dragged width elsewhere (README).
- In Claude Code's default permission mode the asked Claude asks before
  running Earmark's `note` commands (README).
- On Python 3.9/3.10 (no tomllib) a config.toml that doesn't parse can still
  hide a broken block from `config check`.
