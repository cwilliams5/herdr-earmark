# Earmark

Closed agent sessions, filed under their [Herdr](https://herdr.dev)
workspace and ready to reopen.

In development.

Notes for the real README (go-public):
- Needs Herdr 0.9.5+ and `python3` (3.9 or newer, standard library only).
- Bind the two actions in Herdr's config.toml (`[[keys.command]]`, type
  `plugin_action`): `io.github.cwilliams5.earmark.open` and
  `io.github.cwilliams5.earmark.open-workspaces`.
- Codex: start it with `codex --no-daemon` until herdrdev/herdr#4649 is
  fixed, or Herdr can't tell which pane a Codex session is in.
- Sidebar count: add `$earmark` to `ui.sidebar.spaces.rows`; off otherwise.
- Uninstalling: `herdr plugin uninstall io.github.cwilliams5.earmark`, remove
  the key bindings, and delete `~/.local/state/herdr/plugins/io.github.cwilliams5.earmark/`
  (the archive) and `~/.config/herdr/plugins/config/io.github.cwilliams5.earmark/`
  (settings). The agents' own conversations are never touched.
