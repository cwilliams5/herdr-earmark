"""Earmark's values in Herdr's sidebar (PLAN phase M): numbers on each
workspace's row, and model · effort · context on each agent's second line.

What Earmark sends is plain text in metadata tokens (Herdr strips control
characters); colours live only in Herdr's config.toml, per token, which
`earmark.py rows` prints (and, opted in, Earmark keeps: herdrconf.py).

Earmark fits its own text to the row, because Herdr's fitting is wrong for
it (src/ui/sidebar.rs `resolved_token_spans` in Herdr 0.9.5): every text
token, the workspace's name included, is flexible with a 1-column minimum;
when those minimums overflow, Herdr drops all of them and adds them back
from the right, so a long row loses the workspace's name first; when they
fit, spare width is shared a column at a time, so the longest token is cut
("Opus 5…"). Herdr never tells a plugin how wide the sidebar is (the
server's layout is its own virtual screen), so the width is worked out the
way Herdr's client does (sidebar_width()).
"""
import json
import os

from . import config, herdr
from .text import cols as text_cols

PREFIX = "earmark_"
COUNT_TOKENS = tuple(PREFIX + item for item in config.COUNT_ITEMS)
CONTEXT_TOKENS = tuple(f"{PREFIX}ctx_{n}" for n in range(1, config.MAX_LEVELS + 2))
AGENT_TOKENS = (PREFIX + "model", PREFIX + "effort") + CONTEXT_TOKENS
LEGACY_TOKEN = "earmark"  # 1.0-1.1's "N archived"; cleared once per workspace
NOTE_MARK = "✎"

# Herdr's client: ui.sidebar_width, clamped to [sidebar_min_width,
# sidebar_max_width] (defaults 26, 18, 36), unless the user dragged it: the
# client keeps that in its own preferences file (src/client/shell/state.rs,
# preferences.rs).
DEFAULT_WIDTH, DEFAULT_MIN, DEFAULT_MAX = 26, 18, 36
# The sidebar's own divider column, and a scrollbar column assumed always
# there: Earmark can't see whether a list overflows the client's screen, and
# a row one column short beats Herdr dropping a workspace's name.
DIVIDER, SCROLLBAR = 1, 1
SEPARATOR = " · "  # Herdr's, between two text tokens (src/ui/sidebar/tokens.rs)

EFFORT_SHORT = {"minimal": "mn", "low": "l", "medium": "m", "high": "h", "xhigh": "xh", "max": "mx",
                "ultra": "u", "none": "0"}


def text_width(text):
    """Terminal columns of text (text.cols: wide characters 2, marks and
    joiners 0)."""
    return text_cols(text)


def clean(text, limit=40):
    """A value fit for a token: printable, one line, at most `limit` chars."""
    text = "".join(ch for ch in str(text) if ch.isprintable() and ch not in "\r\n\t").strip()
    return text[:limit]


# ------------------------------------------------------------------ width

def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def client_preferences(session):
    """The Herdr client's preferences file for a session: in Herdr's state
    folder, named after an FNV-1a hash of the session's client socket path
    (src/client/shell/preferences.rs path_for_local_endpoint; the socket is
    in the session's folder, src/session.rs data_dir_for). A dragged sidebar
    width is kept there, never in session.json (always null in 0.9.5)."""
    herdr_dir = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "herdr")
    folder = herdr_dir if session == "default" else os.path.join(herdr_dir, "sessions", session)
    h = 0xcbf29ce484222325
    for byte in os.path.join(folder, "herdr-client.sock").encode("utf-8", "surrogateescape"):
        h = ((h ^ byte) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    state = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "herdr")
    return os.path.join(state, "client-shell", f"local-{h:016x}.json")


def sidebar_width(session="default"):
    """The sidebar's width in columns, as Herdr's client works it out."""
    low = _int(herdr.setting("ui", "sidebar_min_width")) or DEFAULT_MIN
    high = _int(herdr.setting("ui", "sidebar_max_width")) or DEFAULT_MAX
    if low > high:
        low, high = DEFAULT_MIN, DEFAULT_MAX
    dragged = None
    try:
        with open(client_preferences(session), encoding="utf-8") as f:
            dragged = _int(json.load(f).get("sidebar_width"))
    except (OSError, ValueError, AttributeError):
        pass
    width = dragged or _int(herdr.setting("ui", "sidebar_width")) or DEFAULT_WIDTH
    return max(low, min(high, width))


def space_line_width(width, line):
    """Columns for a workspace's line `line` (0 = the name's): Herdr indents
    the first line by 1 and later ones by 3, and keeps 2 at the right
    (src/client/shell/sidebar.rs render_workspace_rows)."""
    return width - DIVIDER - SCROLLBAR - 2 - (1 if line == 0 else 3)


def agent_line_width(width, line):
    """Columns for an agent's line `line`: indented 1, then 3
    (src/client/shell/agent_sidebar.rs)."""
    return width - DIVIDER - SCROLLBAR - (1 if line == 0 else 3)


# ------------------------------------------------------- workspace counts

def count_values(snap, workspace_id, suspended, archived, has_note):
    """{item: count} for one workspace: agents by Herdr's status (done
    and idle both count as done), suspended tabs and archived sessions from
    Earmark's own files, and 1 for a note."""
    out = dict.fromkeys(config.COUNT_ITEMS, 0)
    for p in snap["panes"].values():
        if p.get("workspace_id") != workspace_id or not p.get("agent"):
            continue
        status = p.get("agent_status")
        if status == "blocked":
            out["blocked"] += 1
        elif status == "working":
            out["working"] += 1
        elif status in ("done", "idle"):
            out["done"] += 1
    out["suspended"] = suspended
    out["archived"] = archived
    out["note"] = 1 if has_note else 0
    return out


def fit_counts(label, values, show, line, width):
    """The (item, text) pairs to show for one workspace, in `show` order,
    zeros left out, and dropped from the right until they fit: after the
    name ("same": each one costs a separator, and the name is never given
    up) or on a line of their own ("new")."""
    items = [(i, NOTE_MARK if i == "note" else str(values[i])) for i in show if values.get(i)]
    if line == "same":
        budget = space_line_width(width, 0) - 2 - text_width(label)  # the state icon and its space
    else:
        budget = space_line_width(width, 1)
    out, used = [], 0
    for item, text in items:
        need = text_width(text) + (len(SEPARATOR) if line == "same" or out else 0)
        if used + need > budget:
            break
        out.append((item, text))
        used += need
    return out


def count_tokens(fitted):
    """Every count token, set or cleared (None): a token not set this time
    must not keep last time's value."""
    shown = dict(fitted)
    return {PREFIX + item: shown.get(item) for item in config.COUNT_ITEMS}


# --------------------------------------------------------------- agent rows

def short_effort(effort):
    return EFFORT_SHORT.get(effort.lower(), effort[:2]) if effort else effort


def short_model(model):
    """"Opus 5.5" -> "O5.5", "GPT-6.2-Sol" -> "G6.2S", "grok-4.7" -> "g4.7":
    the first letter, the version, then the first letter of each word after
    it. A name without a version keeps its first 4 characters."""
    if not model:
        return model
    base = model.split("(")[0].strip() or model
    words = [w for w in base.replace("-", " ").replace("_", " ").split() if w]
    if len(words) > 1 and words[0].lower() == "claude":  # "Claude Opus 5.5": the family leads
        words = words[1:]
    version = next((i for i, w in enumerate(words) if any(c.isdigit() for c in w)), None)
    if version is None:
        return words[0][:4] if words else model[:4]
    if version == 0:
        return words[0] + "".join(w[0] for w in words[1:])
    return words[0][0] + words[version] + "".join(w[0] for w in words[version + 1:])


def context_band(percent, levels):
    """1-based: 1 below the first threshold, n+1 at or above the last."""
    return 1 + sum(1 for t in levels if percent >= t)


def fit_agent(model, effort, percent, show, width):
    """(model, effort, context text) for an agent's second line, shortened
    in stages until it fits: full, short effort, short model, no effort, no
    model. The context number always stays."""
    ctx = f"{percent}%" if percent is not None and "context" in show else None
    model = model if "model" in show else None
    effort = effort if "effort" in show else None
    budget = agent_line_width(width, 1)
    stages = [(model, effort), (model, short_effort(effort)), (short_model(model), short_effort(effort)),
              (short_model(model), None), (None, None)]
    for m, e in stages:
        parts = [p for p in (m, e, ctx) if p]
        if text_width(SEPARATOR.join(parts)) <= budget:
            return m or None, e or None, ctx
    return None, None, ctx


def agent_tokens(model, effort, percent, cfg_sidebar, width):
    """Every agent-row token, set or cleared."""
    m, e, ctx = fit_agent(clean(model) if model else None, clean(effort, 12) if effort else None,
                          percent, cfg_sidebar["agent_row"], width)
    out = {PREFIX + "model": m, PREFIX + "effort": e}
    band = context_band(percent, cfg_sidebar["context_levels"]) if ctx else None
    for n, token in enumerate(CONTEXT_TOKENS, 1):
        out[token] = ctx if n == band else None
    return out


def percent_of(used, window):
    """Whole percent of a context window, or None."""
    try:
        used, window = float(used), float(window)
    except (TypeError, ValueError):
        return None
    if not (0 < window < float("inf") and 0 <= used < float("inf")):  # NaN fails every comparison
        return None
    return int(round(used * 100.0 / window))


# ---------------------------------------------------------------- sending

def changed(tokens, sent):
    """The tokens to send: all of them when any differs from what was last
    sent, or isn't known to have been (Herdr keeps only the newest report
    per source and target by its sequence number, so a part sent alone could
    be overtaken by an older-looking one and lost); none when nothing
    changed. Nothing sent yet (`sent` None: a new row, or after a restart):
    only those with a value, as there's nothing to clear."""
    if not isinstance(sent, dict):
        return {k: v for k, v in tokens.items() if v}
    return dict(tokens) if any(k not in sent or sent[k] != v for k, v in tokens.items()) else {}


def report(kind, target, tokens, seq):
    """Set and clear tokens on a workspace or pane (`kind`); ids go before
    the options (Herdr 0.9.5 rejects them last). A value is one argument
    ("name=value"), so nothing in it can pass for an option."""
    from . import PLUGIN_ID
    args = [kind, "report-metadata", target, "--source", PLUGIN_ID, "--seq", str(seq)]
    for name, value in sorted(tokens.items()):
        args += ["--token", f"{name}={value}"] if value else ["--clear-token", name]
    herdr.run(*args)
