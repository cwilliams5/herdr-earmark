"""The archive logic: notes on live panes, and what happens when one closes.

Herdr's close events say what closed but not what was in it (CLAUDE.md,
"What close events carry"), so every hook refreshes Earmark's notes on each
live pane from `pane list`, and closes are found by comparing those notes
with what Herdr reports now: a noted pane that's gone was closed (with its
tab or workspace), and a noted pane whose agent left was exited.
"""
import os
import sys
import time

from . import agents, config, herdr, store

# After a Herdr server starts, each restored agent pane reports "released"
# while its resume is deferred (CLAUDE.md, "Restarts"). Within this many
# seconds of the startup hook, a release of a pane that existed at boot is
# that, not a user's /exit.
BOOT_GRACE = 60

# How long a newly detected agent may take to report its session id.
SESSION_WAIT = 8.0


def now():
    return time.time()


# ------------------------------------------------------------------ hooks

def handle_event(event, payload, env=None):
    """Entry point for every hook (and the startup hook, event "startup")."""
    env = os.environ if env is None else env
    cfg = config.load()
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    if cfg["debug_log"]:
        store.debug_log({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event,
                         "data": data, "session": herdr.session_name(env)})

    if event == "pane.agent_detected" and not data.get("released") and data.get("pane_id"):
        _wait_for_session(data["pane_id"])

    session = herdr.session_name(env)
    with store.locked():
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError:
            return  # Herdr is going away or busy; the next hook catches up
        index, archive = store.load_index(), store.load_archive()
        changed = apply(index, archive, session, snap, event, data, now())
        if event == "startup":
            changed |= prune(archive, cfg, now())
        reports = pending_reports(index, archive, session, snap) if cfg["report_count"] else []
        store.save_index(index)
        if changed:
            store.save_archive(archive)
    send_reports(reports)


def _wait_for_session(pane_id):
    deadline = now() + SESSION_WAIT
    while now() < deadline:
        try:
            p = herdr.pane(pane_id)
        except herdr.HerdrError:
            return
        if (p.get("agent_session") or {}).get("value") or not p.get("agent"):
            return
        time.sleep(0.4)


def apply(index, archive, session, snap, event, data, t):
    """Bring the notes for one Herdr session up to date with a snapshot, and
    archive what closed or exited. Returns True if the archive changed."""
    s = index.setdefault("sessions", {}).setdefault(
        session, {"panes": {}, "workspaces": {}, "boot": 0, "boot_panes": [], "reported": {}})
    entries = archive.setdefault("entries", {})
    changed = False

    if event == "startup":
        s["boot"], s["boot_panes"] = t, sorted(s["panes"])
        s["reported"] = {}  # sidebar tokens don't survive a restart: send them all again

    ws_labels = {wid: w.get("label") or "" for wid, w in snap["workspaces"].items()}

    # Renamed workspaces take their archive with them.
    for wid, old in s.get("workspaces", {}).items():
        new = ws_labels.get(wid)
        if new and old and new != old:
            for e in entries.values():
                if e["herdr_session"] == session and e["workspace_id"] == wid and e["workspace_label"] == old:
                    e["workspace_label"] = new
                    changed = True
    s["workspaces"] = ws_labels

    live = set()
    for pid, p in snap["panes"].items():
        ref = p.get("agent_session") or {}
        note = s["panes"].get(pid)
        if ref.get("value"):
            agent = ref.get("agent") or p.get("agent") or "unknown"
            live.add(f"{agent}:{ref['value']}")
            if note and note["session_id"] != ref["value"]:
                # A different session in the same pane (/clear, /resume): the old one closed.
                changed |= archive_note(entries, session, note, t, "replaced")
                note = None
            s["panes"][pid] = {
                "pane_id": pid,
                "tab_id": p.get("tab_id"),
                "workspace_id": p.get("workspace_id"),
                "workspace_label": ws_labels.get(p.get("workspace_id"), (note or {}).get("workspace_label", "")),
                "tab_label": (snap["tabs"].get(p.get("tab_id")) or {}).get("label") or "",
                "tab_number": (snap["tabs"].get(p.get("tab_id")) or {}).get("number"),
                "pane_label": p.get("label") or "",
                "agent": agent,
                "session_id": ref["value"],
                "source": ref.get("source"),
                "cwd": p.get("foreground_cwd") or p.get("cwd"),
                "title": agents.clean_title(p.get("terminal_title"), agent) or (note or {}).get("title", ""),
                "seen": t,
            }
        elif note:
            # The pane is alive but its agent is gone. A release right after a
            # restart is a deferred resume; keep the note for when it comes back.
            released = (event == "pane.agent_detected" and data.get("released")
                        and data.get("pane_id") == pid)
            if released and not boot_protected(s, pid, t):
                changed |= archive_note(entries, session, s["panes"].pop(pid), t, "exited")

    # Noted panes Herdr no longer has were closed, alone or with their tab or workspace.
    for pid in [pid for pid in s["panes"] if pid not in snap["panes"]]:
        changed |= archive_note(entries, session, s["panes"].pop(pid), t, "closed")

    # A session that's live again (reopened, resumed by hand, restored) leaves the archive.
    for key in [k for k, e in entries.items() if f"{e['agent']}:{e['session_id']}" in live]:
        del entries[key]
        changed = True
    return changed


def boot_protected(s, pid, t):
    return pid in s.get("boot_panes", []) and t - s.get("boot", 0) < BOOT_GRACE


def archive_note(entries, session, note, t, reason):
    """File a closed pane's session. Sessions with nothing to resume are skipped."""
    facts = agents.session_facts(note["agent"], note["session_id"])
    if facts["known"] and not (facts["exists"] and facts["has_content"]):
        return False
    key = f"{note['agent']}:{note['session_id']}"
    entries[key] = {
        "herdr_session": session,
        "workspace_id": note.get("workspace_id"),
        "workspace_label": note.get("workspace_label") or "",
        "tab_label": note.get("tab_label") or "",
        "tab_number": note.get("tab_number"),
        "pane_label": note.get("pane_label") or "",
        "agent": note["agent"],
        "session_id": note["session_id"],
        "source": note.get("source"),
        "cwd": note.get("cwd"),
        "title": facts["title"] or note.get("title") or "",
        "closed_at": t,
        "last_active": facts["last_active"] or note.get("seen") or t,
        "reason": reason,
    }
    return True


# ------------------------------------------------------------------ names

def is_default_tab_label(label, number=None):
    """Herdr names a new tab "Initial" (a workspace's first) or its number;
    anything else is a name the user gave it."""
    label = (label or "").strip()
    return not label or label == "Initial" or label.isdigit() or (number is not None and label == str(number))


def custom_name(entry):
    """The name the user gave the session's pane or tab, or ""."""
    if entry.get("pane_label"):
        return entry["pane_label"]
    label = entry.get("tab_label") or ""
    return "" if is_default_tab_label(label, entry.get("tab_number")) else label


def names(entry, first="tab"):
    """(primary, secondary) names to show: the user's tab name and the agent's
    title, in the order config.title_first asks for; secondary is "" when
    there's only one, or they're the same."""
    mine, agents_title = custom_name(entry), entry.get("title") or ""
    pair = (mine, agents_title) if first != "agent" else (agents_title, mine)
    primary, secondary = pair[0] or pair[1], (pair[1] if pair[0] else "")
    if secondary.strip().lower() == primary.strip().lower():
        secondary = ""
    return primary or "(untitled session)", secondary


# ---------------------------------------------------------------- archive

def prune(archive, cfg, t):
    """Drop sessions past keep_days and sessions whose agent data is gone.
    Refreshes titles and last activity from the agent's files on the way."""
    changed = False
    entries = archive.setdefault("entries", {})
    for key in list(entries):
        e = entries[key]
        facts = agents.session_facts(e["agent"], e["session_id"])
        if facts["known"]:
            if not (facts["exists"] and facts["has_content"]):
                del entries[key]
                changed = True
                continue
            for field in ("last_active", "title"):
                if facts[field] and facts[field] != e.get(field):
                    e[field] = facts[field]
                    changed = True
        if cfg["keep_days"] and t - (e.get("last_active") or e.get("closed_at") or t) > cfg["keep_days"] * 86400:
            del entries[key]
            changed = True
    return changed


def listing(archive, session, workspace_label=None):
    """Archive entries for one Herdr session (and workspace), newest first."""
    rows = [dict(e, key=k) for k, e in archive.get("entries", {}).items()
            if e["herdr_session"] == session
            and (workspace_label is None or e["workspace_label"] == workspace_label)]
    return sorted(rows, key=lambda e: e.get("last_active") or 0, reverse=True)


def forget(key):
    with store.locked():
        archive = store.load_archive()
        if archive.get("entries", {}).pop(key, None) is not None:
            store.save_archive(archive)


def reopen(entry, ctx, cfg):
    """Open a new tab running the session's resume command. Returns the error
    message to show, or None."""
    argv = agents.resume_argv(entry["agent"], entry["session_id"], cfg["resume"])
    if not argv:
        return f"Earmark doesn't know how to reopen {entry['agent']} sessions (add it under [resume] in config.toml)."
    try:
        snap = herdr.snapshot()
    except herdr.HerdrError as e:
        return str(e)
    # Its own workspace if it still exists (by id, then by name), else this one.
    target = None
    w = snap["workspaces"].get(entry.get("workspace_id"))
    if w and (w.get("label") or "") == entry["workspace_label"]:
        target = entry["workspace_id"]
    if not target:
        target = next((wid for wid, w in snap["workspaces"].items()
                       if (w.get("label") or "") == entry["workspace_label"]), None)
    target = target or ctx.get("workspace_id")
    try:
        # The tab's own name comes back; a tab that only had Herdr's default
        # label gets a default label again, not the agent's title.
        pane_id = herdr.new_tab(target, entry.get("cwd"), custom_name(entry))
        herdr.run_in_pane(pane_id, argv)
    except herdr.HerdrError as e:
        return str(e)
    forget(entry["key"])
    return None


# ---------------------------------------------------------------- sidebar

def count_text(n):
    return f"{n} archived" if n else ""


def pending_reports(index, archive, session, snap):
    """The $earmark sidebar tokens that changed since they were last sent."""
    s = index["sessions"][session]
    sent = s.setdefault("reported", {})
    out = []
    for wid, w in snap["workspaces"].items():
        text = count_text(len(listing(archive, session, w.get("label") or "")))
        if sent.get(wid) != text:
            out.append((wid, text))
            sent[wid] = text
    for wid in [wid for wid in sent if wid not in snap["workspaces"]]:
        del sent[wid]
    return out


def update_counts(session):
    """Resend any $earmark tokens the archive's current state changes."""
    cfg = config.load()
    if not cfg["report_count"]:
        return
    with store.locked():
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError:
            return
        index, archive = store.load_index(), store.load_archive()
        index.setdefault("sessions", {}).setdefault(
            session, {"panes": {}, "workspaces": {}, "boot": 0, "boot_panes": [], "reported": {}})
        reports = pending_reports(index, archive, session, snap)
        store.save_index(index)
    send_reports(reports)


def send_reports(reports):
    for wid, text in reports:
        try:
            herdr.report_count(wid, text)
        except herdr.HerdrError as e:
            print(f"earmark: sidebar count for {wid}: {e}", file=sys.stderr)  # shows in `herdr plugin log`
