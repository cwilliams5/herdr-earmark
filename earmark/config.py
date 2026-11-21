"""config.toml in the plugin's config dir (`herdr plugin config-dir
io.github.cwilliams5.earmark`). Every key is optional:

    keep_days = 30         forget sessions this many days after their last
                           activity. Unset (the default): sessions of agents
                           Earmark can look into (Claude Code, Codex, Grok)
                           stay as long as the agent keeps them, so the
                           agent's own retention decides (Claude Code's
                           cleanupPeriodDays, default 30); other agents'
                           sessions, and closed workspaces, go after 30
                           days. 0 keeps everything until the agent's files
                           are gone.
    report_count = true    publish "N archived" as the $earmark sidebar
                           token; it only shows if you add $earmark to
                           ui.sidebar.spaces.rows in Herdr's config.
    title_first = "tab"    which name leads in the archive list: "tab" (the
                           name you gave the tab or pane, when you gave one)
                           or "agent" (the agent's own title for the session).
                           The other is shown dimmed beside it.
    debug_log = false      append every hook's event to events.jsonl in the
                           state dir.

    [resume]               reopen commands, per agent name as Herdr reports
    claude = ["claude", "--resume", "{id}"]      it; {id} is the session id
"""
import os
import re

try:
    import tomllib
except ImportError:  # Python < 3.11 (macOS's built-in python3 is 3.9)
    tomllib = None

FALLBACK_DAYS = 30  # for what Earmark can't look into, when keep_days is unset

DEFAULTS = {"keep_days": None, "report_count": True, "title_first": "tab", "debug_log": False, "resume": {}}


def config_path():
    directory = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or os.path.expanduser(
        "~/.config/herdr/plugins/config/io.github.cwilliams5.earmark")
    return os.path.join(directory, "config.toml")


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "rb") as f:
            raw = f.read()
    except OSError:
        return cfg
    try:
        data = tomllib.loads(raw.decode("utf-8")) if tomllib else parse_simple_toml(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return cfg  # a broken file never breaks Herdr's hooks; `earmark.py check` reports it
    if isinstance(data.get("keep_days"), int) and data["keep_days"] >= 0:
        cfg["keep_days"] = data["keep_days"]
    for key in ("report_count", "debug_log"):
        if isinstance(data.get(key), bool):
            cfg[key] = data[key]
    if data.get("title_first") in ("tab", "agent"):
        cfg["title_first"] = data["title_first"]
    resume = data.get("resume")
    if isinstance(resume, dict):
        cfg["resume"] = {k: v for k, v in resume.items()
                         if isinstance(v, list) and v and all(isinstance(x, str) for x in v)}
    return cfg


def check():
    """A problem with config.toml, or None (for `earmark.py check`)."""
    try:
        with open(config_path(), "rb") as f:
            raw = f.read().decode("utf-8")
        (tomllib.loads if tomllib else parse_simple_toml)(raw)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return str(e)
    return None


_VALUE = re.compile(r'''^(?:"((?:[^"\\]|\\.)*)"|(true|false)|(-?\d+)|\[(.*)\])$''')


def parse_simple_toml(text):
    """The part of TOML Earmark's settings use, for Pythons without tomllib:
    comments, [tables], and key = string / integer / true / false / an array
    of strings on one line."""
    data, table = {}, None
    for n, line in enumerate(text.splitlines(), 1):
        line = re.sub(r'''\s+#[^"]*$|^\s*#.*$''', "", line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            table = data.setdefault(line[1:-1].strip(), {})
            continue
        key, sep, value = line.partition("=")
        m = _VALUE.match(value.strip())
        if not sep or not m:
            raise ValueError(f"config.toml line {n}: can't read {line!r}")
        text_value, boolean, number, array = m.groups()
        if text_value is not None:
            value = bytes(text_value, "utf-8").decode("unicode_escape")
        elif boolean:
            value = boolean == "true"
        elif number:
            value = int(number)
        else:
            value = [v.strip()[1:-1] for v in re.findall(r'"(?:[^"\\]|\\.)*"', array)]
        (table if table is not None else data)[key.strip().strip('"')] = value
    return data
