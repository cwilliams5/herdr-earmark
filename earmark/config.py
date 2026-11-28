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
    title_first = "tab"    which name leads in the archive list: "tab" (the
                           name you gave the tab or pane, when you gave one)
                           or "agent" (the agent's own title for the session).
                           The other is shown dimmed beside it.
    debug_log = false      append every hook's event to events.jsonl in the
                           state dir.

    [sidebar]              what Earmark shows in Herdr's sidebar (only where
                           Herdr's rows ask for it: `earmark rows`)
    counts = ["blocked", "working", "done", "suspended", "archived"]
                           the numbers on each workspace's row, in this
                           order: agents needing input, working, done (done
                           or idle), suspended tabs, archived sessions; and
                           "note" for a mark on workspaces with a note. A
                           zero is never shown.
    counts_line = "same"   "same" (after the workspace's name; numbers that
                           don't fit go, from the right) or "new" (a line of
                           their own under the name)
    agent_row = ["model", "effort", "context"]
                           the second line of each agent (Claude Code,
                           Codex, Grok): what's shown, in this order
    context_levels = [70, 85, 95]
                           context use from which the next colour in
                           [colors] context applies (up to 4)
    write_herdr_config = false
                           true: Earmark keeps its rows in a marked block of
                           Herdr's config.toml (and recolours it when the
                           Omarchy theme changes; the theme hook follows
                           this too); false: `earmark rows` prints the
                           block to paste yourself, and nothing is written

    [notes]                workspace notes
    read_transcripts = false
                           true: the /herdr-note skill may also read the end
                           of each other tab's transcript (more detail, but
                           transcripts hold the web pages, files and command
                           output agents read, where planted instructions can
                           hide, read by a Claude that may act on its own);
                           false: it gets each tab's recent requests, the end
                           of its recent replies and its tools' names only

    [colors]               each: "#rrggbb" or "theme:<name>" (a colour of the
                           current Omarchy theme: red, yellow, green, blue,
                           magenta, orange, accent, foreground,
                           dark_foreground...), plus "bold" and/or "dim"
    blocked = "theme:red bold"     working = "theme:yellow"
    done = "theme:green"           suspended = "theme:blue"
    archived = "dim"               note = "theme:accent"
    model = "theme:foreground"     effort = "theme:dark_foreground"
    context = ["theme:green", "theme:yellow", "theme:red bold", "theme:magenta bold"]
                           one more than context_levels

    [resume]               reopen commands, per agent name as Herdr reports
    claude = ["command", "claude", "--resume", "{id}"]   it; {id} is the
                           session id, always a whole argument (never inside
                           sh -c "..."); `command` keeps a shell alias or
                           function named claude out of it

    [suspend]              suspend idle agent tabs in place to free memory:
                           the tab stays, the agent ends, and the tab shows
                           what was on screen with "Enter to resume".
    when = "off"           "off"; "manual" (only the suspend key); "time"
                           (idle for idle_minutes); "memory" (when available
                           memory falls below memory_below percent; Linux);
                           "count" (keep the keep_awake most recently used
                           agents awake). The key works in every mode but off.
    idle_minutes = 60      time: minutes without activity before suspending.
    memory_below = 20      memory: suspend the longest-idle agents while less
                           than this percent of memory is available, until
                           5 points more is.
    keep_awake = 8         count: how many agents stay awake.
    resume_on = "enter"    "enter" (press Enter in the tab) or "view" (stay on
                           the tab for a moment).
    show = "frozen"        "frozen" (the agent's last screen, dimmed) or
                           "notice" (a short notice); both say "Enter to resume".
    tab_mark = "💤"        put in front of a suspended tab's name while it's
                           suspended (display only; "" for none).
    suspend_unseen = true  automatic modes also take an agent whose finished
                           answer you haven't looked at (Herdr's "done");
                           its placeholder says it's unread. false keeps
                           those awake.
    messages = "popup"     how the suspend key answers: "popup" (a small
                           Earmark popup; a "suspend anyway?" question takes
                           y) or "toast" (Herdr's notifications, which need
                           [ui.toast] delivery on in Herdr's config.toml; a
                           question takes a second press of the key within
                           10 seconds). Whenever Herdr answers that it
                           didn't show a toast, the popup is used instead.

    Agents are never suspended automatically while working, waiting on a
    question, holding unsent text (or where Earmark can't read the prompt),
    running a command (tests, builds, background tasks) or sharing their
    terminal with one, waiting on a Claude /loop wake-up or scheduled task,
    with Remote Control on, started with options or a wrapper Earmark can't
    bring back, from a nested shell, or in the tab in view; an unseen result
    only with suspend_unseen. Memory and count modes also wait until an agent
    has been quiet for 10 minutes. While config.toml can't be read, or has
    a key or value that isn't valid, the defaults stand in for what's wrong,
    and nothing is pruned or suspended automatically until it's fixed.
"""
import os
import re

try:
    import tomllib
except ImportError:  # Python < 3.11 (macOS's built-in python3 is 3.9)
    tomllib = None

FALLBACK_DAYS = 30  # for what Earmark can't look into, when keep_days is unset

SUSPEND_DEFAULTS = {"when": "off", "idle_minutes": 60, "memory_below": 20, "keep_awake": 8,
                    "resume_on": "enter", "show": "frozen", "tab_mark": "💤", "suspend_unseen": True,
                    "messages": "popup"}
SUSPEND_MODES = ("off", "manual", "time", "memory", "count")
AUTO_MODES = ("time", "memory", "count")

COUNT_ITEMS = ("blocked", "working", "done", "suspended", "archived", "note")
AGENT_ITEMS = ("model", "effort", "context")
MAX_LEVELS = 4  # context thresholds; one more colour than thresholds, so five colours at most

SIDEBAR_DEFAULTS = {"counts": ["blocked", "working", "done", "suspended", "archived"], "counts_line": "same",
                    "agent_row": ["model", "effort", "context"], "context_levels": [70, 85, 95],
                    "write_herdr_config": False}
COLOR_DEFAULTS = {"blocked": "theme:red bold", "working": "theme:yellow", "done": "theme:green",
                  "suspended": "theme:blue", "archived": "dim", "note": "theme:accent",
                  "model": "theme:foreground", "effort": "theme:dark_foreground",
                  "context": ["theme:green", "theme:yellow", "theme:red bold", "theme:magenta bold"]}

# Settings earlier versions had, now without effect: never a problem (an old
# config.toml mustn't pause automatic suspends), but `check` says so.
RETIRED = {"report_count": "1.2 replaced the \"N archived\" token with [sidebar] counts"}

NOTES_DEFAULTS = {"read_transcripts": False}

DEFAULTS = {"keep_days": None, "title_first": "tab", "debug_log": False, "resume": {},
            "suspend": SUSPEND_DEFAULTS, "sidebar": SIDEBAR_DEFAULTS, "colors": COLOR_DEFAULTS,
            "notes": NOTES_DEFAULTS}


def config_dir():
    """Herdr passes it to hooks and actions; `earmark.py check` run by hand
    finds it where Herdr keeps it (XDG_CONFIG_HOME, else ~/.config)."""
    return os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
        "herdr", "plugins", "config", "io.github.cwilliams5.earmark")


def config_path():
    return os.path.join(config_dir(), "config.toml")


def _read():
    """(the file's data, a problem with it). Only a missing file means "the
    defaults, all is well" (data None, no problem); one that can't be read
    (permissions, a link to nowhere) or parsed is a problem."""
    path = config_path()
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        if isinstance(e, FileNotFoundError) and not os.path.lexists(path):
            return None, None
        return None, f"can't read config.toml ({e.strerror or e})"
    errors = []
    try:
        text = raw.decode("utf-8")
        # Without tomllib, a line the small parser can't read is skipped and
        # the rest still applies; the line is reported as a problem.
        data = tomllib.loads(text) if tomllib else parse_simple_toml(text, errors=errors)
    except (ValueError, UnicodeDecodeError) as e:
        return None, str(e)
    problems = errors + settings_problems(data)
    return data, "; ".join(problems) or None


def load():
    """The settings. A problem with the file (it can't be read or parsed, or
    a key or value isn't valid) never breaks Herdr's hooks: the defaults
    stand in for what couldn't be read, and `_broken` says what's wrong, so
    nothing that loses data runs meanwhile (no pruning, no automatic
    suspends; the key says so)."""
    cfg = dict(DEFAULTS, suspend=dict(SUSPEND_DEFAULTS), sidebar=sidebar_settings({}), colors=color_settings({}),
               notes=dict(NOTES_DEFAULTS))
    data, problem = _read()
    if problem:
        cfg["_broken"] = problem
    if data is None:
        return cfg
    days = data.get("keep_days")
    if isinstance(days, int) and not isinstance(days, bool) and days >= 0:  # true is an int in Python
        cfg["keep_days"] = days
    if isinstance(data.get("debug_log"), bool):
        cfg["debug_log"] = data["debug_log"]
    if data.get("title_first") in ("tab", "agent"):
        cfg["title_first"] = data["title_first"]
    resume = data.get("resume")
    if isinstance(resume, dict):
        cfg["resume"] = {k: v for k, v in resume.items() if _resume_ok(v)}
    if isinstance(data.get("suspend"), dict):
        cfg["suspend"] = suspend_settings(data["suspend"])
    if isinstance(data.get("sidebar"), dict):
        cfg["sidebar"] = sidebar_settings(data["sidebar"])
    if isinstance(data.get("colors"), dict):
        cfg["colors"] = color_settings(data["colors"])
    if isinstance(data.get("notes"), dict) and isinstance(data["notes"].get("read_transcripts"), bool):
        cfg["notes"] = {"read_transcripts": data["notes"]["read_transcripts"]}
    if len(cfg["colors"]["context"]) != len(cfg["sidebar"]["context_levels"]) + 1:
        cfg["colors"]["context"] = fit_context_colors(cfg["colors"]["context"], len(cfg["sidebar"]["context_levels"]) + 1)
    return cfg


def _resume_ok(value):
    return isinstance(value, list) and bool(value) and all(isinstance(x, str) for x in value)


def settings_problems(data):
    """Every key or value in config.toml that isn't valid (and so was
    ignored)."""
    out = []
    for key, value in data.items():
        if key == "keep_days":
            if not _int(value, 0, 10 ** 6):
                out.append(f"keep_days = {value!r} isn't a number of days (0 or more)")
        elif key == "debug_log":
            if not isinstance(value, bool):
                out.append(f"{key} = {value!r} isn't true or false")
        elif key in RETIRED:
            pass  # without effect now; `check` says so (retired()), never a problem
        elif key == "title_first":
            if value not in ("tab", "agent"):
                out.append(f'title_first = {value!r} isn\'t "tab" or "agent"')
        elif key == "resume":
            if not isinstance(value, dict):
                out.append("[resume] isn't a table")
            else:
                out += [f"[resume] {k} isn't a list of words" for k, v in value.items() if not _resume_ok(v)]
        elif key == "suspend":
            out += suspend_problems(value) if isinstance(value, dict) else ["[suspend] isn't a table"]
        elif key == "sidebar":
            out += sidebar_problems(value) if isinstance(value, dict) else ["[sidebar] isn't a table"]
        elif key == "colors":
            out += color_problems(value) if isinstance(value, dict) else ["[colors] isn't a table"]
        elif key == "notes":
            if not isinstance(value, dict):
                out.append("[notes] isn't a table")
            else:
                out += [f"[notes] {k} = {v!r} isn't true or false" if k in NOTES_DEFAULTS else
                        f"[notes] {k} isn't a setting" for k, v in value.items()
                        if k not in NOTES_DEFAULTS or not isinstance(v, bool)]
        else:
            out.append(f"{key} isn't a setting")
    return out


def _int(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def suspend_settings(raw):
    """The [suspend] table, each key checked; a bad value keeps its default."""
    out = dict(SUSPEND_DEFAULTS)
    if raw.get("when") in SUSPEND_MODES:
        out["when"] = raw["when"]
    if _int(raw.get("idle_minutes"), 1, 100000):
        out["idle_minutes"] = raw["idle_minutes"]
    if _int(raw.get("memory_below"), 1, 90):
        out["memory_below"] = raw["memory_below"]
    if _int(raw.get("keep_awake"), 0, 1000):
        out["keep_awake"] = raw["keep_awake"]
    if raw.get("resume_on") in ("enter", "view"):
        out["resume_on"] = raw["resume_on"]
    if raw.get("show") in ("frozen", "notice"):
        out["show"] = raw["show"]
    if isinstance(raw.get("suspend_unseen"), bool):
        out["suspend_unseen"] = raw["suspend_unseen"]
    if raw.get("messages") in ("popup", "toast"):
        out["messages"] = raw["messages"]
    mark = raw.get("tab_mark")
    if isinstance(mark, str) and len(mark) <= 8 and not mark.startswith("-") and mark.isprintable() \
            and " " not in mark:
        out["tab_mark"] = mark
    return out


def suspend_problems(raw):
    """[suspend] values that were ignored, for `earmark.py check`."""
    if not isinstance(raw, dict):
        return []
    good = suspend_settings(raw)
    return [f"[suspend] {k} = {raw[k]!r} isn't valid; using {good[k]!r}"
            for k in raw if k in SUSPEND_DEFAULTS and raw[k] != good[k]] + \
           [f"[suspend] {k} isn't a setting" for k in raw if k not in SUSPEND_DEFAULTS]


def _items(value, allowed):
    """A list of known item names without repeats, or None."""
    if not isinstance(value, list) or not all(isinstance(x, str) and x in allowed for x in value):
        return None
    return value if len(set(value)) == len(value) else None


def _levels(value):
    """Context thresholds: up to MAX_LEVELS whole percents, rising, or None."""
    if not isinstance(value, list) or len(value) > MAX_LEVELS or not all(_int(x, 1, 100) for x in value):
        return None
    return value if all(a < b for a, b in zip(value, value[1:])) else None


def sidebar_settings(raw):
    """The [sidebar] table, each key checked; a bad value keeps its default."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in SIDEBAR_DEFAULTS.items()}
    counts = _items(raw.get("counts"), COUNT_ITEMS)
    if counts is not None:
        out["counts"] = counts
    if raw.get("counts_line") in ("same", "new"):
        out["counts_line"] = raw["counts_line"]
    row = _items(raw.get("agent_row"), AGENT_ITEMS)
    if row is not None:
        out["agent_row"] = row
    levels = _levels(raw.get("context_levels"))
    if levels is not None:
        out["context_levels"] = levels
    if isinstance(raw.get("write_herdr_config"), bool):
        out["write_herdr_config"] = raw["write_herdr_config"]
    return out


def sidebar_problems(raw):
    good = sidebar_settings(raw)
    return [f"[sidebar] {k} = {raw[k]!r} isn't valid; using {good[k]!r}"
            for k in raw if k in SIDEBAR_DEFAULTS and raw[k] != good[k]] + \
           [f"[sidebar] {k} isn't a setting" for k in raw if k not in SIDEBAR_DEFAULTS]


HEX = re.compile(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})")
_THEME = re.compile(r"theme:[a-z][a-z0-9_]{0,31}")


def color_spec(value):
    """A colour setting as (colour, bold, dim), or None if it isn't one:
    "#rrggbb" / "#rgb" / "theme:<name>", optionally with "bold" and/or
    "dim", in any order; at least one word; colour at most once."""
    if not isinstance(value, str) or len(value) > 64:
        return None
    color, bold, dim = None, False, False
    words = value.split()
    for w in words:
        if w == "bold" and not bold:
            bold = True
        elif w == "dim" and not dim:
            dim = True
        elif color is None and (HEX.fullmatch(w) or _THEME.fullmatch(w)):
            color = w
        else:
            return None
    return (color, bold, dim) if words else None


def fit_context_colors(colors, n):
    """`colors` made n long: cut, or the last one repeated (a mismatch is
    reported by color_problems; the levels still get a colour each)."""
    colors = list(colors) or list(COLOR_DEFAULTS["context"][:1])
    return (colors + [colors[-1]] * n)[:n]


def color_settings(raw):
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in COLOR_DEFAULTS.items()}
    for k, v in raw.items():
        if k == "context":
            if isinstance(v, list) and 1 <= len(v) <= MAX_LEVELS + 1 and all(color_spec(x) for x in v):
                out[k] = list(v)
        elif k in COLOR_DEFAULTS and color_spec(v):
            out[k] = v
    return out


def color_problems(raw):
    good = color_settings(raw)
    return [f"[colors] {k} = {raw[k]!r} isn't a colour (\"#rrggbb\" or \"theme:<name>\", with bold/dim); "
            f"using {good[k]!r}" for k in raw if k in COLOR_DEFAULTS and raw[k] != good[k]] + \
           [f"[colors] {k} isn't a setting" for k in raw if k not in COLOR_DEFAULTS]


def context_mismatch(cfg_data):
    """[colors] context must have one more colour than [sidebar]
    context_levels has thresholds: a note for `check`, or None."""
    levels = sidebar_settings(cfg_data.get("sidebar") or {})["context_levels"] \
        if isinstance(cfg_data.get("sidebar"), dict) else SIDEBAR_DEFAULTS["context_levels"]
    colors = color_settings(cfg_data.get("colors") or {})["context"] \
        if isinstance(cfg_data.get("colors"), dict) else COLOR_DEFAULTS["context"]
    if len(colors) != len(levels) + 1:
        return (f"[colors] context has {len(colors)} colours for {len(levels)} context_levels "
                f"(needs {len(levels) + 1}); the last colour is repeated or the extra ones left out")
    return None


def retired():
    """Settings in config.toml that no longer do anything: (key, why)."""
    data = _read()[0] or {}
    return [(k, RETIRED[k]) for k in data if k in RETIRED]


def check():
    """A problem with config.toml, or None (for `earmark.py check`)."""
    return _read()[1]


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


_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


def _unescape(text):
    """A TOML basic string's escapes (\\n, \\", \\\\, \\uXXXX, \\UXXXXXXXX),
    leaving every other character, non-ASCII included, as it is."""
    def one(m):
        e = m.group(1)
        if e[0] in "uU":
            try:
                return chr(int(e[1:], 16))
            except ValueError:
                return m.group(0)
        return _ESCAPES.get(e, m.group(0))
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)", one, text)


def _open_brackets(value):
    bare = re.sub(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'', '""', value)
    return bare.count("[") - bare.count("]")


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
        # An array that goes on over the next lines, until its brackets
        # balance (a row of Herdr's rows on a line of its own is no table).
        while value.startswith("[") and _open_brackets(value) > 0 and n < len(lines):
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
            value = _unescape(text_value)
        elif boolean:
            value = boolean == "true"
        elif number:
            value = int(number)
        elif array.strip() and re.fullmatch(r"\s*-?\d+\s*(?:,\s*-?\d+\s*)*,?\s*", array):
            value = [int(v) for v in re.findall(r"-?\d+", array)]  # [70, 85, 95]
        else:
            value = [_unescape(v.strip()[1:-1]) for v in re.findall(r'"(?:[^"\\]|\\.)*"', array)]
        (table if table is not None else data)[key.strip().strip('"')] = value
    return data
