# Earmark: plan

What's left to do, and what was decided not to do. Read CLAUDE.md first:
it has how Earmark works, the decisions and the reasons behind them.

The history is in git, not here: `git show v1.1.0:docs/PLAN.md` has the
plan through 1.1 (phases A to J, the pre-release review, strict reviews 1
to 8, every finding and its fix). 1.2 (phases K to N: the one-call snapshot,
workspace notes, the coloured sidebar, strict reviews 9 and 10, findings
R168 to R210) is summed up in CLAUDE.md and the 1.2 release notes; its
review reports are kept outside the repo.

## Now: release 1.2.0

Built, reviewed (strict reviews 9 and 10: the second found no critical or
high), README media done; on the local `main`, live on the maintainer's
Herdr, not pushed. The ship-update skill (go-public's updates.md) has the
steps; CLAUDE.md's "Releasing" has this project's.

- [x] Codex and Grok live check: `EARMARK_AGENTS="codex grok"
      tests/live_check.sh` in an isolated HOME (CLAUDE.md, "Working on it").
      34/34 (2026-11-27; the check's `rows --apply` step now turns
      write_herdr_config on itself, and checks nothing is written while off).
- [x] The unit tests on Python 3.9 (`mise exec python@3.9 -- python -m
      unittest discover tests`, then `mise uninstall` it). 857 OK, 2 skipped
      (they need tomllib).
- [x] Re-check the sidebar width model, where the client keeps a dragged
      width, and the plugin install layout against the installed Herdr's
      source (CLAUDE.md, Releasing step 3); look at the real sidebar,
      dragged too. Herdr still 0.9.5, checked line by line by both review 10
      reviewers; the README shoot's sidebar showed full lines, nothing cut.
      The install layout gets its real test from the public URL after push.
- [x] README "Tested with" (Herdr, Claude Code, Codex, Grok, Pythons):
      unchanged, all still true (Herdr 0.9.5, Claude Code 2.1.332, Codex
      0.172, Grok 1.0.92, Python 3.14 and 3.9). Built on credits 1.2's
      idea sources.
- [ ] Squash the 1.2 history into one commit on top of 1.1.0 (Cody,
      2026-11-27), after backing it up in a bundle, as for 1.1.
- [ ] The privacy scan (go-public `scripts/privacy-scan.sh`) over everything
      to be pushed, last.
- [ ] Release notes shown to Cody; push; `gh release create v1.2.0`; upload
      `media/social-preview.png` by hand (Settings > Social preview).
- [ ] Afterwards: CLAUDE.md status, the maintainer's dotfiles (which mention
      the version).

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
