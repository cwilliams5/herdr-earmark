"""config.toml in the plugin's config dir (`herdr plugin config-dir
io.github.cwilliams5.earmark`). Every key is optional:

    keep_days = 30         forget a session this many days after its last
                           activity; 0 keeps entries until the agent's own
                           files are gone. Claude Code deletes transcripts
                           after cleanupPeriodDays (default 30), and Earmark
                           can't keep a session the agent has deleted.
    report_count = true    publish "N archived" as the $earmark sidebar
                           token; it only shows if you add $earmark to
                           ui.sidebar.spaces.rows in Herdr's config.
    debug_log = false      append every hook's event to events.jsonl in the
                           state dir.

    [resume]               reopen commands, per agent name as Herdr reports
    claude = ["claude", "--resume", "{id}"]      it; {id} is the session id
"""
import os
import tomllib

DEFAULTS = {"keep_days": 30, "report_count": True, "debug_log": False, "resume": {}}


def config_path():
    directory = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or os.path.expanduser(
        "~/.config/herdr/plugins/config/io.github.cwilliams5.earmark")
    return os.path.join(directory, "config.toml")


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return cfg
    except (OSError, tomllib.TOMLDecodeError):
        return cfg  # a broken file never breaks Herdr's hooks; `earmark.py check` reports it
    if isinstance(data.get("keep_days"), int) and data["keep_days"] >= 0:
        cfg["keep_days"] = data["keep_days"]
    for key in ("report_count", "debug_log"):
        if isinstance(data.get(key), bool):
            cfg[key] = data[key]
    resume = data.get("resume")
    if isinstance(resume, dict):
        cfg["resume"] = {k: v for k, v in resume.items()
                         if isinstance(v, list) and v and all(isinstance(x, str) for x in v)}
    return cfg
