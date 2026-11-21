#!/usr/bin/env python3
"""Earmark: closed agent sessions, filed under their Herdr workspace.

Herdr runs this with a subcommand from herdr-plugin.toml:

    open           the "open" action: show the archive popup
    popup          the popup itself (a terminal UI)
    record-event   phase A2: log what Herdr reports on an event

Python standard library only (see CLAUDE.md, rule 1).
"""
import fcntl
import json
import os
import subprocess
import sys
import time

PLUGIN_ID = "io.github.cwilliams5.earmark"


def herdr(*args):
    """Run the Herdr CLI that launched us and return its parsed JSON reply."""
    binary = os.environ.get("HERDR_BIN_PATH") or "herdr"
    out = subprocess.run([binary, *args], capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)}: {out.stderr.strip() or out.returncode}")
    return json.loads(out.stdout) if out.stdout.strip() else None


def state_dir():
    path = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
        "~/.local/state/earmark-dev")
    os.makedirs(path, exist_ok=True)
    return path


def context():
    try:
        return json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    except ValueError:
        return {}


def append_jsonl(name, record):
    """Append one JSON line under a lock: several hooks can run at once."""
    with open(os.path.join(state_dir(), name), "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- commands

def cmd_open():
    herdr("plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "archive")


def cmd_record_event():
    env = {k: v for k, v in os.environ.items()
           if k.startswith("HERDR_") and k not in ("HERDR_PLUGIN_EVENT_JSON", "HERDR_PLUGIN_CONTEXT_JSON")}
    record = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": os.environ.get("HERDR_PLUGIN_EVENT"),
        "payload": _json_env("HERDR_PLUGIN_EVENT_JSON"),
        "context": _json_env("HERDR_PLUGIN_CONTEXT_JSON"),
        "env": env,
    }
    # What the pane list says at the moment the hook runs: is a closed pane
    # still listed, and does it still name its session?
    try:
        panes = herdr("pane", "list")["result"]["panes"]
        record["panes_now"] = [
            {"pane": p.get("pane_id"), "tab": p.get("tab_id"),
             "agent": p.get("agent"), "session": (p.get("agent_session") or {}).get("value")}
            for p in panes]
    except Exception as e:  # recorder only: never fail the hook
        record["panes_now_error"] = str(e)
    append_jsonl("events.jsonl", record)


def _json_env(name):
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def cmd_popup():
    import curses

    ctx = context()

    def draw(screen):
        curses.set_escdelay(25)
        curses.curs_set(0)
        curses.use_default_colors()
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        last = "nothing yet"
        while True:
            screen.erase()
            lines = [
                "Earmark (phase A1 check)",
                "",
                f"workspace: {json.dumps(ctx.get('workspace'), ensure_ascii=False)[:200]}",
                f"tab:       {json.dumps(ctx.get('tab'), ensure_ascii=False)[:200]}",
                f"context keys: {', '.join(sorted(ctx)) or '(none)'}",
                "",
                f"last input: {last}",
                "",
                "Click anywhere, scroll, or press keys. Esc or q closes.",
            ]
            h, w = screen.getmaxyx()
            for i, line in enumerate(lines[:h]):
                screen.addnstr(i, 0, line, max(w - 1, 1))
            screen.refresh()
            key = screen.get_wch()
            if key in ("q", "\x1b"):
                return
            if key == curses.KEY_MOUSE:
                try:
                    _, x, y, _, bstate = curses.getmouse()
                    last = f"mouse at column {x}, row {y}, buttons {bstate:#x}"
                except curses.error:
                    last = "mouse (unreadable)"
            else:
                last = f"key {key!r}"

    append_jsonl("popup.jsonl", {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "context": ctx,
                                 "env": {k: v for k, v in os.environ.items() if k.startswith("HERDR_")
                                         and k != "HERDR_PLUGIN_CONTEXT_JSON"}})
    curses.wrapper(draw)


COMMANDS = {"open": cmd_open, "popup": cmd_popup, "record-event": cmd_record_event}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(f"usage: earmark.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    COMMANDS[argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
