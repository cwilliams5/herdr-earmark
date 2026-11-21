"""Earmark's own files, in the plugin state dir Herdr gives it (CLAUDE.md, rule 4).

index.json    what each live pane runs, refreshed on every hook; needed
              because Herdr's close events carry only ids (CLAUDE.md,
              "What close events carry").
archive.json  the closed sessions, filed by Herdr session and workspace.

Several hooks can run at once (a tab switch fires three), so every
read-modify-write happens under one lock, and files are replaced atomically:
written to a temp file in the same folder (mode 0600), flushed to disk, then
renamed over the old one.
"""
import contextlib
import fcntl
import json
import os
import tempfile
import time

INDEX_VERSION = 1
ARCHIVE_VERSION = 1

# What an archive entry or a closed-workspace record must have; anything else
# (hand-edited, or from a future version) is skipped rather than breaking
# every hook.
ENTRY_KEYS = ("herdr_session", "workspace_label", "agent", "session_id")
WORKSPACE_KEYS = ("herdr_session", "label", "tabs")


def state_dir():
    path = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
        "~/.local/state/herdr/plugins/io.github.cwilliams5.earmark")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


@contextlib.contextmanager
def locked():
    fd = os.open(os.path.join(state_dir(), ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _load(name, empty):
    path = os.path.join(state_dir(), name)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else empty
    except FileNotFoundError:
        return empty
    except (ValueError, UnicodeDecodeError):
        # A damaged file: keep it aside (never over an earlier one) rather
        # than lose it silently, and start again.
        aside = f"{path}.damaged-{time.strftime('%Y%m%d-%H%M%S')}"
        n = 1
        while os.path.exists(aside if n == 1 else f"{aside}-{n}"):
            n += 1
        os.replace(path, aside if n == 1 else f"{aside}-{n}")
        return empty


def _save(name, data):
    directory = state_dir()
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(directory, name))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def load_index():
    data = _load("index.json", {"version": INDEX_VERSION, "sessions": {}})
    if not isinstance(data.get("sessions"), dict):
        data["sessions"] = {}
    data["sessions"] = {k: v for k, v in data["sessions"].items()
                        if isinstance(v, dict) and isinstance(v.get("panes", {}), dict)}
    return data


def save_index(data):
    _save("index.json", data)


def _valid(record, keys):
    return isinstance(record, dict) and all(k in record for k in keys)


def load_archive():
    data = _load("archive.json", {"version": ARCHIVE_VERSION, "entries": {}})
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    data["entries"] = {k: v for k, v in entries.items() if _valid(v, ENTRY_KEYS)}
    workspaces = data.get("workspaces") if isinstance(data.get("workspaces"), dict) else {}
    data["workspaces"] = {k: v for k, v in workspaces.items()
                          if _valid(v, WORKSPACE_KEYS) and isinstance(v["tabs"], list)}
    return data


def save_archive(data):
    _save("archive.json", data)


def debug_log(record):
    """Append to events.jsonl when debug_log is on in the config. It holds
    raw event payloads, so only the user can read it."""
    fd = os.open(os.path.join(state_dir(), "events.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
