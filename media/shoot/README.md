# How the README media were made

Every image comes from a staged demo, never from the maintainer's real Herdr
session. Re-shoot them when the popup's or the sidebar's look changes.

## 1.2: `hero.png`, `sidebar.png`, `notes.gif`, `suspended.png`

1. `stage-1.2.sh`: a named demo session (`earmark-demo`) with its own copy of
   your Herdr config (the hostname taken out of the tab bar, `sidebar_width =
   30` so an agent line shows in full), workspaces `web`, `docs` and `api`
   over `/tmp/demo`, each folder with a project `.claude/settings.json` whose
   status line is Earmark's launcher alone (`statusline`, no command of your
   own: it hides a personal status line and still sends the agent lines).
2. `agents-1.2.sh web|docs|api` (run the three at once): real Claude Code,
   Codex and Grok exchanges with prompts that say not to edit anything; some
   tabs are closed afterwards for the archive. `docs/outline` runs Claude in
   auto mode, so it can write the note without a permission prompt.
3. Staging by hand: a Claude asked a question with its AskUserQuestion tool
   waits on you (the red "needs input" count; a request to edit a file
   doesn't, in auto mode); `touch -d` two archived Claude transcripts for
   believable ages (3 hours, yesterday).
4. `SHOOT_DIR=<scratch> shoot-1.2.sh`: suspends `api/errors` with Earmark's
   own key action, sets one agent working, stages two context percentages
   (88% and 71%, through Earmark's own `agentrow.update`; short demo chats
   never fill a context window), shoots the sidebar and the archive over it,
   then opens the note popup on an empty note, asks `docs/outline` to write it
   (`noteui.ask`, what `u` does) and shoots while the note fills in. Herdr's
   toasts show in some frames; pick frames without them.
5. `social-preview.png`: the go-public skill's `social-preview.sh` on the new
   hero padded to 3:2 with the terminal's background (`magick -extent
   1968x1312`), so the card's frame cuts nothing.
6. Cropped 16 px on each side (the window's border glow), captioned with the
   go-public skill's `caption.sh`, GIF with `gif.sh` (3 frames, 2.2 s, 1000 px).
   Every colour was checked against the theme's with a pixel sample.

## 1.0: `hero-1.0.png`, `workspaces.png`, `reopen.gif`, `restore.gif`

1. **A named demo session with its own config.** Copy your Herdr config to
   `/tmp/earmark-demo/herdr-config.toml`, drop anything personal from it
   (the `hostname` entry in `tab_bar_right`), and start
   `HERDR_CONFIG_PATH=/tmp/earmark-demo/herdr-config.toml herdr --session earmark-demo server`.
   Plugins are global, so Earmark runs there too.
2. **Real sessions, neutral content.** Workspaces `web-app`, `docs` and `api`
   over folders in `/tmp/demo`, each tab running one short exchange with
   Claude Code, Codex (`codex --no-daemon`) or Grok, with prompts that say
   not to edit anything. `demo-lib.sh` has the helpers (`agent_tab`
   handles each agent's first-run trust prompt: Claude Code defaults to "No,
   exit", so it sends Down then Enter; Grok takes `y`).
3. **Hide personal details in Claude Code:** a project
   `.claude/settings.json` in each demo folder with
   `{ "statusLine": { "type": "command", "command": "true" } }` hides a
   personal status line. Claude Code's banner still shows the plan name.
4. **Believable ages:** `touch -d` the demo Claude transcripts, and set the
   demo closed workspaces' `closed_at` in Earmark's `archive.json` (under
   `store.locked()`).
5. **Shoot:** `shoot.sh` opens a foot window on workspace 9 attached to the
   demo session, places it with `$PLACE_WINDOW`, and drives everything
   through Herdr's CLI and socket API: `plugin pane open --env
   EARMARK_VIEW=...` for the popup, a raw `popup.close` request to close it,
   and Earmark's own `core.reopen` / `core.restore_workspace` for the
   actions. No simulated keys or mouse. It takes over the screen for about
   three minutes and restores the workspace and do-not-disturb after.
6. **Afterwards:** stop and delete the demo session, remove `/tmp/demo`,
   `/tmp/earmark-demo`, the demo transcripts in `~/.claude/projects/-tmp-demo-*`,
   and the demo's entries in Earmark's archive (`herdr_session ==
   "earmark-demo"`).

Captions and GIFs were made with the go-public skill's `caption.sh` and
`gif.sh` (frames 1000 px wide, 1.6 to 1.8 s each).
