"""config.toml in the plugin's config dir (`herdr plugin config-dir
io.github.cwilliams5.earmark`). Every key is optional:

    keep_days = 30         forget sessions this many days after their last
                           activity. Unset (the default): sessions of agents
                           Earmark can look into (Claude Code, Codex, Grok)
                           stay as long as the agent keeps them, so the
                           agent's own retention decides (Claude Code's
                           cleanupPeriodDays, default 30); other agents'
                           sessions, and closed workspaces, go after 30
                           days. 0 keeps sessions until the agent's files
                           are gone, and closed workspaces until forgotten.
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
    claude = ["claude", "--resume", "{id}"]      it; {id} is the session id,
                           always a whole argument (never inside sh -c "...")
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
        text = raw.decode("utf-8")
        # Without tomllib, a line the small parser can't read is skipped and
        # the rest still applies; `earmark.py check` reports the line.
        data = tomllib.loads(text) if tomllib else parse_simple_toml(text, errors=[])
    except (ValueError, UnicodeDecodeError):
        return cfg  # a broken file never breaks Herdr's hooks; `earmark.py check` reports it
    days = data.get("keep_days")
    if isinstance(days, int) and not isinstance(days, bool) and days >= 0:  # true is an int in Python
        cfg["keep_days"] = days
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
        if tomllib:
            tomllib.loads(raw)
        else:
            errors = []
            parse_simple_toml(raw, errors=errors)
            if errors:
                return "; ".join(errors)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return str(e)
    return None


_VALUE = re.compile(r"""^(?:"((?:[^"\\]|\\.)*)"|(true|false)|(-?\d+)|\[(.*)\])$""", re.S)


def _strip_comment(line):
    """The line without its # comment; a # inside a "string" stays."""
    in_string = escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
        elif ch == "\\" and in_string:
            escaped = True
        elif ch == '"':
            in_string = not in_string
        elif ch == "#" and not in_string:
            return line[:i]
    return line


def parse_simple_toml(text, errors=None):
    """The part of TOML Earmark's settings use, for Pythons without tomllib
    (3.9 and 3.10): comments, [tables], and key = string / integer / true /
    false / an array of strings, which may span several lines. With an
    errors list, a line it can't read is noted there and skipped; without
    one, it raises ValueError."""
    data, table = {}, None
    lines = text.splitlines()
    n = 0
    while n < len(lines):
        start = n + 1
        line = _strip_comment(lines[n]).strip()
        n += 1
        if not line:
            continue
        if line.startswith("[") and line.endswith("]") and "=" not in line:
            table = data.setdefault(line[1:-1].strip(), {})
            continue
        key, sep, value = line.partition("=")
        value = value.strip()
        # An array that goes on over the next lines.
        while value.startswith("[") and "]" not in value and n < len(lines):
            value += " " + _strip_comment(lines[n]).strip()
            n += 1
        m = _VALUE.match(value)
        if not sep or not m:
            problem = f"config.toml line {start}: can't read {line!r}"
            if errors is None:
                raise ValueError(problem)
            errors.append(problem)
            continue
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
