#!/usr/bin/env python3
"""Earmark: closed agent sessions, filed under their Herdr workspace.

Herdr runs this with a subcommand from herdr-plugin.toml:

    open     the "open" action (bound to a key): show the archive popup
    popup    the popup itself
    hook     every event hook and the startup hook: keep the notes on live
             panes current and archive what closed

and for people:

    list     print the archive (all Herdr sessions and workspaces)
    check    print the settings in effect and where Earmark keeps its files

Python standard library only (CLAUDE.md, rule 1).
"""
import json
import os
import sys

from earmark import PLUGIN_ID, VERSION, config, core, herdr, store


def _json_env(name):
    try:
        return json.loads(os.environ.get(name) or "null")
    except ValueError:
        return None


def cmd_open():
    herdr.run("plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "archive")


def cmd_popup():
    from earmark import ui
    ui.main(_json_env("HERDR_PLUGIN_CONTEXT_JSON") or {})


def cmd_hook():
    event = os.environ.get("HERDR_PLUGIN_EVENT") or "startup"
    core.handle_event(event, _json_env("HERDR_PLUGIN_EVENT_JSON"))


def cmd_list():
    archive = store.load_archive()
    entries = sorted(archive.get("entries", {}).values(),
                     key=lambda e: (e["herdr_session"], e["workspace_label"], -(e.get("last_active") or 0)))
    if not entries:
        print("The archive is empty.")
    for e in entries:
        print(f"{e['herdr_session']} / {e['workspace_label'] or '?'}: {e.get('title') or '(untitled)'}"
              f"  [{e['agent']} {e['session_id']}]")


def cmd_check():
    cfg = config.load()
    print(f"Earmark {VERSION}")
    print(f"settings: {config.config_path()}"
          f"{'' if os.path.exists(config.config_path()) else ' (not created; defaults in use)'}")
    for key in ("keep_days", "report_count", "debug_log"):
        print(f"  {key} = {cfg[key]!r}")
    for agent, argv in sorted(cfg["resume"].items()):
        print(f"  resume.{agent} = {argv!r}")
    print(f"data: {store.state_dir()}")
    print(f"  {len(store.load_archive().get('entries', {}))} archived sessions")


COMMANDS = {"open": cmd_open, "popup": cmd_popup, "hook": cmd_hook, "list": cmd_list, "check": cmd_check}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(f"usage: earmark.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    COMMANDS[argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
