#!/usr/bin/env python3
"""Earmark: closed agent sessions, filed under their Herdr workspace.

Herdr runs this with a subcommand from herdr-plugin.toml:

    open             the "open" action: the popup on this workspace's sessions
    open-workspaces  the "open-workspaces" action: the popup on closed workspaces
    popup            the popup itself (EARMARK_VIEW picks the view)
    suspend          the "suspend" action: suspend the agent in view, or
                     resume it if it's suspended
    message          the small popup the suspend key answers in
    hook     every event hook and the startup hook: keep the notes on live
             panes current and archive what closed

and for workspace notes:

    note-open        the "note" action: the popup on this workspace's note
    note-popup       the note popup itself (EARMARK_NOTE_WS picks the workspace)
    note [show [--json] | write [--expect VERSION] | path]
                     read or replace this workspace's note (the /herdr-note
                     skill uses it); --workspace W, --session S

and for Herdr's sidebar:

    rows [--apply | --theme-hook]   print the rows to put in Herdr's
                                    config.toml for Earmark's values;
                                    --apply puts them there now (between
                                    Earmark's markers; only with
                                    write_herdr_config on); --theme-hook makes
                                    Omarchy recolour them after each theme
                                    switch

for Claude Code (its statusLine command in settings.json):

    statusline [-- command...]   pass Claude's status-line input to your own
                                 status line command (its output and exit
                                 code pass through), and show the model,
                                 effort and context use on this agent's row
                                 in Herdr's sidebar

and for Earmark itself:

    suspended <session> <pane>   the placeholder in a suspended tab
    worker [options]             suspends agents in the background: an
                                 automatic check, or --pane P for the key
                                 (--pressed T, --accept DOUBT), --rearm
                                 after a restart, --rearm-pass for missing
                                 placeholders; --session S

and for people:

    list     print the archive (all Herdr sessions and workspaces)
    check    print the settings in effect and where Earmark keeps its files

Outside Herdr (Claude Code's status line, the /herdr-note skill, Omarchy's
theme hook) it's run through the launcher Earmark keeps in its config folder
(earmark/launcher.py), never from where Herdr installed it.

Python standard library only (CLAUDE.md, rule 1).
"""
import json
import os
import sys

if __name__ == "__main__" and sys.argv[1:2] == ["statusline"]:
    # The user's own status line goes out before the rest of Earmark loads.
    from earmark import statusline
    sys.exit(statusline.run(sys.argv[2:]))

from earmark import PLUGIN_ID, VERSION, config, core, herdr, store  # noqa: E402


def _json_env(name):
    try:
        return json.loads(os.environ.get(name) or "null")
    except ValueError:
        return None


def cmd_open(view="sessions"):
    herdr.run("plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "archive",
              "--env", f"EARMARK_VIEW={view}")


def cmd_open_workspaces():
    cmd_open("workspaces")


def cmd_popup():
    from earmark import ui
    ui.main(_json_env("HERDR_PLUGIN_CONTEXT_JSON") or {}, os.environ.get("EARMARK_VIEW") or "sessions")


def cmd_message():
    from earmark import message
    message.main()


def cmd_suspend():
    from earmark import suspend
    ctx = _json_env("HERDR_PLUGIN_CONTEXT_JSON") or {}
    pane_id = ctx.get("focused_pane_id") or os.environ.get("HERDR_PANE_ID")
    if not pane_id:
        suspend.say(config.load(), "Earmark", "No tab in view to suspend.")
        return
    suspend.key(herdr.session_name(), pane_id)


def cmd_suspended():
    """The placeholder. A pane's shell doesn't have Herdr's plugin variables,
    so the line that starts it says where Earmark's files are."""
    args = sys.argv[2:]
    if len(args) < 2 or len(args) % 2:
        print("usage: earmark.py suspended <herdr session> <pane id> [--state DIR] [--config DIR]", file=sys.stderr)
        sys.exit(2)
    for option, value in zip(args[2::2], args[3::2]):
        if option == "--state":
            os.environ["HERDR_PLUGIN_STATE_DIR"] = value
        elif option == "--config":
            os.environ["HERDR_PLUGIN_CONFIG_DIR"] = value
        else:
            print(f"earmark.py suspended: unknown option {option}", file=sys.stderr)
            sys.exit(2)
    from earmark import placeholder
    sys.exit(placeholder.main(args[0], args[1]))


def _arg(args, name):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def cmd_worker():
    from earmark import suspend
    args = sys.argv[2:]
    try:
        pressed = float(_arg(args, "--pressed") or "")
    except ValueError:
        pressed = None
    suspend.worker(_arg(args, "--session") or herdr.session_name(), config.load(), pane_id=_arg(args, "--pane"),
                   rearm="--rearm" in args, accept=_arg(args, "--accept"), pressed=pressed,
                   rearm_pass_only="--rearm-pass" in args)


def cmd_hook():
    event = os.environ.get("HERDR_PLUGIN_EVENT") or "startup"
    core.handle_event(event, _json_env("HERDR_PLUGIN_EVENT_JSON"))


def cmd_list():
    archive = store.load_archive()
    entries = sorted(archive.get("entries", {}).values(),
                     key=lambda e: (e["herdr_session"], e["workspace_label"], -(e.get("last_active") or 0)))
    index = store.load_index()
    for session, s in sorted(index.get("sessions", {}).items()):
        for pane_id, rec in sorted((s.get("suspended") or {}).items()):
            primary, _ = core.names(rec)
            print(f"{session} / {rec.get('workspace_label') or '?'}: {primary}  "
                  f"[{rec.get('agent')} {rec.get('session_id')}]  suspended in {pane_id} ({rec.get('state')})")
    if not entries:
        print("The archive is empty.")
    for e in entries:
        primary, secondary = core.names(e)
        print(f"{e['herdr_session']} / {e['workspace_label'] or '?'}: {primary}"
              f"{'  (' + secondary + ')' if secondary else ''}"
              f"  [{e['agent']} {e['session_id']}]")


def cmd_check():
    cfg = config.load()
    print(f"Earmark {VERSION}")
    print(f"settings: {config.config_path()}"
          f"{'' if os.path.exists(config.config_path()) else ' (not created; defaults in use)'}")
    problem = config.check()
    if problem:
        print(f"  PROBLEM: {problem}")
    if problem or cfg.get("_broken"):
        print("  Until it's fixed: no automatic suspends and no pruning (the archive keeps everything); "
              "a bad value falls back to its default.")
    if cfg["suspend"]["messages"] == "toast" and herdr.toasts_on() is False:
        print(f"  messages = \"toast\", but Herdr's toasts are off ([ui.toast] delivery in {herdr.config_path()}),"
              " so the suspend key answers in its popup.")
    for key, why in config.retired():
        print(f"  {key}: no longer used ({why}); you can remove it")
    for key in ("keep_days", "title_first", "debug_log"):
        if key == "keep_days" and cfg[key] is None:
            print(f"  keep_days unset: as long as the agent keeps a session; "
                  f"{config.FALLBACK_DAYS} days where Earmark can't check")
        else:
            print(f"  {key} = {cfg[key]!r}")
    for agent, argv in sorted(cfg["resume"].items()):
        print(f"  resume.{agent} = {argv!r}")
    for key, value in cfg["suspend"].items():
        print(f"  suspend.{key} = {value!r}")
    for key, value in cfg["sidebar"].items():
        print(f"  sidebar.{key} = {value!r}")
    for key, value in cfg["colors"].items():
        print(f"  colors.{key} = {value!r}")
    for key, value in cfg["notes"].items():
        print(f"  notes.{key} = {value!r}")
    mismatch = config.context_mismatch(config._read()[0] or {})
    if mismatch:
        print(f"  note: {mismatch}")
    from earmark import herdrconf
    try:
        with open(herdr.config_path(), encoding="utf-8") as f:
            has_block = herdrconf.BEGIN in f.read()
    except OSError:
        has_block = False
    print(f"  Herdr's config.toml: {'has' if has_block else 'no'} Earmark rows"
          f"{'' if has_block or cfg['sidebar']['write_herdr_config'] else ' (earmark rows prints them)'}; "
          f"theme hook {'on' if os.path.exists(herdrconf.theme_hook_path()) else 'off'}")
    last = store.load_json("herdrconf.json").get("last")
    if cfg["sidebar"]["write_herdr_config"] and isinstance(last, dict) and last.get("status") not in ("written", "unchanged"):
        print(f"    last write: {last.get('status')}: {last.get('detail')}")
    from earmark import launcher
    print(f"  launcher: {launcher.path()}{'' if os.path.exists(launcher.path()) else ' (written at the next Herdr event)'}")
    if cfg["suspend"]["when"] == "memory":
        from earmark import procs
        available = procs.available_percent()
        print(f"    memory available now: {available:.0f}%" if available is not None
              else "    memory mode needs Linux; here it acts like manual")
    archive = store.load_archive()
    print(f"data: {store.state_dir()}")
    suspended = sum(len(s.get("suspended") or {}) for s in store.load_index().get("sessions", {}).values())
    print(f"  {len(archive.get('entries', {}))} archived sessions, "
          f"{len(archive.get('workspaces', {}))} closed workspaces, {suspended} suspended tabs")


def cmd_note():
    from earmark import notes
    return notes.cli(sys.argv[2:])


def cmd_note_open():
    wid = os.environ.get("HERDR_WORKSPACE_ID") or (_json_env("HERDR_PLUGIN_CONTEXT_JSON") or {}).get("workspace_id")
    if not wid:
        print("earmark: no workspace to show the note of", file=sys.stderr)
        return 2
    herdr.run("plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "note",
              "--env", f"EARMARK_NOTE_WS={wid}")
    return 0


def cmd_note_popup():
    from earmark import noteui
    ctx = _json_env("HERDR_PLUGIN_CONTEXT_JSON") or {}
    wid = os.environ.get("EARMARK_NOTE_WS") or ctx.get("workspace_id") or os.environ.get("HERDR_WORKSPACE_ID")
    if not wid:
        return 2
    noteui.main(herdr.session_name(), wid, ctx.get("workspace_label") or "")
    return 0


def cmd_rows():
    from earmark import herdrconf
    args = sys.argv[2:]
    cfg = config.load()
    palette = herdrconf.theme_palette() if herdrconf.theme_stamp() else {}
    if "--theme-hook" in args:
        hook = herdrconf.install_theme_hook()
        print(f"Omarchy now runs {hook} after each theme switch." if hook else
              "No Omarchy here (~/.config/omarchy): nothing to hook. Earmark recolours at its next Herdr event.")
        return 0 if hook else 1
    if "--apply" in args:
        status, detail = herdrconf.keep_current(cfg, now=True)
        print(f"{status}: {detail}" if detail else status)
        return 0 if status in ("written", "unchanged") else 1
    text = herdrconf.block(cfg, palette)
    if not text:
        print("# Nothing to show: [sidebar] counts and agent_row are both empty.")
        return 0
    print(f"# For {herdr.config_path()} (then: herdr server reload-config).")
    print("# Or set write_herdr_config = true in Earmark's [sidebar] and Earmark keeps it there itself.")
    print(text, end="")
    return 0


COMMANDS = {"note": cmd_note, "note-open": cmd_note_open, "note-popup": cmd_note_popup, "rows": cmd_rows, "open": cmd_open, "open-workspaces": cmd_open_workspaces, "popup": cmd_popup, "suspend": cmd_suspend,
            "message": cmd_message,
            "suspended": cmd_suspended, "worker": cmd_worker, "hook": cmd_hook, "list": cmd_list, "check": cmd_check}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(f"usage: earmark.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    result = COMMANDS[argv[1]]()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
