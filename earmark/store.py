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
import hashlib
import json
import os
import re
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
    path = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.join(  # by hand: where Herdr keeps it
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
        "herdr", "plugins", "io.github.cwilliams5.earmark")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


@contextlib.contextmanager
def flock(path, timeout=None):
    """An exclusive lock on the file at `path` (created, mode 0600). With a
    `timeout`, TimeoutError after that many seconds of someone else holding
    it, rather than waiting for ever."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as f:
        if timeout is None:
            fcntl.flock(f, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"{path} is held by another process")
                    time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def locked():
    return flock(os.path.join(state_dir(), ".lock"))


def write_atomic(path, text, mode=0o600, sync=True):
    """Replace the file at `path` with `text` all at once: written to a temp
    file in the same folder, flushed (and synced to disk unless `sync` is
    False: caches only), given `mode`, then renamed over the old one."""
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            if sync:
                os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def segment(text):
    """A file name for a session, workspace or pane id: itself when plain,
    else a hash (ids come from Herdr and from the environment)."""
    return text if re.fullmatch(r"[A-Za-z0-9:_.-]{1,64}", text or "") and text not in (".", "..") else \
        hashlib.sha256((text or "").encode()).hexdigest()[:24]


@contextlib.contextmanager
def try_lock(name):
    """A lock only one process holds at a time; yields False (at once) if
    another process has it."""
    fd = os.open(os.path.join(state_dir(), f".{name}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def screens_dir():
    """Where suspended tabs' last screens are kept (only the user can read
    them: they're copies of what the terminal showed)."""
    path = os.path.join(state_dir(), "screens")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def load_json(name):
    return _load(name, {})


def save_json(name, data):
    _save(name, data)


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
        try:
            os.replace(path, aside if n == 1 else f"{aside}-{n}")
        except FileNotFoundError:
            pass  # another reader set it aside first
        return empty


def _save(name, data, sync=True):
    """Atomically replace a file; `sync` flushes it to disk first (left
    out only for caches, which a crash may lose: sidebar.json)."""
    write_atomic(os.path.join(state_dir(), name), json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                 sync=sync)


def session_state(index, session):
    """One Herdr session's part of index.json, created empty if new."""
    return index.setdefault("sessions", {}).setdefault(
        session, {"panes": {}, "workspaces": {}, "boot": 0, "boot_panes": []})


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


def load_sidebar():
    """sidebar.json: the tokens last sent to Herdr's sidebar, per Herdr
    session, so only changes are sent. A cache: lost, everything is sent
    again; kept out of index.json so a status change doesn't rewrite that."""
    data = _load("sidebar.json", {"sessions": {}})
    if not isinstance(data.get("sessions"), dict):
        data["sessions"] = {}
    return data


def save_sidebar(data):
    _save("sidebar.json", data, sync=False)


def debug_log(record):
    """Append to events.jsonl when debug_log is on in the config. It holds
    raw event payloads, so only the user can read it."""
    fd = os.open(os.path.join(state_dir(), "events.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
