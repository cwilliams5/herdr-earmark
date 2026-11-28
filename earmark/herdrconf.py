"""Herdr's sidebar rows for Earmark's values (PLAN M6, M7).

Herdr styles a token only where its own config.toml names it (a hex `fg`,
`bold`, `dim`), so Earmark's [sidebar] and [colors] settings become a block of
Herdr config: `earmark.py rows` prints it to paste; with `write_herdr_config
= true` Earmark keeps it between its markers in Herdr's config.toml itself
and Herdr reloads it. Colours can name the current Omarchy theme's
("theme:red"), so a theme switch recolours the rows: at Earmark's next hook,
or at once with the theme-set hook (`earmark.py rows --theme-hook`).

Writing Herdr's file is guarded: nothing outside the markers changes (and
anything Herdr's own settings screen put inside them, before Earmark's first
table, is kept above them); where the user has sidebar rows of their own,
Earmark refuses and says so; a symlinked file is written through its link;
the first write keeps a copy of the file as it was (config.toml.before-earmark);
a file that changed while Earmark checked it is left for the next try; after
writing, `herdr config check` may report only what it reported before, or the
old text goes back.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

from . import config, herdr, sidebar, store

BEGIN = "# >>> earmark: sidebar rows (written by Earmark; change [sidebar] and [colors] in its config.toml) >>>"
END = "# <<< earmark <<<"
BACKUP_SUFFIX = ".before-earmark"
AGENTS = ("claude", "codex", "grok")  # rows_by_agent: other agents keep Herdr's rows
HOOK_NAME = "earmark-sidebar"

# Where Omarchy's theme isn't there to ask (another system, or a colour the
# theme doesn't name): mid tones readable on light and dark themes alike
# (3.2:1 or better on white, Catppuccin Latte and Mocha, Solarized Light,
# Gruvbox Dark, black); Herdr has light themes and switches by itself. The
# text colours have none: Herdr's own text colour stays, the soft ones dimmed.
FALLBACK = {"red": "#d0453d", "yellow": "#a77d00", "green": "#3a9a4a", "blue": "#3b7dd8", "magenta": "#a855c8",
            "purple": "#a855c8", "orange": "#cc6a1a", "cyan": "#0f8f8f", "accent": "#3b7dd8"}
SOFT = ("dark_foreground", "muted")


# ------------------------------------------------------------------ theme

def theme_file():
    return os.path.expanduser("~/.local/state/omarchy/current/theme/colors.toml")  # Omarchy's own path, not XDG


def theme_stamp():
    """What identifies the current theme's colours (the file's real path,
    size and time), or None without an Omarchy theme."""
    path = theme_file()
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [os.path.realpath(path), st.st_size, st.st_mtime_ns]


def theme_palette():
    """{name: "#hex"} of the current Omarchy theme: through Omarchy's own
    resolver when it's there (it applies each theme's fallbacks), else read
    from colors.toml; {} without a theme."""
    tool = shutil.which("omarchy-theme-color")
    if tool and os.path.exists(theme_file()):
        try:
            out = subprocess.run([tool, "--all"], capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                pairs = (line.split("\t", 1) for line in out.stdout.splitlines() if "\t" in line)
                palette = {k.strip(): v.strip() for k, v in pairs if config.HEX.fullmatch(v.strip())}
                if palette:
                    return palette
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        with open(theme_file(), encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        data = config.tomllib.loads(text) if config.tomllib else config.parse_simple_toml(text, errors=[])
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str) and config.HEX.fullmatch(v)}


def resolve(spec, palette):
    """(hex or None, bold, dim) for a colour setting."""
    parsed = config.color_spec(spec) or (None, False, False)
    color, bold, dim = parsed
    if color and color.startswith("theme:"):
        name = color[len("theme:"):]
        color = palette.get(name) or FALLBACK.get(name)
        dim = dim or (color is None and name in SOFT)
    return color, bold, dim


# ------------------------------------------------------------------ block

def _style(token, spec, palette):
    """One styled token for Herdr's rows: `dim = false` unless asked, so
    Herdr's own dimming of secondary text doesn't wash the colour out."""
    color, bold, dim = resolve(spec, palette)
    parts = [f'token = "${token}"']
    if color:
        parts.append(f'fg = "{color}"')
    if bold:
        parts.append("bold = true")
    parts.append(f"dim = {'true' if dim else 'false'}")
    return "{ " + ", ".join(parts) + " }"


def _row(items):
    return "[" + ", ".join(items) + "]"


def block(cfg, palette):
    """Herdr config for Earmark's rows, between the markers ("" when
    nothing is to be shown)."""
    side, colors = cfg["sidebar"], cfg["colors"]
    out = []
    if side["counts"]:
        counts = [_style(sidebar.PREFIX + item, colors[item], palette) for item in side["counts"]]
        if side["counts_line"] == "same":
            rows = [_row(['"state_icon"', '"workspace"'] + counts)]
        else:
            rows = [_row(['"state_icon"', '"workspace"']), _row(counts)]
        rows.append(_row(['"branch"', '"git_status"']))
        out += ["[ui.sidebar.spaces]", "rows = [", *(f"  {r}," for r in rows), "]", ""]
    if side["agent_row"]:
        second = []
        for item in side["agent_row"]:
            if item == "context":
                ctx = config.fit_context_colors(colors["context"], len(side["context_levels"]) + 1)
                second += [_style(f"{sidebar.PREFIX}ctx_{n}", spec, palette) for n, spec in enumerate(ctx, 1)]
            else:
                second.append(_style(sidebar.PREFIX + item, colors[item], palette))
        first = _row(['"state_icon"', '"machine"', '"workspace"', '"tab"'])  # Herdr's own first line
        out += ["[ui.sidebar.agents.rows_by_agent]"] + [f"{a} = [{first}, {_row(second)}]" for a in AGENTS] + [""]
    if not out:
        return ""
    return "\n".join([BEGIN] + out[:-1] + [END]) + "\n"


# ------------------------------------------------------- Herdr's config.toml

_HEADER = re.compile(r'^\s*\[\[?\s*([A-Za-z0-9_.\s"-]+?)\s*\]\]?\s*(?:#.*)?$')
_KEY = re.compile(r'^\s*([A-Za-z0-9_"-][A-Za-z0-9_.\s"-]*?)\s*=')
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'')
_TRIPLE = re.compile(r"\'\'\'.*?\'\'\'|\"\"\".*?\"\"\"")


def _dotted(name):
    return re.sub(r"\s*\.\s*", ".", name.strip()).replace('"', "")


def key_paths(text):
    """Every table and key the file sets, as full dotted names
    ("ui.sidebar.agents.rows"), from the lines alone: values are never read,
    so Herdr's nested arrays and inline tables can't hide a key, and lines
    inside a value that goes on over several lines are never taken for one."""
    table, depth, quote = "", 0, None
    for line in text.splitlines():
        if quote:  # inside a multi-line string: nothing in it is a key
            if quote in line:
                quote = None
            continue
        line_ = _TRIPLE.sub('""', line)
        opener = min((line_.find(q), q) for q in ("\'\'\'", '"""') if q in line_) if \
            ("\'\'\'" in line_ or '"""' in line_) else None
        bare = _STRING.sub('""', line_[:opener[0]] if opener else line_).split("#", 1)[0]
        if opener:
            quote = opener[1]
        if depth == 0:
            m = _HEADER.match(line)
            if m:
                table = _dotted(m.group(1))
                yield table
                continue
            k = _KEY.match(line)
            if k:
                yield (table + "." if table else "") + _dotted(k.group(1))
        depth = max(0, depth + bare.count("[") + bare.count("{") - bare.count("]") - bare.count("}"))


def _own_rows(path):
    """The name of the user's own sidebar rows setting a path belongs to, or
    None: Earmark's block defines [ui.sidebar.spaces] and rows_by_agent (a
    second definition is an error in TOML), and rows_by_agent outranks the
    user's [ui.sidebar.agents] rows in Herdr (src/config/sidebar.rs)."""
    for own in ("ui.sidebar.spaces", "ui.sidebar.agents.rows_by_agent", "ui.sidebar.agents.rows"):
        if path == own or path.startswith(own + "."):
            return own
    return None


def split(text):
    """(before, Earmark's block or None, after). A file with markers out of
    order or twice is refused (ValueError) rather than guessed at."""
    begins = [m.start() for m in re.finditer(re.escape(BEGIN), text)]
    ends = [m.start() for m in re.finditer(re.escape(END), text)]
    if not begins and not ends:
        return text, None, ""
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise ValueError("Earmark's markers in Herdr's config.toml are broken (missing, repeated or out of order)")
    stop = text.find("\n", ends[0])
    stop = len(text) if stop < 0 else stop + 1
    return text[:begins[0]], text[begins[0]:stop], text[stop:]


def conflicts(text):
    """Sidebar rows of the user's own (outside Earmark's markers) that
    Earmark's block would clash with or override."""
    before, _, after = split(text)
    return sorted({own for own in map(_own_rows, key_paths(before + after)) if own})


def _foreign(old, ours=""):
    """Lines inside Earmark's markers before its first table that Earmark
    didn't write (`ours`: what it did): they belong to the table above the
    block (Herdr's settings screen adds a key right before the next table
    header, which is Earmark's)."""
    mine = set(ours.splitlines())
    kept = []
    for line in old.splitlines(keepends=True)[1:]:
        if line.strip().startswith("[") or line.strip() == END:
            break
        if line.rstrip("\n") not in mine:
            kept.append(line)
    return "".join(kept).strip("\n") + "\n" if "".join(kept).strip() else ""


def _own_part(block):
    """A block without what _foreign() moves above it: the BEGIN line, then
    from Earmark's first table on."""
    lines = block.splitlines(keepends=True)
    for n, line in enumerate(lines[1:], 1):
        if line.strip().startswith("[") or line.strip() == END:
            return lines[0] + "".join(lines[n:])
    return block


def compose(text, new_block, ours=""):
    """Herdr's config with Earmark's block put in (or replaced, or removed
    when new_block is ""). `ours`: the block Earmark wrote there, if known."""
    before, old, after = split(text)
    if old is not None:
        return before + _foreign(old, ours) + new_block + after
    if not new_block:
        return text
    sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + new_block


class NoAnswer(Exception):
    """`herdr config check` didn't answer."""


def _parses(text):
    """False if text isn't TOML (only where Python has tomllib: 3.11+)."""
    if not config.tomllib:
        return True
    try:
        config.tomllib.loads(text)
        return True
    except ValueError:
        return False


def _check_lines():
    """`herdr config check`'s issue lines (empty: all fine)."""
    try:
        out = subprocess.run([os.environ.get("HERDR_BIN_PATH") or "herdr", "config", "check"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        raise NoAnswer(str(e)) from e
    lines = [line.strip() for line in (out.stdout + out.stderr).splitlines()]
    return set() if out.returncode == 0 else {line for line in lines if line and not line.startswith("config:")}


def _mode(path):
    try:
        return os.stat(path).st_mode & 0o777
    except OSError:
        return 0o600


def _write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    store.write_atomic(path, text, mode=_mode(path))


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def reload_all():
    """Every running Herdr session reloads its config (they share the file)."""
    binary = os.environ.get("HERDR_BIN_PATH") or "herdr"
    try:
        out = subprocess.run([binary, "session", "list", "--json"], capture_output=True, text=True, timeout=10)
        sessions = [s for s in json.loads(out.stdout).get("sessions", []) if s.get("running")]
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        sessions = [{"default": True}]
    problems = []
    for s in sessions:
        # Always named: without --session Herdr goes to HERDR_SOCKET_PATH,
        # the session of the hook running this (src/session.rs).
        name = "default" if s.get("default") else s.get("name", "")
        args = [binary, "--session", name, "server", "reload-config"]
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                problems.append((r.stderr or r.stdout).strip())
        except (OSError, subprocess.SubprocessError) as e:
            problems.append(str(e))
    return problems


def apply(cfg, palette):
    """Put Earmark's block into Herdr's config.toml and have Herdr reload
    it. Returns (status, detail): "unchanged", "written", "refused" (the
    user's own rows, broken markers), "rolled back" (Herdr found a new
    problem), "busy" (the file changed meanwhile: try again later) or "not
    reloaded"."""
    link = herdr.config_path()
    path = os.path.realpath(link)  # a symlink (stow, home-manager) stays one
    try:
        text = _read(path)
    except (OSError, UnicodeDecodeError) as e:
        return "refused", f"can't read {link}: {e}"
    try:
        own = conflicts(text)
        new = compose(text, block(cfg, palette))
    except ValueError as e:
        return "refused", str(e)
    if new == text:
        return "unchanged", ""
    if own:
        return "refused", (f"{link} has sidebar rows of its own ({', '.join(own)}); Earmark leaves it alone. "
                           "Merge `earmark.py rows` into it by hand, or remove them")
    if not _parses(text):  # Herdr's check stops at the first error: one there would hide a new one
        return "refused", f"{link} isn't valid TOML (Herdr runs on its defaults); Earmark writes once it's fixed"
    if not _parses(new):
        return "refused", "Earmark's block would break the file; nothing written"
    try:
        before = _check_lines()
    except NoAnswer as e:
        return "busy", f"Herdr's config check didn't answer ({e}); tried again later"
    if text and not os.path.exists(link + BACKUP_SUFFIX):
        store.write_atomic(link + BACKUP_SUFFIX, text, mode=_mode(path))
    if _read(path) != text:  # someone saved it while Herdr checked it
        return "busy", f"{link} changed while Earmark was writing; it tries again later"
    _write(path, new)
    try:
        added = _check_lines() - before
    except NoAnswer as e:  # unchecked: the old text goes back
        added = {f"Herdr's config check didn't answer ({e})"}
    if added:
        now = _read(path)
        try:  # the old text; or, after an edit made meanwhile, only Earmark's part goes back
            # (the old block without the lines its rewrite moved above it,
            # which a putback would otherwise repeat: a duplicate key)
            _write(path, text if now == new else compose(now, _own_part(split(text)[1] or ""), ours=split(new)[1] or ""))
        except ValueError:
            pass  # the markers were changed meanwhile: left for the user (check shows it)
        return "rolled back", "; ".join(sorted(added))
    problems = reload_all()
    return ("not reloaded", "; ".join(problems)) if problems else ("written", link)


def _stamp():
    """Herdr's config file as it is now (its real path, size and time)."""
    path = os.path.realpath(herdr.config_path())
    try:
        st = os.stat(path)
        return [path, st.st_size, st.st_mtime_ns]
    except OSError:
        return [path, None, None]


def fingerprint(cfg, palette):
    return hashlib.sha256(block(cfg, palette).encode()).hexdigest()[:16]


def keep_current(cfg, now=False):
    """With write_herdr_config on, rewrite the block when the settings or the
    theme's colours changed (`now`: whatever was written before, for the
    theme hook). herdrconf.json keeps the theme's palette (asked again only
    when its file changes), what was last written and the last result; a
    failure is tried again only once something changes ("busy" at the next
    hook). One process at a time; another finding it busy moves on."""
    if not cfg["sidebar"]["write_herdr_config"]:
        return "off", "write_herdr_config is off in Earmark's [sidebar]"
    if cfg.get("_broken"):
        return "refused", f"Earmark's config.toml has a problem ({cfg['_broken']})"
    with store.try_lock("herdrconf") as mine_now:
        if not mine_now:
            return "busy", "another Earmark process is writing it"
        state = store.load_json("herdrconf.json")
        old = dict(state)
        stamp = theme_stamp()
        if state.get("stamp") != stamp or not isinstance(state.get("palette"), dict):
            state["stamp"], state["palette"] = stamp, theme_palette() if stamp else {}
        want = fingerprint(cfg, state["palette"])
        # Done, or failed, for these settings and colours, and Herdr's file
        # untouched since: nothing to do (a block removed by hand, or a file
        # the user fixed, is tried again; an unchanged block costs no check).
        if not now and want in (state.get("written"), state.get("failed")) and state.get("file") == _stamp():
            if state != old:  # the palette, if the theme changed
                store.save_json("herdrconf.json", state)
            return None
        try:
            status, detail = apply(cfg, state["palette"])
        except OSError as e:  # can't write there (a read-only target): failed, not tried every hook
            status, detail = "refused", f"can't write Herdr's config.toml: {e}"
        state["file"] = _stamp()
        if status in ("written", "unchanged", "not reloaded"):
            state["written"] = want
            state.pop("failed", None)
        elif status != "busy":
            state["failed"] = want
            print(f"earmark: Herdr's config.toml: {status}: {detail}", file=sys.stderr)
        state["last"] = {"status": status, "detail": detail, "at": int(time.time())}
        store.save_json("herdrconf.json", state)
        return status, detail


# ---------------------------------------------------------- the theme hook

def theme_hook_path():
    return os.path.join(os.path.expanduser("~/.config/omarchy/hooks/theme-set.d"), HOOK_NAME)


def install_theme_hook():
    """A script Omarchy runs after each theme switch: Earmark rewrites its
    rows for the new colours at once (rather than at its next hook). It
    goes through Earmark's launcher, so it survives Herdr updating Earmark
    and does nothing once Earmark is gone. None without Omarchy."""
    from . import launcher
    if not os.path.isdir(os.path.expanduser("~/.config/omarchy")):
        return None
    path = theme_hook_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    script = ("#!/bin/bash\n"
              "# Earmark: recolour its rows in Herdr's sidebar for the new theme.\n"
              f"exec {shlex.quote(launcher.ensure())} rows --apply >/dev/null 2>&1\n")
    store.write_atomic(path, script, mode=0o755)
    return path
