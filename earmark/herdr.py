"""Calls into the Herdr that launched us, through its CLI (CLAUDE.md, rule 2)."""
import json
import os
import shlex
import subprocess


class HerdrError(RuntimeError):
    pass


def run(*args, timeout=10):
    """Run `herdr <args>` and return the reply's "result" object."""
    binary = os.environ.get("HERDR_BIN_PATH") or "herdr"
    try:
        out = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HerdrError(f"herdr {args[0] if args else ''}: {e}") from e
    if out.returncode != 0:
        raise HerdrError(f"herdr {' '.join(args)}: {out.stderr.strip() or out.returncode}")
    if not out.stdout.strip():
        return None
    try:
        reply = json.loads(out.stdout)
    except ValueError as e:
        raise HerdrError(f"herdr {' '.join(args)}: unreadable reply") from e
    if isinstance(reply, dict) and "error" in reply:
        raise HerdrError(f"herdr {' '.join(args)}: {reply['error']}")
    return reply.get("result") if isinstance(reply, dict) else reply


def session_name(env=None):
    """The Herdr session we run in: HERDR_SESSION for a named one, else "default"."""
    env = os.environ if env is None else env
    return env.get("HERDR_SESSION") or "default"


def snapshot():
    """Panes, workspaces and tabs as Herdr reports them right now."""
    panes = run("pane", "list")["panes"]
    workspaces = run("workspace", "list")["workspaces"]
    tabs = run("tab", "list")["tabs"]
    return {
        "panes": {p["pane_id"]: p for p in panes},
        "workspaces": {w["workspace_id"]: w for w in workspaces},
        "tabs": {t["tab_id"]: t for t in tabs},
    }


def pane(pane_id):
    return run("pane", "get", pane_id)["pane"]


def new_tab(workspace_id, cwd, label, focus=True):
    """Open a tab; returns (tab id, root pane id)."""
    args = ["tab", "create", "--workspace", workspace_id, "--focus" if focus else "--no-focus"]
    if cwd and os.path.isdir(cwd):
        args += ["--cwd", cwd]
    if label:
        args += ["--label", label]
    result = run(*args)
    return result["tab"]["tab_id"], (result.get("root_pane") or result.get("pane"))["pane_id"]


def run_in_pane(pane_id, argv):
    """Type a command into a pane's shell and run it."""
    run("pane", "run", pane_id, shlex.join(argv))


def report_count(workspace_id, text):
    """Set or clear the $earmark sidebar token on one workspace. Herdr's CLI
    takes the workspace id before the options (0.9.5 rejects it last)."""
    from . import PLUGIN_ID
    args = ["workspace", "report-metadata", workspace_id, "--source", PLUGIN_ID, "--seq", str(time_ns())]
    args += ["--token", f"earmark={text}"] if text else ["--clear-token", "earmark"]
    run(*args)


def time_ns():
    import time
    return time.time_ns()
