# How the README media were made

`media/hero.png`, `workspaces.png`, `reopen.gif` and `restore.gif` come from
a staged demo, never from the maintainer's real Herdr session. Re-shoot them
when the popup's look changes.

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
