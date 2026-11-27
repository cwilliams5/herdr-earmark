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
    """Panes, workspaces and tabs as Herdr reports them right now. A reply
    of another shape is a HerdrError (never a crash halfway through)."""
    try:
        panes = run("pane", "list")["panes"]
        workspaces = run("workspace", "list")["workspaces"]
        tabs = run("tab", "list")["tabs"]
        return {
            "panes": {p["pane_id"]: p for p in panes},
            "workspaces": {w["workspace_id"]: w for w in workspaces},
            "tabs": {t["tab_id"]: t for t in tabs},
        }
    except (TypeError, KeyError, AttributeError) as e:
        raise HerdrError(f"Herdr answered in a shape Earmark doesn't know ({e!r})")


def pane(pane_id):
    try:
        p = run("pane", "get", pane_id)["pane"]
    except (TypeError, KeyError) as e:
        raise HerdrError(f"Herdr answered in a shape Earmark doesn't know ({e!r})")
    if not isinstance(p, dict):
        raise HerdrError("Herdr answered in a shape Earmark doesn't know")
    return p


def safe_label(label):
    """A tab or workspace name that's safe to pass on Herdr's command line, or
    "". Herdr 0.9.5 scans the whole argv for its global flags (-h, --help,
    --session=..., --remote=...) before anything else, so a name like "-h"
    or "--session=x" would change what the command does. Such names are
    left out (the tab gets Herdr's default name)."""
    label = label or ""
    return "" if label.startswith("-") else label


def new_tab(workspace_id, cwd, label, focus=True):
    """Open a tab; returns (tab id, root pane id)."""
    args = ["tab", "create", "--workspace", workspace_id, "--focus" if focus else "--no-focus"]
    if cwd and os.path.isdir(cwd):
        args += ["--cwd", cwd]
    if safe_label(label):
        args += ["--label", label]
    result = run(*args)
    return result["tab"]["tab_id"], (result.get("root_pane") or result.get("pane"))["pane_id"]


def run_in_pane(pane_id, argv, env=""):
    """Type a command into a pane's shell and run it (`env`: a shell prefix
    such as "CLAUDE_CONFIG_DIR=... ")."""
    run("pane", "run", pane_id, env + shlex.join(argv))


def report_count(workspace_id, text, seq):
    """Set or clear the $earmark sidebar token on one workspace. Herdr's CLI
    takes the workspace id before the options (0.9.5 rejects it last).
    Herdr ignores a lower seq from the same source, so seq is taken when the
    count is worked out (under Earmark's lock), not when it's sent."""
    from . import PLUGIN_ID
    args = ["workspace", "report-metadata", workspace_id, "--source", PLUGIN_ID, "--seq", str(seq)]
    args += ["--token", f"earmark={text}"] if text else ["--clear-token", "earmark"]
    run(*args)


def process_info(pane_id):
    """The pane's shell pid, its foreground process group and the processes
    in it (`pane process-info`)."""
    result = run("pane", "process-info", "--pane", pane_id)
    info = result.get("process_info") if isinstance(result, dict) else None
    if not isinstance(info, dict):
        return {}
    info["foreground_processes"] = [x for x in info.get("foreground_processes") or [] if isinstance(x, dict)]
    return info


def read_screen(pane_id, rows=None, timeout=10):
    """What the pane shows, with its colours (ANSI), from the bottom: the
    last `rows` lines (the pane's height) of what Herdr keeps. `--source
    visible` would follow the user's scroll position, and a pane scrolled up
    shows an old prompt box. `pane read` answers with the text itself, not
    JSON."""
    binary = os.environ.get("HERDR_BIN_PATH") or "herdr"
    source = ["--source", "recent", "--lines", str(int(rows))] if rows else ["--source", "visible"]
    try:
        out = subprocess.run([binary, "pane", "read", pane_id, *source, "--format", "ansi"],
                             capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HerdrError(f"herdr pane read: {e}") from e
    if out.returncode != 0:
        raise HerdrError(f"herdr pane read {pane_id}: {out.stderr.decode('utf-8', 'replace').strip() or out.returncode}")
    return out.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def send_enter(pane_id):
    run("pane", "send-keys", pane_id, "enter")


def config_path():
    """Herdr's own config.toml (HERDR_CONFIG_PATH overrides it, as in Herdr)."""
    return os.environ.get("HERDR_CONFIG_PATH") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "herdr", "config.toml")


def setting(table, key):
    """One value from Herdr's own config.toml (read only, never changed):
    `setting("ui.toast", "delivery")`. None when it's unset or unreadable."""
    try:
        with open(config_path(), "rb") as f:
            raw = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    from . import config
    try:
        if config.tomllib:
            node = config.tomllib.loads(raw)
            for part in table.split("."):
                node = node.get(part) if isinstance(node, dict) else None
        else:
            node = config.parse_simple_toml(raw, errors=[]).get(table)
    except (ValueError, AttributeError):
        return None
    return node.get(key) if isinstance(node, dict) else None


def toasts_on():
    """Whether Herdr's config turns its notifications on ([ui.toast]
    delivery, "off" unless set): a hint for `earmark.py check` only; whether
    a toast was shown comes from Herdr's own reply (notify)."""
    return (setting("ui.toast", "delivery") or "off") != "off"


def notify(title, body=""):
    """A Herdr notification; never fails the caller. Returns Herdr's own
    answer to whether it was shown (its reply's `shown`: toasts off, rate
    limited, busy or no client all say False), or None when it didn't say."""
    try:
        reply = run("notification", "show", title, *(["--body", body] if body else []))
    except HerdrError:
        return False
    shown = reply.get("shown") if isinstance(reply, dict) else None
    return shown if isinstance(shown, bool) else None

