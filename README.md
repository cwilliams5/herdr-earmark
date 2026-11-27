<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="branding/eartag/lockup-dark.svg">
    <img alt="Earmark" src="branding/eartag/lockup-light.svg" width="360">
  </picture>
</h1>

**Closed agent sessions, filed under their [Herdr](https://herdr.dev) workspace and ready to reopen.** An archive per workspace · reopen in one click · bring back whole workspaces · suspend idle tabs to free memory · Claude Code, Codex, Grok and the other agents Herdr knows

![The Earmark popup over a Herdr workspace called web-app, listing five archived sessions: each with the tab's name in bold, the agent's own title dimmed beside it, the agent (codex, grok, claude) and when it was last active](media/hero.png)

Herdr keeps your coding agents in workspaces and tabs. Close a tab, though, and its conversation is gone from Herdr: you're left digging for a session id, and the agent's own resume picker lists sessions by folder, not by the Herdr workspace you were working in. Earmark keeps every closed session filed under its workspace, so one key shows that workspace's archive and Enter brings a conversation back. To earmark something is to set it aside for later; an earmark is also the notch a shepherd cuts to show whose flock a sheep belongs to.

![Closing a Claude tab in web-app, opening the archive with Ctrl+Space then a, and pressing Enter: the tab is back with its name and its conversation](media/reopen.gif)

## What you get

- **An archive for each workspace.** Close a tab running an agent, or `/exit` the agent, and its session is filed under the Herdr workspace it was in. Archives go by workspace name, so a workspace you close and open again later gets its archive back.
- **Reopen in one click.** Ctrl+Space then `a` lists this workspace's closed sessions, newest first. Enter or a double-click opens the session in a new tab with its old name, resuming the conversation where it stopped.
- **Bring back a closed workspace.** Ctrl+Space then Shift+A lists the workspaces you've closed. Restoring one brings back the tabs it had when you closed it, in order, with their names and folders, plain tabs included, and every agent tab resumes its session. Its older archived sessions stay in the archive, so a workspace with 5 open tabs and 70 archived sessions comes back as 5 tabs.

  ![Ctrl+Space Shift+A lists closed workspaces; Enter brings docs back with its outline tab, where Claude resumes, and its plain notes tab](media/restore.gif)

- **Suspend idle tabs to free memory.** Each coding agent holds a few hundred MB while it waits. Suspending one ends the agent and keeps its tab where it was, marked 💤, showing the agent's last screen dimmed with "Press Enter to resume"; Enter brings the same conversation back in the same tab, with the options it was started with that Earmark knows (Claude Code and Codex; Claude in the permission mode it was in when it stopped, read from what Claude writes as it exits, and never in auto or bypass mode on a guess; see Known limits). Suspend a tab with a key (Ctrl+Space then Ctrl+S), or let Earmark do it after an hour idle, when memory runs low, or for all but the most recently used agents. It's off until you turn it on, and it never suspends an agent that's working, running a command, waiting on a Claude `/loop` wake-up or scheduled task (including one saved to survive restarts), or holding text you haven't sent, nor one where Claude's own record of the process names a different conversation than Herdr shows. Where it can't read an agent's prompt, can't tell what the agent is doing, or doesn't know an option it was started with, automatic suspends leave it alone, and the key asks first: its answers come in a small Earmark popup (Herdr's own notifications are off by default), and only `y` then Enter there suspends it anyway (or, with `messages = "toast"`, Herdr's toasts and a second press).
- **Your names first.** Each session shows the name you gave its tab (or pane) in bold, with the agent's own title for the session beside it. Reopening gives the tab its name back.
- **Mouse and keyboard.** Click to select, double-click to open, scroll with the wheel, click a row's × to forget it (with Forget and Keep buttons to confirm). Or arrows, Enter, Delete, `/` to filter, Tab to switch between Sessions and Workspaces.
- **Follows each agent's own housekeeping.** For Claude Code, Codex and Grok, Earmark reads the agent's own files (never writes them) for the title, the last activity and whether the session still exists. A session stays in the archive as long as the agent keeps it, and leaves when the agent deletes it, so the archive never offers a dead session.
- **Restarts are safe.** Restarting Herdr's server, or a reboot, doesn't archive anything: Herdr restores those tabs itself.
- **No daemon.** Earmark is a few short Herdr hooks and a popup, in plain Python with no dependencies. With suspending on, a hook also starts a check at most once a minute, which exits when it's done (it takes longer when it suspends tabs: up to about 30 seconds for each), and each suspended tab runs a small placeholder (about 20 MB) until it's resumed.

## Install

```bash
herdr plugin install cwilliams5/herdr-earmark
```

Then bind the archive to keys in Herdr's config (`~/.config/herdr/config.toml`) and run `herdr server reload-config`. `prefix` is Herdr's prefix key: Ctrl+B unless you've changed it; this page writes Ctrl+Space, the prefix Omarchy sets up.

```toml
[[keys.command]]
key = "prefix+a"
type = "plugin_action"
command = "io.github.cwilliams5.earmark.open"
description = "Earmark: archived sessions"

[[keys.command]]
key = "prefix+shift+a"
type = "plugin_action"
command = "io.github.cwilliams5.earmark.open-workspaces"
description = "Earmark: closed workspaces"
```

Any free key works; `prefix+a` and `prefix+shift+a` are unused in Herdr's default keys.

To suspend idle tabs, turn it on in Earmark's `config.toml` (`herdr plugin config-dir io.github.cwilliams5.earmark` prints the folder) and bind the key that suspends the tab in view, or resumes it:

```toml
[suspend]
when = "time"        # or "manual" (the key only), "memory", "count"; "off" by default
idle_minutes = 60
```

```toml
[[keys.command]]
key = "prefix+ctrl+s"
type = "plugin_action"
command = "io.github.cwilliams5.earmark.suspend"
description = "Earmark: suspend or resume this tab"
```

That's the prefix, then Ctrl+S (with Omarchy's prefix: Ctrl+Space, then Ctrl+S). (`prefix+s` is Herdr's settings key; a plain `ctrl+s` would take Ctrl+S away from every program in Herdr.)

Optionally:

- **Codex:** start it with `codex --no-daemon`. Since 0.157, Codex runs sessions in a shared background daemon, and Herdr then can't tell which tab a Codex session is in ([herdrdev/herdr#4649](https://github.com/herdrdev/herdr/issues/4649)), so Earmark can't file it either, and never suspends a Codex started without the flag (it couldn't be sure which session to bring back). Earmark's own reopen command already uses the flag.
- **An archive count in Herdr's sidebar:** Earmark publishes a `$earmark` token ("3 archived") for each workspace. It shows only if you add it to your sidebar rows:

  ```toml
  [ui.sidebar.spaces]
  rows = [["state_icon", "workspace", { token = "$earmark", dim = true }], ["branch", "git_status"]]
  ```

**Dependencies:** Herdr 0.9.5 or newer and `python3` 3.9 or newer, standard library only.

**What it changes:** its own two folders, the archive in `~/.local/state/herdr/plugins/io.github.cwilliams5.earmark/` and its settings in `~/.config/herdr/plugins/config/io.github.cwilliams5.earmark/`. It reads the agents' session files but never writes them, and it never edits Herdr's config: the key bindings above are yours to add. When it suspends a tab (only if you turn suspending on), it also stops that tab's agent (SIGTERM), types the placeholder's line into the tab's shell, and puts 💤 in front of the tab's name until it wakes.

## Uninstall

```bash
herdr plugin uninstall io.github.cwilliams5.earmark
```

Resume any suspended tabs first (Enter in the tab): Herdr keeps their 💤 names, and without Earmark a restart leaves them at a bare shell (the session can still be resumed by hand with the agent's own command). Then remove the `[[keys.command]]` blocks (and the `$earmark` token, if you added it) from Herdr's config, and delete Earmark's two folders listed above. The agents' own conversations are untouched.

## Resources

Earmark has no daemon (only each suspended tab's placeholder stays running). Its hooks run when Herdr reports an event (a tab focused, an agent starting or finishing, a close), take about 60 ms each (Herdr's own log; longer when a new agent is still reporting its session), and ran about twice a minute during a working session. Opening the popup checks the archive against the agents' files; each session's file is read once and then only again if it changes, so checking 300 archived sessions takes under a millisecond (the popup itself starts in about 50 ms).

With suspending on, a hook starts a check at most once a minute. It looks at the idle agents (their processes, and the agent's own files: for a Claude, its transcript's timers are read on from where the last check stopped), suspends what it should, and exits. It sees that placeholders are still up from the process table, without asking Herdr, and looks closely only at agents quiet long enough to qualify (none at all in memory mode while memory is fine). A suspended tab's placeholder uses about 20 MB instead of the agent's few hundred (282 MB for a short Claude Code session). With nothing changing, Earmark rewrites its notes about once every 10 minutes (with suspending on, also once a minute for its check), not on every tab switch.

**Tested with** Herdr 0.9.5, Claude Code 2.1.332, Codex 0.172 and Grok 1.0.92, on Arch Linux (Omarchy), with Python 3.14 and 3.9.

## Known limits

- **No right-click menu entry.** Herdr 0.9.5 doesn't let plugins add to its menus; the popup and its two keys are the way in.
- **Splits aren't restored.** A restored workspace's tabs come back with one pane each.
- **Only sessions closed after you install Earmark** are in the archive, and only sessions Herdr knows: the agent needs Herdr's integration installed (`herdr integration status`).
- **Archives go by workspace name.** Herdr names a workspace you haven't renamed after its folder, so two unnamed workspaces in the same folder share one archive (and a restore goes into whichever is open). Name them to keep them apart.
- **Earmark can't keep a session longer than its agent does.** Claude Code deletes conversations after 30 days of inactivity by default (`cleanupPeriodDays` in its settings). If you move Claude Code's files with `CLAUDE_CONFIG_DIR`, Earmark reads it from each Claude process's own environment when it first sees the session, so Herdr's server needn't have it; if it couldn't read it before the tab closed, the session is still filed, and kept for 30 days instead of following the agent.
- **Suspending, automatically, only takes Claude Code and Codex.** Earmark has to be sure no unsent text is in an agent's prompt before suspending it, and it knows how to read only those two prompts. Other agents can be suspended with the key. Suspending Codex is built and unit-tested but hasn't been run live yet (Claude Code has); Earmark reads Codex's files from Herdr's own `CODEX_HOME`, not each Codex process's.
- **Claude's own timers are the only ones Earmark can see.** A Claude waiting on a `/loop` wake-up or a scheduled task stays awake; another agent waiting on a timer of its own looks idle. Use `when = "manual"` if that matters to you.
- **Suspending ends what lives inside the agent:** its MCP servers start again on resume, and anything the agent kept only in memory is gone; the conversation itself is saved by the agent as it goes. Earmark never suspends an agent with a command running under it, so an MCP server that runs behind a shell of its own (a wrapper script that doesn't `exec`) keeps its agent awake for good.
- **A suspended tab leaves Herdr's agent views.** While suspended, its agent isn't in Herdr's agent panel or sidebar rows and sends no notifications; it comes back on resume.
- **A line in the shell's history.** The placeholder and the resume command are typed into the tab's shell as one line, with a leading space, which keeps it out of the history where the shell ignores such lines (bash with `HISTCONTROL=ignorespace`, zsh with `HIST_IGNORE_SPACE`). Before typing, Earmark cancels whatever is on the shell's line (Ctrl+C, then Ctrl+E and Ctrl+U), so nothing you left there, an unfinished command or an open quote, runs with its line; text half-typed in that bare shell is cleared. A placeholder that went missing comes back by itself only into a shell nobody has used since Earmark saw it back; once you've used that shell, the key brings the placeholder back.
- **Memory mode is Linux only.** Elsewhere only the key suspends.
- **Time mode acts on Herdr's events.** Checks run when Herdr has something going on (a tab focused, an agent starting or finishing), so while everything is quiet, overnight say, nothing is suspended. After Herdr has been quiet for 15 minutes, automatic suspends wait 5 minutes from the first event, so coming back doesn't set off suspends in front of you; then a check suspends, one by one, every agent idle for longer than `idle_minutes` that isn't in view. The idle clock counts from an agent's last activity or the moment you left its tab (a split beside the pane you were using counts as looked at), whichever is later.
- **Claude Code must be on PATH.** Resume runs `command claude`, so an install that works only through a shell alias (Claude Code's old `~/.claude/local` setup) isn't resumed.
- **Options and environment.** Resume brings back the options a Claude Code or Codex session was started with, and runs the agent as `command claude` (or `codex`), so a shell alias or function of that name isn't used. Variables set just for the agent (`ANTHROPIC_BASE_URL=... claude`, a function that sets a work profile) don't come back, apart from `CLAUDE_CONFIG_DIR`: the resume runs with the shell's. When the agent's account settings (`ANTHROPIC_*`, Bedrock and Vertex switches, cloud profiles, `OPENAI_*`, `XAI_*`, proxies) aren't the shell's, the placeholder says which before resuming and resumes only on a second Enter (Earmark keeps a hash of each value, never the value). Automatic suspends leave awake (and the key asks first about) an agent started with an option Earmark doesn't know, with a value that can't be typed back safely (a quote, a backslash, a newline), or through a wrapper (`aws-vault exec -- claude`); one started from a second shell inside the tab's (you ran `bash` first), or whose folder or Claude folder can't be typed back safely, isn't suspended at all. Other agents come back without options, and one started with any is left awake.
- **A command after the agent on the same line runs when it's suspended.** Earmark never suspends an agent with a command running under it, but `claude; exit` or `claude && make` goes on to the next command once the agent ends: with `; exit` the tab closes, and the session goes to the archive.
- **A Claude waiting on another session looks idle.** Claude Code sessions can message each other; one waiting for a reply from another session shows no sign of it Earmark can read, so automatic modes may suspend it.
- **A recreated Herdr session.** If you delete a named Herdr session and start a new one with the same name, Herdr hands out the same tab and pane ids again. After a restart, Earmark puts a placeholder back only into a tab with the same name, number, workspace name and folder, and treats a restart that brought back few of the old panes as a new session (its suspended tabs go to the archive); a new session whose only tab has a default name in the same folder can still look like the old one.
- **The key types right after its last look.** Pressing the key on a tab whose placeholder is missing types the placeholder's line after checking the shell is idle; a command started in that same instant receives its Ctrl+C and the line.
- **Shells:** bash, zsh, fish and POSIX sh. A tab whose shell can't run `a && b` (nushell, elvish, csh, tcsh) isn't suspended. Typing into the shell (Ctrl+C first, vi mode included) has been run live with bash only.
- **"In view" is Herdr's focused tab.** With a second Herdr client attached elsewhere, the tab it shows isn't protected.
- **"Open somewhere else" is seen fully only for Claude Code.** Before resuming or reopening, Earmark asks Claude's own registry whether the session runs anywhere (other Herdr sessions, plain terminals); for Codex and other agents it sees only this Herdr session's tabs, so one open in another Herdr session or a terminal can be resumed a second time.
- **A paste into a suspended tab doesn't resume it.** Pasted text is set aside (the frozen view looks like the agent's own screen); press Enter to resume, then paste.
- **A Herdr restart can wake a suspended tab.** If Herdr's server stops while it still lists the suspended agent (Earmark waits for Herdr to let go before showing the placeholder, so this should be rare), Herdr's own restore starts the agent again; Earmark sees it running and treats it as awake. Where Herdr listed the stopped agent before a restart, Earmark gives its restore a minute before it puts the placeholder back.
- **Titles can be the start of a prompt.** When an agent hasn't named a session, Earmark shows the beginning of what you typed, up to 120 characters, in its archive file and the popup.
- **Agents other than Claude Code, Codex and Grok** reopen with Herdr's own resume commands but are untested, and their sessions leave the archive after 30 days rather than following the agent.
- **Codex** needs `--no-daemon` (see Install) until [herdrdev/herdr#4649](https://github.com/herdrdev/herdr/issues/4649) is fixed.
- **Linux and macOS only:** the popup uses Python's `curses`, which Windows lacks. macOS is untested, though Earmark runs on Python 3.9, the version macOS ships; there a Claude Code installed through npm may show up as `node`, and then isn't suspended.

## Built on

- [Herdr](https://herdr.dev) ([herdrdev/herdr](https://github.com/herdrdev/herdr)): the plugin API, CLI and socket API Earmark runs on, and its table of resume commands per agent, which Earmark's defaults copy.
- Forge, the author's session manager for Windows: Earmark brings its per-project archive of closed sessions to Herdr.
- [douglascorrea/herdr-agent-inbox](https://github.com/douglascorrea/herdr-agent-inbox) showed that closed chats can be kept per workspace and reopened with `claude --resume` through Herdr's public plugin API, and [pedroloch/herdr-undo-close](https://github.com/pedroloch/herdr-undo-close) documented that Herdr's `tab.closed` event carries no tab contents. Ideas only; no code taken.
- The `codex --no-daemon` workaround documented in [herdrdev/herdr#4649](https://github.com/herdrdev/herdr/issues/4649).
- Suspending learned from other Herdr plugins that put agents to sleep, ideas only, no code taken: [herdr-autopark](https://github.com/common-resources/herdr-autopark) (the frozen view, unsent-text checks), [claude-hibernate](https://github.com/novarii/claude-hibernate) (pending timers from the transcript, resume flags and permission mode), [herdr-memory-guard](https://github.com/0xArchiviste/herdr-memory-guard) (memory thresholds), [herdr-hibernate](https://github.com/bengemine/herdr-hibernate), [herdr-shelve](https://github.com/meta-boy/herdr-shelve) and [herdr-rest](https://github.com/utkrshm/herdr-rest) (records first, re-checking before acting).
- Python's standard library (`curses`, `sqlite3`, `tomllib` where present).

---

The rest of this page is the reference: every setting, how Earmark works, and notes for changing it.

## Settings

Settings live in `config.toml` in Earmark's config folder (`herdr plugin config-dir io.github.cwilliams5.earmark` prints it). The file is optional; every key is.

| Setting | Default | What |
|---|---|---|
| `keep_days` | unset | Forget sessions this many days after their last activity. Unset: sessions of Claude Code, Codex and Grok stay as long as the agent keeps them; other agents' sessions and closed workspaces go after 30 days. `0` keeps sessions until the agent's files are gone, and closed workspaces until you forget them. |
| `title_first` | `"tab"` | Which name leads in the list: `"tab"` (the name you gave the tab or pane, when there is one) or `"agent"` (the agent's own title). The other is shown dimmed beside it. |
| `report_count` | `true` | Publish the `$earmark` sidebar token. It's only visible if you add it to your sidebar rows. |
| `debug_log` | `false` | Log every hook's event to `events.jsonl` in the state folder. |
| `[suspend]` `when` | `"off"` | Suspend idle agent tabs in place: `"off"`; `"manual"` (only the suspend key); `"time"` (after `idle_minutes`); `"memory"` (while less than `memory_below` percent of memory is available, longest idle first, until 5 points more is; Linux); `"count"` (all but the `keep_awake` most recently used agents). The key works in every mode but off. |
| `[suspend]` `idle_minutes` | `60` | Time mode: minutes since the agent's last activity (its conversation, subagents, your last look at the tab). |
| `[suspend]` `memory_below` | `20` | Memory mode: the percent of memory available below which agents are suspended. |
| `[suspend]` `keep_awake` | `8` | Count mode: how many agents stay awake, by last use (agents it doesn't look at closely, working, in view or active in the last 10 minutes, count as just used, so a few more may stay awake). |
| `[suspend]` `resume_on` | `"enter"` | `"enter"` (press Enter in the tab, or the key) or `"view"` (stay on the tab for a moment). |
| `[suspend]` `show` | `"frozen"` | What a suspended tab shows: `"frozen"` (the agent's last screen, dimmed) or `"notice"` (a short notice). Both say "Press Enter to resume"; Ctrl+C turns the tab into a plain shell and files the session in the archive. |
| `[suspend]` `suspend_unseen` | `true` | Automatic modes also take an agent whose finished answer you haven't looked at yet (Herdr's "done"); its placeholder says it's unread. `false` keeps those awake. |
| `[suspend]` `tab_mark` | `"💤"` | Put in front of a suspended tab's name while it's suspended, then taken off. Display only: archived and restored tabs keep their own names. `""` for none. |
| `[suspend]` `messages` | `"popup"` | How the suspend key answers: `"popup"` (a small Earmark popup that closes on any key or by itself; "suspend anyway?" takes `y` then Enter, any other key keeps it running; an answer that comes long after the press tries a Herdr toast first, so it doesn't take the keyboard) or `"toast"` (Herdr's notifications, which need `[ui.toast] delivery` on in Herdr's config; "suspend anyway?" takes a second press of the key within 10 seconds). Whenever Herdr answers that it didn't show a toast (toasts off, rate limited, busy), the popup is used instead, and a question goes by toast only with `delivery = "herdr"` (Herdr's own in-app toasts). |
| `[resume]` | Herdr's commands | The command that reopens a session, per agent name as Herdr reports it, with `{id}` for the session id as a whole argument (never inside `sh -c "..."`). For example `claude = ["command", "claude", "--resume", "{id}"]` (`command` keeps a shell alias or function named `claude` out of it). Earmark won't reopen a session whose id starts with `-` or holds a quote, a backslash or a control character. |

A `config.toml` Earmark can't read, or with a value it doesn't accept, stops automatic suspends and archive pruning until it's fixed (the key says so); meanwhile the defaults stand in for what's wrong (all of them, if the file can't be parsed), but nothing is pruned or suspended behind your back because of a typo. `python3 earmark.py check` (in the plugin's folder) prints the settings in effect, any problem with the file, and where the archive is; `python3 earmark.py list` prints the archive.

## How it works

- **Notes, not events.** Herdr's close events say what closed, not what was in it, so on each Herdr event Earmark takes a quick snapshot of panes, tabs and workspaces and compares it with its notes. A noted agent pane that's gone was closed (alone, or with its tab or workspace); an agent that left a pane was exited; a new session in the same pane replaced the old one. Those sessions are archived under their Herdr session and workspace. A session that's open again leaves the archive.
- **Restarts.** After a Herdr server start, restored agent panes briefly report their agent as gone while their resume is pending. Earmark ignores that for a minute after startup.
- **Closed workspaces** are remembered as a unit: the tabs open at the time, in order, with names, folders and agent sessions. Restoring creates the workspace again (or uses an open one with the same name) and resumes each agent tab whose session still exists.
- **Reopening** opens a tab with `herdr tab create` and runs the agent's resume command in it with `herdr pane run`.
- **Suspending** looks at the agent again just before acting (same processes, still idle, not in view, nothing typed, nothing running under it or sharing its terminal, no Claude timer pending), reads its screen, writes a record and a copy of the screen, and right before the signal checks once more that it's the same process, that Herdr doesn't show it working or asking a question, that nothing has been typed into its prompt meanwhile, and (for an automatic suspend) that it's not in view; then it sends SIGTERM to the agent and its launcher only (never SIGKILL, never its whole process group; one that hasn't stopped after 15 seconds is left running and not tried again for half an hour), waits for Herdr to see it gone, and starts the placeholder in the tab's shell as `placeholder && resume command`. On Enter the placeholder exits and the shell starts the agent as a new command, just as if you'd typed it, so Herdr sees it start as usual. The record goes once the session is seen running again; a suspended tab you close, or leave with Ctrl+C, goes to the archive. Earmark types only into a known shell with nothing running in it, and looks again, at the shell and at the tab in view, right before typing. When it puts a missing placeholder back by itself, the shell must also be unchanged at two looks (a check apart, or a few seconds after a restart); a shell someone has used since is left to the key. After a Herdr restart, Earmark starts the placeholders again in tabs that came back to a bare shell (after a minute where Herdr's own restore may relaunch the agent); hooks look for missing placeholders at most once a minute in every mode; a placeholder that doesn't come up isn't tried again for half an hour (the key always tries). Automatic modes never take an agent that's in view or (in memory and count modes) was active in the last 10 minutes; one with a result you haven't looked at only if `suspend_unseen` is on (the default), and its placeholder says so.

## Developing

- Link a working copy instead of installing: `herdr plugin link /path/to/herdr-earmark`. Code changes apply on the next hook or popup; re-link after editing `herdr-plugin.toml`.
- `python3 -m unittest discover tests` runs the unit tests; they never touch Herdr.
- `tests/live_check.sh` runs the whole flow (close, reopen, `/exit`, restart, restore a workspace, suspend and resume) against a throwaway named Herdr session with real Claude Code sessions. It uses your real Earmark state folder (test entries are removed afterwards), so with Earmark installed in your own Herdr run it under a throwaway HOME (CLAUDE.md, "Working on it"). `EARMARK_AGENTS="codex grok" tests/live_check.sh` adds Codex and Grok.
- `python3 tests/mutate.py` plants each one-line regression in `tests/mutations.md` in a scratch copy and runs the suite: every one must be caught.
- Hook errors show in `herdr plugin log list --plugin io.github.cwilliams5.earmark`; what the suspend checks did is in `worker.log` in the state folder.

## License

MIT. See [LICENSE](LICENSE).
