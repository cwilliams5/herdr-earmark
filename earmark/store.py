"""Earmark's own files, in the plugin state dir Herdr gives it (CLAUDE.md, rule 4).

index.json    what each live pane runs, refreshed on every hook; needed
              because Herdr's close events carry only ids (CLAUDE.md,
              "What close events carry").
archive.json  the closed sessions, filed by Herdr session and workspace.

Several hooks can run at once (a tab switch fires three), so every
read-modify-write happens under one lock, and files are replaced atomically.
"""
import contextlib
import fcntl
import json
import os
import tempfile

INDEX_VERSION = 1
ARCHIVE_VERSION = 1


def state_dir():
    path = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
        "~/.local/state/herdr/plugins/io.github.cwilliams5.earmark")
    os.makedirs(path, exist_ok=True)
    return path


@contextlib.contextmanager
def locked():
    with open(os.path.join(state_dir(), ".lock"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _load(name, empty):
    try:
        with open(os.path.join(state_dir(), name), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else empty
    except FileNotFoundError:
        return empty
    except ValueError:
        # A damaged file: keep it aside rather than lose it silently.
        path = os.path.join(state_dir(), name)
        os.replace(path, path + ".damaged")
        return empty


def _save(name, data):
    directory = state_dir()
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, os.path.join(directory, name))


def load_index():
    return _load("index.json", {"version": INDEX_VERSION, "sessions": {}})


def save_index(data):
    _save("index.json", data)


def load_archive():
    return _load("archive.json", {"version": ARCHIVE_VERSION, "entries": {}})


def save_archive(data):
    _save("archive.json", data)


def debug_log(record):
    """Append to events.jsonl when debug_log is on in the config."""
    with open(os.path.join(state_dir(), "events.jsonl"), "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
