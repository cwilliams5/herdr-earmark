"""Workspace notes (PLAN phase L): one Markdown note per Herdr workspace,
kept in Earmark's state folder (notes/<session>/<workspace>.md), so you (or
your Claude, through the /herdr-note skill) can leave yourself where a
project stands.

A note follows its workspace, never its id: Herdr reuses workspace ids (an
in-memory counter seeded after a restart with the highest surviving id + 1,
src/workspace.rs), so when a workspace closes its note moves into that
closed workspace's record in archive.json, and comes back when it's
restored; forgetting the record forgets the note. The file is removed only
after the archive holding the copy is saved (retire()).

Writes are atomic and flushed to disk (it's the user's own text), and a
write can name the version it was based on, so the skill never silently
overwrites an edit made in the popup meanwhile.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile

from . import store

LIMIT = 1_000_000  # characters: a note, not a file store


class Conflict(Exception):
    """The note changed since the version a write was based on."""


def notes_dir(session):
    path = os.path.join(store.state_dir(), "notes", store.segment(session))
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def note_path(session, workspace_id):
    return os.path.join(notes_dir(session), store.segment(workspace_id) + ".md")


def _locked(session):
    return store.flock(os.path.join(notes_dir(session), ".lock"))


def read(session, workspace_id):
    try:
        with open(note_path(session, workspace_id), encoding="utf-8", errors="replace") as f:
            return f.read(LIMIT + 1)[:LIMIT]
    except FileNotFoundError:
        return ""


def version(text):
    """What a write names to say which note it was based on."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _store(path, text):
    if not text.strip():
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        return
    store.write_atomic(path, text if text.endswith("\n") else text + "\n")


def write(session, workspace_id, text, expect=None, clear=False):
    """Replace the note. Empty removes it, only with `clear` (an empty write
    is more often a mistake than a wish). With `expect` (a version()),
    refuse with Conflict if the note isn't that version any more."""
    if len(text) > LIMIT:
        raise ValueError(f"a note holds at most {LIMIT} characters")
    if not text.strip() and not clear:
        raise ValueError("an empty note would remove it: write it with --clear to mean that")
    with _locked(session):
        if expect is not None and version(read(session, workspace_id)) != expect:
            raise Conflict("the note changed since it was read")
        _store(note_path(session, workspace_id), text)


def noted(session):
    """Workspace ids with a note (for the sidebar mark)."""
    out = set()
    try:
        names = os.listdir(notes_dir(session))
    except OSError:
        return out
    for name in names:
        if name.endswith(".md") and not name.startswith("."):
            try:
                if os.path.getsize(os.path.join(notes_dir(session), name)) > 0:
                    out.add(name[:-3])
            except OSError:
                pass
    return out


def retire(session, workspace_id, text):
    """Remove a closed workspace's note file, once its text is safe in the
    archive (and only if it's still that text)."""
    with _locked(session):
        if read(session, workspace_id) == text:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(note_path(session, workspace_id))


def put_back(session, workspace_id, text):
    """A restored workspace's note; added below a note already there (a
    restore into a live workspace of the same name)."""
    if not text.strip():
        return
    with _locked(session):
        now = read(session, workspace_id)
        if now.strip() and now.strip() != text.strip():
            text = now.rstrip("\n") + "\n\n---\n\n" + text
        _store(note_path(session, workspace_id), text)


# --------------------------------------------------------------------- CLI

def _args(argv):
    """`note <show|write|path> [--json] [--workspace W] [--session S]
    [--expect V]`, defaults from the pane's own Herdr variables."""
    opts = {"workspace": os.environ.get("HERDR_WORKSPACE_ID") or "",
            "session": os.environ.get("HERDR_SESSION") or "default", "expect": None, "json": False, "clear": False}
    words = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--workspace", "--session", "--expect") and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        if a in ("--json", "--clear"):
            opts[a[2:]] = True
        else:
            words.append(a)
        i += 1
    return (words[0] if words else "show"), opts


STATES = {"blocked": "needs the user", "working": "working", "done": "finished, not read yet", "idle": "idle"}


def workspace_tabs(session, workspace_id, here=None):
    """This workspace's tabs, in their on-screen order, for the skill: each
    tab's name (None for one Herdr named itself) and its agents: what each
    is doing (Herdr's status, or "suspended" from Earmark's records, since a
    suspended tab is in no Herdr agent list), its title, and its recent
    requests, replies and tools' names (agents.recent_exchange: never a
    tool's output). Its transcript's path only where the user opted in
    ([notes] read_transcripts): transcripts hold what tools read. `here`:
    the asking pane's tab."""
    from . import agents, config, core, herdr
    read_transcripts = config.load()["notes"]["read_transcripts"]
    snap = herdr.snapshot()
    with store.locked():
        s = (store.load_index().get("sessions") or {}).get(session) or {}
    noted, suspended = s.get("panes") or {}, s.get("suspended") or {}
    out = []
    for tid, t in snap["tabs"].items():
        if t.get("workspace_id") != workspace_id:
            continue
        label = t.get("label")
        found = []
        for pid, p in snap["panes"].items():
            if p.get("tab_id") != tid:
                continue
            rec = suspended.get(pid) or {}
            agent = p.get("agent") or rec.get("agent")
            if not agent:
                continue  # a plain shell
            sid = (p.get("agent_session") or {}).get("value") or rec.get("session_id")
            note = noted.get(pid) or {}
            config_dir = note.get("config_dir") or rec.get("config_dir")
            if not sid:
                path = None
            elif agent == "claude":
                path = agents.claude_transcript(sid, config_dir)
            else:
                path = agents.session_facts(agent, sid, title=False).get("source")
            entry = {"pane": pid, "agent": agent, "session_id": sid,
                     "state": "suspended" if rec else STATES.get(p.get("agent_status"), "unknown"),
                     "title": agents.clean_title(p.get("terminal_title"), agent) or note.get("title") or rec.get("title") or ""}
            entry.update(agents.recent_exchange(agent, path))
            if read_transcripts and path:
                entry["transcript"] = path
            found.append(entry)
        out.append({"tab": None if core.is_default_tab_label(label, t.get("number")) else label,
                    "here": tid == here, "agents": found})
    return out


def _label(workspace_id):
    from . import herdr
    try:
        return (herdr.run("workspace", "get", workspace_id) or {}).get("workspace", {}).get("label") or ""
    except herdr.HerdrError:
        return ""


def cli(argv, stdin=None, out=None):
    """`earmark.py note ...` (for the /herdr-note skill and people)."""
    stdin = stdin if stdin is not None else sys.stdin
    out = out if out is not None else sys.stdout
    what, o = _args(argv)
    if not o["workspace"]:
        print("earmark note: no workspace (run it in a Herdr pane, or give --workspace)", file=sys.stderr)
        return 2
    session, wid = o["session"], o["workspace"]
    if what == "path":
        print(note_path(session, wid), file=out)
        return 0
    if what == "show":
        text = read(session, wid)
        if o["json"]:
            from . import herdr
            try:
                tabs = workspace_tabs(session, wid, here=os.environ.get("HERDR_TAB_ID"))
            except herdr.HerdrError:
                tabs = None  # Herdr didn't answer: the note still reads
            json.dump({"session": session, "workspace": wid, "label": _label(wid), "path": note_path(session, wid),
                       "version": version(text), "text": text, "tabs": tabs}, out, ensure_ascii=False)
            out.write("\n")
        else:
            out.write(text)
        return 0
    if what == "write":
        try:
            write(session, wid, "" if o["clear"] else stdin.read(), expect=o["expect"], clear=o["clear"])
        except Conflict:
            print("earmark note: the note changed since you read it (edited in the popup?); read it again",
                  file=sys.stderr)
            return 3
        except ValueError as e:
            print(f"earmark note: {e}", file=sys.stderr)
            return 2
        return 0
    print("usage: earmark note [show [--json] | write [--expect VERSION] [--clear] | path] "
          "[--workspace W] [--session S]", file=sys.stderr)
    return 2
