"""The archive logic: notes on live panes, and what happens when one closes.

Herdr's close events say what closed but not what was in it (CLAUDE.md,
"What close events carry"), so every hook refreshes Earmark's notes on each
live pane from `pane list`, and closes are found by comparing those notes
with what Herdr reports now: a noted pane that's gone was closed (with its
tab or workspace), and a noted pane whose agent left was exited.
"""
import json
import os
import sys
import time

from . import agents, config, herdr, sidebar, store

# After a Herdr server starts, each restored agent pane reports "released"
# while its resume is deferred (CLAUDE.md, "Restarts"). Within this many
# seconds of the startup hook, a release of a pane that existed at boot is
# that, not a user's /exit.
BOOT_GRACE = 60

# How long a newly detected agent may take to report its session id.
SESSION_WAIT = 8.0

# Notes for a Herdr session (a named one that was deleted, say) nothing has
# been heard from in this many days are dropped.
FORGET_SESSION_DAYS = 30

# What a pane's note keeps from one snapshot to the next while it runs the
# same session: when Earmark first saw it, when it was last focused or
# changed status (Suspend's idle clock), the Claude folder its process uses,
# and a failed suspend's back-off.
CARRY = ("since", "focused_at", "status", "status_at", "config_dir", "config_dir_tried", "backoff_until")
CONFIG_DIR_RETRY = 600  # a Claude folder lookup that failed is tried again after this


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
    from . import suspend
    scfg = cfg["suspend"]
    worker_args = wake = None
    with store.locked():
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError:
            return  # Herdr is going away or busy; the next hook catches up
        index, archive = store.load_index(), store.load_archive()
        before = json.dumps(index, sort_keys=True)
        try:
            note_config_dirs(snap, index.get("sessions", {}).get(session) or {})
        except Exception as e:  # never at the cost of archiving
            print(f"earmark: CLAUDE_CONFIG_DIR lookup: {e!r}", file=sys.stderr)
        # Hooks are started by the Herdr server itself (no shell), so the
        # parent process is the server: a new one means Herdr restarted.
        t = now()
        changed = apply(index, archive, session, snap, event, data, t, server_pid=os.getppid(),
                        idle_clock=scfg["when"] in config.AUTO_MODES)
        if event == "startup" and not cfg.get("_broken"):  # a broken config.toml never prunes
            changed |= prune(archive, cfg, t)
        try:
            cache = store.load_sidebar()
            cache_before = json.dumps(cache, sort_keys=True)
            reports = pending_reports(index, archive, session, snap, cfg, cache)
            if json.dumps(cache, sort_keys=True) != cache_before:
                store.save_sidebar(cache)
        except Exception as e:  # the sidebar never at the cost of archiving
            print(f"earmark: sidebar counts: {e!r}", file=sys.stderr)
            reports = []
        s = index["sessions"][session]
        # Suspend: placeholders back after a restart; an automatic check at
        # most once a minute; resume on view (earmark/suspend.py).
        try:
            rearm = s.pop("rearm", False)
            from . import procs
            if scfg["when"] == "memory":  # a worker only when memory is low (it'd do nothing else)
                available = procs.available_percent()
                can_act = available is not None and available < scfg["memory_below"]
            else:
                can_act = True
            # Herdr quiet for a long time (a laptop asleep, a night away): the
            # first events after it are the user coming back, not idleness.
            if scfg["when"] in config.AUTO_MODES:  # nothing else reads it: no write for it otherwise
                if s.get("last_event") and t - s["last_event"] > suspend.AWAY_GAP:
                    s["quiet_until"] = t + suspend.RETURN_GRACE
                    s["away"] = [s["last_event"], t]
                if t - s.get("last_event", 0) > 60:
                    s["last_event"] = t
            if cfg.get("_broken") != s.get("config_problem"):  # said once per problem, where the worker logs
                if cfg.get("_broken"):
                    suspend.log(f"{session}: config.toml has a problem ({cfg['_broken']}); no automatic suspends "
                                "or pruning until it's fixed")
                s["config_problem"] = cfg.get("_broken")
            checks_run = scfg["when"] in config.AUTO_MODES and can_act and not cfg.get("_broken")
            due = checks_run and t - s.get("suspend_checked", 0) >= suspend.CHECK_EVERY
            if due:
                s["suspend_checked"] = t
            if rearm or due:
                worker_args = ["--rearm"] if rearm else []
            elif not checks_run and t - s.get("rearm_checked", 0) >= suspend.CHECK_EVERY and any(
                    suspend.waiting(r) for r in (s.get("suspended") or {}).values()):
                # Automatic checks put missing placeholders back; while none
                # run (manual or off, memory that's fine, a broken
                # config.toml), this pass does, at most once a minute.
                s["rearm_checked"] = t
                worker_args = ["--rearm-pass"]
            if event == "pane.focused" and scfg["resume_on"] == "view":
                rec = s.get("suspended", {}).get(data.get("pane_id"))
                wake = data.get("pane_id") if rec and rec.get("state") == "suspended" else None
        except Exception as e:
            print(f"earmark: suspend scheduling: {e!r}", file=sys.stderr)
        # The archive first: if the index write then fails, the next hook files
        # the same sessions again (the same keys); the other way round, a
        # session dropped from the index would be in neither file.
        if changed:
            store.save_archive(archive)
            retire_notes(archive, session, t)
        if json.dumps(index, sort_keys=True) != before:
            store.save_index(index)
    # Suspend's work first: a resume on view shouldn't wait for the sidebar.
    try:
        if worker_args is not None and not suspend.spawn_worker(worker_args) and "--rearm" in worker_args:
            with store.locked():  # keep the restart's request for the next hook
                index = store.load_index()
                store.session_state(index, session)["rearm"] = True
                store.save_index(index)
        if wake:
            suspend.wake_on_view(session, wake)
    except Exception as e:
        print(f"earmark: suspend: {e!r}", file=sys.stderr)
    send_reports(reports, session)
    try:
        s_now = index["sessions"][session]
        for tab_id, label, mark in suspend.stale_marks(snap, s_now.get("suspended") or {}, s_now.get("marked") or {}):
            suspend.unmark_tab(tab_id, label, mark, session=session)
    except Exception as e:
        print(f"earmark: tab marks: {e!r}", file=sys.stderr)
    try:  # agent rows: refit, resend after a restart, Codex and Grok, clear the gone
        from . import agentrow
        agentrow.refresh(session, snap, cfg, index["sessions"][session].get("boot"))
    except Exception as e:
        print(f"earmark: agent rows: {e!r}", file=sys.stderr)
    try:  # opted in: Earmark's rows in Herdr's config.toml, recoloured for the theme
        from . import herdrconf
        herdrconf.keep_current(cfg)
    except Exception as e:
        print(f"earmark: Herdr's config.toml: {e!r}", file=sys.stderr)
    try:  # the launcher the status line, the skill and the theme hook go through
        from . import launcher
        launcher.ensure()
    except Exception as e:
        print(f"earmark: launcher: {e!r}", file=sys.stderr)


def note_config_dirs(snap, s):
    """The Claude folder each newly seen Claude session's process uses
    (CLAUDE_CONFIG_DIR from its own environment; "" when it has none),
    looked up once per session, so Earmark looks for its transcript where
    Claude keeps it even when Herdr's server has a different
    CLAUDE_CONFIG_DIR. A look that fails (Herdr doesn't answer, no process
    named claude in the foreground) records nothing, so the folder stays
    "unknown" (Earmark's own CLAUDE_CONFIG_DIR, else ~/.claude: the 1.0
    behaviour), and is tried again after CONFIG_DIR_RETRY."""
    from . import procs
    notes = s.get("panes") or {}
    t = now()
    for pid, p in snap["panes"].items():
        ref = p.get("agent_session") or {}
        if (ref.get("agent") or p.get("agent")) != "claude" or not ref.get("value"):
            continue
        note = notes.get(pid)
        if note and note.get("session_id") == ref["value"]:
            if note.get("config_dir") is not None or t - note.get("config_dir_tried", 0) < CONFIG_DIR_RETRY:
                continue
        p["_config_dir_tried"] = t
        try:
            info = herdr.process_info(pid)
        except herdr.HerdrError:
            continue
        claude = next((x for x in info.get("foreground_processes") or [] if x.get("name") == "claude"), None)
        if claude and isinstance(claude.get("pid"), int):
            value = procs.environ_var(claude["pid"], "CLAUDE_CONFIG_DIR")
            if value is not None:  # None: its environment couldn't be read; asked again later
                p["_config_dir"] = value


def _wait_for_session(pane_id):
    deadline = now() + SESSION_WAIT
    for _ in range(int(SESSION_WAIT / 0.4) + 1):  # bounded: a clock stepped back can't stretch it
        if now() >= deadline:
            return
        try:
            p = herdr.pane(pane_id)
        except herdr.HerdrError:
            return
        if (p.get("agent_session") or {}).get("value") or not p.get("agent"):
            return
        time.sleep(0.4)


def apply(index, archive, session, snap, event, data, t, server_pid=None, idle_clock=True):
    """Bring the notes for one Herdr session up to date with a snapshot, and
    archive what closed or exited. Returns True if the archive changed.
    `idle_clock`: keep the fields only the automatic suspend modes read
    (when each agent was left or changed status); off, a tab switch doesn't
    rewrite index.json."""
    sessions = index.setdefault("sessions", {})
    s = store.session_state(index, session)
    entries = archive.setdefault("entries", {})
    changed = False

    # A restart: the startup hook, or any hook from a new server process. The
    # restored panes' "released" events race the startup hook for the lock,
    # so whichever runs first after a restart marks the boot.
    restarted = event == "startup"
    if s.get("ppid_unreliable") and t - (s["ppid_unreliable"] if isinstance(s["ppid_unreliable"], (int, float)) else 0) > 6 * 3600:
        del s["ppid_unreliable"]  # give parent pids another chance
    if server_pid is not None and s.get("server_pid") not in (None, server_pid) and not s.get("ppid_unreliable"):
        # A new parent process means a new Herdr server, unless that happens
        # hook after hook (a Herdr that starts hooks through a helper): then
        # only the startup hook counts from now on.
        recent = [x for x in s.get("ppid_boots", []) if t - x < 600] + [t]
        s["ppid_boots"] = recent
        if len(recent) >= 3:
            s["ppid_unreliable"] = t
            print("earmark: hooks keep changing parent process; restarts are taken from the startup hook only",
                  file=sys.stderr)
        else:
            restarted = True
    if server_pid is not None:
        s["server_pid"] = server_pid
    suspended = s.setdefault("suspended", {})
    if restarted:
        known = set(s["panes"]) | set(suspended)
        back = known & set(snap["panes"])
        if len(known) >= 2 and len(back) * 2 < len(known) and not partial_snapshot(snap):
            # Herdr restores every pane at once; most of them missing means a
            # new session under the old name (ids start again): suspended
            # tabs whose ids came back belong to someone else now.
            for pid in [pid for pid in suspended if pid in back]:
                rec = suspended.pop(pid)
                changed |= archive_note(entries, session, labelled(dict(rec), {}), t, "closed")
                _drop_screen(rec)
            # The old workspaces went with them, and their ids start again
            # too: filed as closed, notes and all, before a new w1 shows one.
            for wid, layout in list((s.get("layouts") or {}).items()):
                changed |= record_closed_workspace(archive, session, wid, layout, t)
            s["layouts"] = {}
        s["boot"], s["boot_panes"] = t, sorted(s["panes"])
        s["boot_grace"] = boot_grace_for(len(s["panes"]) + len(suspended))
        if suspended and (server_pid is None or s.get("rearm_pid") != server_pid):
            # The placeholders died with the server: put them back (once per
            # server; its startup hook and its first other hook both see it).
            s["rearm"], s["rearm_pid"] = True, server_pid
            for rec in suspended.values():
                rec.pop("armed_by_rearm", None)
                rec.pop("base", None)  # a new server's shells: watched afresh
    if t - s.get("seen", 0) > 600:  # rewriting index.json for this alone every hook isn't worth it
        s["seen"] = t
    for other in [k for k, v in sessions.items()
                  if k != session and t - v.get("seen", t) > FORGET_SESSION_DAYS * 86400]:
        # Its suspended tabs go to the archive, never nowhere.
        for rec in (sessions[other].get("suspended") or {}).values():
            changed |= archive_note(entries, other, dict(rec), t, "closed")
            _drop_screen(rec)
        del sessions[other]

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

    # A workspace that's gone was closed: remember its tabs as one unit, so
    # it can be restored with exactly the tabs it had (its other archived
    # sessions stay in the archive).
    marked = s.get("marked") or {}
    booting = t - s.get("boot", 0) < grace(s)

    def said_closed(pane_id=None, tab_id=None, workspace_id=None):
        """Whether this hook's own event is Herdr saying it closed (no doubt
        then, even right after a restart)."""
        return ((event == "pane.closed" and pane_id and data.get("pane_id") == pane_id)
                or (event == "tab.closed" and tab_id and data.get("tab_id") == tab_id)
                or (event == "workspace.closed" and workspace_id and data.get("workspace_id") == workspace_id))

    partial = partial_snapshot(snap)
    kept_layouts = {}
    for wid, layout in s.get("layouts", {}).items():
        if wid not in snap["workspaces"]:
            if (booting and not said_closed(workspace_id=wid)) or partial:
                kept_layouts[wid] = layout  # right after a restart it may still be on its way back
            else:
                changed |= record_closed_workspace(archive, session, wid, layout, t)

    def current(note):
        return labelled(note, ws_labels)

    live = set()
    for pid, p in snap["panes"].items():
        ref = p.get("agent_session") or {}
        note = s["panes"].get(pid)
        if ref.get("value"):
            agent = ref.get("agent") or p.get("agent") or "unknown"
            live.add(f"{agent}:{ref['value']}")
            if note and note["session_id"] != ref["value"]:
                # A different session in the same pane (/clear, /resume): the old one closed.
                changed |= archive_note(entries, session, current(note), t, "replaced")
                note = None
            tab = snap["tabs"].get(p.get("tab_id"))
            if tab is None and note and note.get("tab_id") == p.get("tab_id"):
                # The tab closed between Herdr's pane and tab lists: keep its name.
                tab = {"label": note.get("tab_label"), "number": note.get("tab_number")}
            tab = tab or {}
            old = note if note and note.get("session_id") == ref["value"] else None
            new = {
                "pane_id": pid,
                "tab_id": p.get("tab_id"),
                "workspace_id": p.get("workspace_id"),
                "workspace_label": ws_labels.get(p.get("workspace_id"), (note or {}).get("workspace_label", "")),
                "tab_label": _unmarked(tab.get("label"), p.get("tab_id"), marked),
                "tab_number": tab.get("number"),
                "pane_label": p.get("label") or "",
                "agent": agent,
                "session_id": ref["value"],
                "source": ref.get("source"),
                "cwd": p.get("foreground_cwd") or p.get("cwd"),
                "title": agents.clean_title(p.get("terminal_title"), agent) or (note or {}).get("title", ""),
                # The session's own "seen", refreshed every 10 minutes: notes
                # aging one by one rewrote index.json on a third of quiet hooks.
                "seen": s["seen"],
            }
            for key in CARRY:
                if old and key in old:
                    new[key] = old[key]
            new.setdefault("since", t)
            if idle_clock and new.get("status") != p.get("agent_status"):
                new["status"], new["status_at"] = p.get("agent_status"), t
            if p.get("_config_dir") is not None:
                new["config_dir"] = p["_config_dir"]
            if p.get("_config_dir_tried"):
                new["config_dir_tried"] = p["_config_dir_tried"]
            s["panes"][pid] = new
        elif note:
            # The pane is alive but its agent is gone. Earmark stopped it to
            # suspend it: not an exit. A release right after a restart is a
            # deferred resume; keep the note for when it comes back.
            released = (event == "pane.agent_detected" and data.get("released")
                        and data.get("pane_id") == pid)
            rec = suspended.get(pid) or {}
            own_stop = rec.get("session_id") == note.get("session_id") and (
                rec.get("state") == "stopping" or note.get("since", 0) <= rec.get("at", 0))
            if own_stop:
                s["panes"].pop(pid)  # the agent Earmark is suspending
            elif pid in suspended and released:
                # The agent ran again after the record (resumed by hand, or
                # relaunched) and the user ended it: a real exit; the stale
                # record goes with it.
                changed |= archive_note(entries, session, current(s["panes"].pop(pid)), t, "exited")
                _drop_screen(suspended.pop(pid))
            elif released and not boot_protected(s, pid, t):
                changed |= archive_note(entries, session, current(s["panes"].pop(pid)), t, "exited")
            elif pid in s.get("boot_panes", []) and t - s.get("boot", 0) >= grace(s):
                # Its release came inside the restart grace (ignored then) and
                # the agent hasn't come back since: it exited.
                changed |= archive_note(entries, session, current(s["panes"].pop(pid)), t, "exited")
                s["boot_panes"] = [x for x in s["boot_panes"] if x != pid]

    # What's on screen: every pane of the tab in view (a split beside the pane
    # in use is in view too). Automatic modes never take the tab in view, and
    # its idle clock starts when the user leaves it: every pane of the tab
    # that was in view until now is stamped as it's left (no stamp while it
    # stays in view, so a hook doesn't rewrite index.json for nothing).
    if idle_clock:
        focused = next((p for p in snap["panes"].values() if p.get("focused")), None)
        tab_now = (focused or {}).get("tab_id")
        left = s.get("focused_tab") if s.get("focused_tab") != tab_now else None
        for pid, note in s["panes"].items():
            if (left and note.get("tab_id") == left) or (event == "pane.focused" and data.get("pane_id") == pid):
                note["focused_at"] = t
        s["focused_tab"] = tab_now
    s.pop("focused_pane", None)

    # Noted panes Herdr no longer has were closed, alone or with their tab or
    # workspace (right after a restart, a pane that was there may still be on
    # its way back).
    for pid in [pid for pid in s["panes"] if pid not in snap["panes"]]:
        note = s["panes"][pid]
        if partial or (booting and pid in s.get("boot_panes", [])
                       and not said_closed(pid, note.get("tab_id"), note.get("workspace_id"))):
            continue
        changed |= archive_note(entries, session, current(s["panes"].pop(pid)), t, "closed")

    changed |= settle_suspended(suspended, entries, session, snap, t, current, flags=s)

    # Marks of tabs Herdr no longer has are forgotten (a reused tab id
    # mustn't lose a name the user gave it that starts with the mark).
    if not partial and not booting and s.get("marked"):
        for tid in [tid for tid in s["marked"] if tid not in snap["tabs"]]:
            del s["marked"][tid]

    # Each live workspace's tabs as they are now (from the notes just
    # updated), for when it's closed.
    s["layouts"] = dict(tab_layouts(snap, s["panes"], suspended, marked), **kept_layouts)

    # A session that's live again (reopened, resumed by hand, restored) leaves the archive.
    for key in [k for k, e in entries.items() if f"{e['agent']}:{e['session_id']}" in live]:
        del entries[key]
        changed = True
    return changed


def _unmarked(label, tab_id=None, marked=None):
    """A tab name without Earmark's sleep mark: it's display only, never
    recorded (an archived or restored tab gets its own name back). Only a
    mark Earmark put there comes off (`marked`: tab id -> mark)."""
    mark = (marked or {}).get(tab_id)
    label = label or ""
    return label[len(mark) + 1:] if mark and label.startswith(mark + " ") else label


def _drop_screen(rec):
    from . import suspend
    suspend.drop_screen(rec)


def labelled(note, labels):
    """A note with its workspace's name as it is now (a rename and a close
    can land in the same snapshot)."""
    if note.get("workspace_id") in labels:
        note["workspace_label"] = labels[note["workspace_id"]]
    return note


def settle_suspended(suspended, entries, session, snap, t, current, flags=None):
    """Keep the suspended records true to what Herdr shows: a suspended tab
    that was closed goes to the archive; a session open in another pane is
    no longer suspended here; a stop that never finished, or a resume that
    never came back, ends its record (the latter in the archive). Returns
    True if the archive changed.

    Herdr can go on showing a stopped agent's session in its pane for a
    moment, so the session in its own pane counts as resumed only once the
    placeholder started it ("waking"), or for a stop still under way after
    STOP_STALE with Herdr seeing the agent (the stop didn't happen). Herdr's
    agent field isn't proof either way (it can list a stopped agent), so a
    "suspended" record stays; the worker checks the pane's processes
    (suspend.check_pane: Herdr's restore may relaunch the agent). A
    different session now in its pane means the suspended one was left:
    archived. A stop whose worker died midway is finished here: "suspended",
    and the regular re-arm pass starts its placeholder."""
    from . import suspend
    where = {}
    for pid, p in snap["panes"].items():
        ref = p.get("agent_session") or {}
        if ref.get("value"):
            where.setdefault(f"{ref.get('agent') or p.get('agent') or 'unknown'}:{ref['value']}", set()).add(pid)
    changed = False
    booting = flags is not None and t - flags.get("boot", 0) < grace(flags)
    for pid, rec in list(suspended.items()):
        if pid in snap["panes"] and (t - rec.get("seen_at", 0) >= 600 or rec.get("seen_at", 0) < (flags or {}).get("boot", 0)):
            rec["seen_at"] = t  # only "seen since the last restart" matters; not a write per hook
        panes = where.get(f"{rec.get('agent')}:{rec.get('session_id')}", set())
        state, since = rec.get("state"), rec.get("waking_at") or rec.get("at") or t
        here = snap["panes"].get(pid) or {}
        other = (here.get("agent_session") or {}).get("value")
        # Herdr listing the stopped session in its own pane means its restore
        # would relaunch it after a restart: remembered on the record (the
        # pane's note doesn't survive the first hook after a restart), so no
        # placeholder is typed while that may be under way (suspend.arm).
        if pid in panes and state in ("suspended", "stopping", "waking"):
            rec["herdr_listed"] = True  # a stop or a resume under way: Herdr's saved state names the agent too
        elif pid in snap["panes"] and not other and not booting and state == "suspended":
            rec.pop("herdr_listed", None)
        if pid in snap["panes"] and not booting:
            # Its tab's name, number and workspace, kept current (renames
            # included): after a restart a placeholder goes back only into a
            # tab that still matches (a recreated session reuses the ids).
            tab = snap["tabs"].get(here.get("tab_id")) or {}
            ws = snap["workspaces"].get(here.get("workspace_id")) or {}
            if tab:
                current_ids = {"tab_label": _unmarked(tab.get("label"), here.get("tab_id"), (flags or {}).get("marked")),
                               "tab_number": tab.get("number"), "workspace_label": ws.get("label") or ""}
                for k, v in current_ids.items():
                    if rec.get(k) != v:
                        rec[k] = v
        def runs_elsewhere():
            """Claude's own registry decides for Claude: Herdr can go on
            listing a session that no longer runs."""
            return rec.get("agent") != "claude" or agents.claude_running(rec.get("session_id"), rec.get("config_dir"))
        if panes - {pid} and runs_elsewhere():
            del suspended[pid]  # open somewhere else now
        elif pid in panes:
            stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE \
                and runs_elsewhere()
            if state != "waking" and not stop_failed:
                continue
            del suspended[pid]
        elif other:  # something else runs in its pane now: the suspended session was left
            changed |= archive_note(entries, session, current(dict(rec)), t, "replaced")
            del suspended[pid]
        elif state == "stopping" and pid in snap["panes"] and t - since > suspend.STOP_STALE:
            rec["state"], rec["at"] = "suspended", t  # the regular re-arm pass starts its placeholder
            continue
        elif pid not in snap["panes"]:
            if flags is not None and t - flags.get("boot", 0) < grace(flags) \
                    and rec.get("seen_at", 0) < flags.get("boot", 0):
                continue  # right after a restart Herdr may still be bringing it back
            if partial_snapshot(snap):
                continue  # a snapshot that can't be whole closes nothing
            changed |= archive_note(entries, session, current(dict(rec)), t, "closed")
            del suspended[pid]
        elif state == "waking" and t - since > suspend.RESUME_GRACE:
            changed |= archive_note(entries, session, current(dict(rec)), t, "exited")
            del suspended[pid]
        else:
            continue
        suspend.drop_screen(rec)
    return changed


def settle_now(session, snap, t=None):
    """settle_suspended outside a hook, for the worker and the key: a
    resume Herdr didn't report with an event still ends its record."""
    t = now() if t is None else t
    labels = {wid: w.get("label") or "" for wid, w in snap["workspaces"].items()}

    def current(note):
        return labelled(note, labels)

    with store.locked():
        index = store.load_index()
        s = (index.get("sessions") or {}).get(session)
        if not s or not s.get("suspended"):
            return  # nothing suspended: no need to read the archive
        archive = store.load_archive()
        before = json.dumps(s["suspended"], sort_keys=True)
        changed = settle_suspended(s["suspended"], archive.setdefault("entries", {}), session, snap, t, current,
                                   flags=s)
        if changed:  # the archive first (see handle_event)
            store.save_archive(archive)
        if json.dumps(s["suspended"], sort_keys=True) != before:
            store.save_index(index)


def tab_layouts(snap, notes=None, suspended=None, marked=None):
    """Per workspace: its label and its tabs in order, each with its name,
    folder, and the agent session it runs (or had when it was suspended),
    if any. Splits are not kept: a restored tab gets one pane (CLAUDE.md,
    "What Earmark is"). The order is `tab list`'s, which is the order on
    screen; a tab's "number" is fixed when it's created and doesn't follow
    moves."""
    notes, suspended = notes or {}, suspended or {}
    out = {}
    panes_by_tab = {}
    for p in sorted(snap["panes"].values(), key=lambda p: p["pane_id"]):
        panes_by_tab.setdefault(p.get("tab_id"), []).append(p)

    def ref_of(p):
        ref = p.get("agent_session") or {}
        if ref.get("value"):
            return {"agent": ref.get("agent") or p.get("agent"), "value": ref["value"]}
        rec = suspended.get(p["pane_id"])
        return {"agent": rec.get("agent"), "value": rec.get("session_id")} if rec else {}

    for tid, tab in snap["tabs"].items():
        wid = tab.get("workspace_id")
        w = snap["workspaces"].get(wid)
        if not w:
            continue
        panes = panes_by_tab.get(tid, [])
        agent_pane = next((p for p in panes if ref_of(p).get("value")), None)
        lead = agent_pane or (panes[0] if panes else {})
        ref = ref_of(agent_pane) if agent_pane else {}
        source = notes.get((agent_pane or {}).get("pane_id")) or suspended.get((agent_pane or {}).get("pane_id")) or {}
        entry = {
            "number": tab.get("number"),
            "label": _unmarked(tab.get("label"), tid, marked),
            "cwd": (source.get("cwd") if agent_pane and agent_pane["pane_id"] in suspended else None)
                   or lead.get("foreground_cwd") or lead.get("cwd") or "",
            "agent": ref.get("agent") if ref else None,
            "session_id": ref.get("value"),
        }
        if source.get("config_dir") is not None:
            entry["config_dir"] = source["config_dir"]
        if agent_pane and agent_pane["pane_id"] in suspended and suspended[agent_pane["pane_id"]].get("resume"):
            entry["resume"] = suspended[agent_pane["pane_id"]]["resume"]  # its options and permission mode
        layout = out.setdefault(wid, {"label": w.get("label") or "", "tabs": []})
        layout["tabs"].append(entry)
    return out


def record_closed_workspace(archive, session, wid, layout, t):
    if not layout.get("tabs"):
        return False
    key = f"{session}|{wid}|{int(t)}"
    record = archive.setdefault("workspaces", {})[key] = {
        "herdr_session": session,
        "workspace_id": wid,
        "label": layout.get("label") or "",
        "closed_at": t,
        "tabs": layout["tabs"],
    }
    from . import notes  # its note goes with it (Herdr reuses ids); the file goes once the archive is saved
    try:
        text = notes.read(session, wid)
    except OSError:
        text = ""
    if text.strip():
        record["note"] = text
    return True


def retire_notes(archive, session, t):
    """Note files of workspaces closed at `t`, now that their copies are
    saved in archive.json."""
    from . import notes
    for rec in archive.get("workspaces", {}).values():
        if rec.get("herdr_session") == session and rec.get("closed_at") == t and rec.get("note"):
            try:
                notes.retire(session, rec.get("workspace_id") or "", rec["note"])
            except OSError as e:
                print(f"earmark: note of {rec.get('label')}: {e}", file=sys.stderr)


def note_started(session, pane_id, tab_id, workspace_id, workspace_label, tab_label, agent, session_id,
                 cwd, title, source=None):
    """Note a session Earmark just started in a pane. Some agents (Codex)
    report their session to Herdr only after the next prompt, and without a
    note a reopened tab closed before then wouldn't be archived again."""
    with store.locked():
        index = store.load_index()
        s = store.session_state(index, session)
        s["panes"][pane_id] = {
            "pane_id": pane_id, "tab_id": tab_id, "workspace_id": workspace_id,
            "workspace_label": workspace_label, "tab_label": tab_label or "", "tab_number": None,
            "pane_label": "", "agent": agent, "session_id": session_id, "source": source,
            "cwd": cwd, "title": title or "", "seen": now(),
        }
        store.save_index(index)


def partial_snapshot(snap):
    """A snapshot that can't be whole, which closes nothing: Herdr always has
    a workspace, and every tab has a pane (an empty or cut-off answer from a
    server going away mustn't archive every live session)."""
    tabs_with_panes = {p.get("tab_id") for p in snap["panes"].values()}
    return not snap["workspaces"] or any(tid not in tabs_with_panes for tid in snap["tabs"])


def grace(s):
    """How long after a restart Herdr may still be bringing tabs back:
    BOOT_GRACE, or longer when Herdr spaces its agent restores out
    (`[session] startup_per_agent_delay_ms`), worked out at each restart."""
    return (s or {}).get("boot_grace") or BOOT_GRACE


def boot_grace_for(n_panes):
    value = herdr.setting("session", "startup_per_agent_delay_ms")
    try:
        delay = float(100 if value is None else value)  # Herdr's default is 100 ms
    except (TypeError, ValueError):
        delay = 100
    return max(BOOT_GRACE, 30 + n_panes * max(0.0, delay) / 1000)


def boot_protected(s, pid, t):
    return pid in s.get("boot_panes", []) and t - s.get("boot", 0) < grace(s)


def archive_note(entries, session, note, t, reason):
    """File a closed pane's session. Sessions with nothing to resume, and
    session ids that aren't safe to type into a shell, are skipped."""
    if not agents.safe_session_id(note.get("session_id")):
        return False
    facts = agents.session_facts(note["agent"], note["session_id"], config_dir=note.get("config_dir"))
    folder_unknown = note["agent"] == "claude" and note.get("config_dir") is None and facts["known"] \
        and not facts["exists"]
    if folder_unknown:
        # Its process's Claude folder couldn't be read, and the transcript
        # isn't in the default one: it may be in another. Filed, and kept
        # by keep_days like the sessions of agents Earmark can't look into.
        facts = dict(agents.UNKNOWN)
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
    if note.get("config_dir") is not None:
        entries[key]["config_dir"] = note["config_dir"]
    if folder_unknown:
        entries[key]["folder_unknown"] = True
    remember_source(entries[key], facts)
    return True


def remember_source(entry, facts):
    """Keep which file the facts came from and when it last changed (as
    entry["file"]), so the next prune can skip re-reading a file that hasn't
    (archived sessions rarely change; 300 of them took ~0.6 s to re-read on
    every popup). entry["source"] is Herdr's session source, a different
    thing."""
    path = facts.get("source")
    try:
        entry["file"] = [path, os.stat(path).st_mtime_ns] if path else None
    except OSError:
        entry["file"] = None


def unchanged_since_last_look(entry):
    cached = entry.get("file")
    if not cached:
        return False
    try:
        return os.stat(cached[0]).st_mtime_ns == cached[1]
    except OSError:
        return False


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
        if isinstance(e.get("source"), list):  # 0.1 kept the file cache under "source"
            e["file"], e["source"] = e.pop("source"), None
        if e.get("folder_unknown"):
            facts = {"known": False}  # its Claude folder wasn't known: keep_days decides
        elif unchanged_since_last_look(e):
            facts = {"known": True}  # same file, same facts as last time
        else:
            facts = agents.session_facts(e["agent"], e["session_id"], config_dir=e.get("config_dir"))
            if facts["known"]:
                if not (facts["exists"] and facts["has_content"]):
                    del entries[key]
                    changed = True
                    continue
                for field in ("last_active", "title"):
                    if facts[field] and facts[field] != e.get(field):
                        e[field] = facts[field]
                        changed = True
                old = e.get("file")
                remember_source(e, facts)
                changed |= e.get("file") != old
        # keep_days unset: the agent's own retention decides where Earmark can
        # look (the check above), FALLBACK_DAYS elsewhere.
        days = cfg["keep_days"] if cfg["keep_days"] is not None else (0 if facts["known"] else config.FALLBACK_DAYS)
        if days and t - (e.get("last_active") or e.get("closed_at") or t) > days * 86400:
            del entries[key]
            changed = True
    closed = archive.setdefault("workspaces", {})
    for key in list(closed):
        days = cfg["keep_days"] if cfg["keep_days"] is not None else config.FALLBACK_DAYS
        if closed[key].get("note"):  # the user's own text: kept until they forget the workspace
            continue
        if days and t - closed[key].get("closed_at", t) > days * 86400:
            del closed[key]
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
    if not agents.safe_session_id(entry["session_id"]):
        return "This session's id isn't safe to type into a shell, so Earmark won't reopen it."
    argv = agents.resume_argv(entry["agent"], entry["session_id"], cfg["resume"])
    if not argv:
        return f"Earmark doesn't know how to reopen {entry['agent']} sessions (add it under [resume] in config.toml)."
    if entry["agent"] == "claude" and agents.claude_running(entry["session_id"], entry.get("config_dir")):
        return "This session is open somewhere else already (another terminal or Herdr session)."
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
        tab_id, pane_id = herdr.new_tab(target, entry.get("cwd"), custom_name(entry))
        herdr.run_in_pane(pane_id, argv, agents.env_prefix(entry["agent"], entry.get("config_dir")))
    except herdr.HerdrError as e:
        return str(e)
    forget(entry["key"])
    note_started(herdr.session_name(), pane_id, tab_id, target,
                 (snap["workspaces"].get(target) or {}).get("label") or entry["workspace_label"],
                 custom_name(entry), entry["agent"], entry["session_id"], entry.get("cwd"),
                 entry.get("title"), entry.get("source"))
    return None


def closed_workspaces(archive, session):
    """Closed workspaces of one Herdr session, newest first."""
    rows = [dict(w, key=k) for k, w in archive.get("workspaces", {}).items() if w["herdr_session"] == session]
    return sorted(rows, key=lambda w: w.get("closed_at") or 0, reverse=True)


def forget_workspace(key):
    """Forget a closed workspace's grouping and its note (the popup says
    so first); its sessions stay archived."""
    with store.locked():
        archive = store.load_archive()
        if archive.get("workspaces", {}).pop(key, None) is not None:
            store.save_archive(archive)


def restore_workspace(record, cfg):
    """Bring a closed workspace back: its tabs in order, with their names and
    folders, each agent tab resuming its session. Into the live workspace of
    the same name if there is one, else a new one. Returns an error or None."""
    tabs = record.get("tabs") or []
    if not tabs:
        return "Nothing to restore."
    try:
        snap = herdr.snapshot()
    except herdr.HerdrError as e:
        return str(e)
    target = next((wid for wid, w in snap["workspaces"].items()
                   if (w.get("label") or "") == record["label"]), None)
    # A session already open elsewhere (reopened on its own since) stays
    # there: its tab is left out rather than running the session twice.
    live = {f"{(p.get('agent_session') or {}).get('agent') or p.get('agent')}:{p['agent_session']['value']}"
            for p in snap["panes"].values() if (p.get("agent_session") or {}).get("value")}
    tabs = [tb for tb in tabs if not (tb.get("session_id") and f"{tb.get('agent')}:{tb['session_id']}" in live)]
    if not tabs:
        return "Its sessions are all open already."
    first_cwd = next((tb["cwd"] for tb in tabs if tb.get("cwd") and os.path.isdir(tb["cwd"])),
                     os.path.expanduser("~"))
    resumed, started = [], []
    try:
        first_pane = first_tab = None
        if target:
            herdr.run("workspace", "focus", target)
        else:
            name = herdr.safe_label(record["label"])
            created = herdr.run("workspace", "create", "--cwd", first_cwd, *(["--label", name] if name else []), "--focus")
            target = created["workspace"]["workspace_id"]
            first_tab = created["tab"]["tab_id"]
            first_pane = (created.get("root_pane") or created.get("pane"))["pane_id"]
        for i, tab in enumerate(tabs):
            label = "" if is_default_tab_label(tab.get("label"), tab.get("number")) else herdr.safe_label(tab["label"])
            if i == 0 and first_pane:
                tab_id, pane_id = first_tab, first_pane
                if label:
                    herdr.run("tab", "rename", first_tab, label)
            else:
                tab_id, pane_id = herdr.new_tab(target, tab.get("cwd"), label, focus=(i == 0))
            argv = None
            if tab.get("session_id") and tab.get("agent"):
                facts = agents.session_facts(tab["agent"], tab["session_id"], config_dir=tab.get("config_dir"))
                elsewhere = tab["agent"] == "claude" and agents.claude_running(tab["session_id"], tab.get("config_dir"))
                if facts["exists"] and facts["has_content"] and not elsewhere:
                    argv = tab.get("resume") or agents.resume_argv(tab["agent"], tab["session_id"], cfg["resume"])
            if argv:
                herdr.run_in_pane(pane_id, argv, agents.env_prefix(tab.get("agent"), tab.get("config_dir")))
                resumed.append(f"{tab['agent']}:{tab['session_id']}")
                started.append((pane_id, tab_id, label, tab))
    except herdr.HerdrError as e:
        return str(e)
    if record.get("note"):  # back before the record goes, so a failure never loses it
        from . import notes
        try:
            notes.put_back(herdr.session_name(), target, record["note"])
        except OSError as e:
            return f"the workspace is back, but its note couldn't be written ({e}); it stays in the list"
    with store.locked():
        archive = store.load_archive()
        archive.get("workspaces", {}).pop(record["key"], None)
        for key in resumed:  # live again; the next hook would also drop them
            archive.get("entries", {}).pop(key, None)
        store.save_archive(archive)
    for pane_id, tab_id, label, tab in started:
        note_started(herdr.session_name(), pane_id, tab_id, target, record["label"], label,
                     tab["agent"], tab["session_id"], tab.get("cwd"), "")
    return None


# ---------------------------------------------------------------- sidebar

def noted_workspaces(session):
    """Workspace ids with a note (for the sidebar's note mark)."""
    from . import notes
    return notes.noted(session)


def pending_reports(index, archive, session, snap, cfg=None, cache=None):
    """The sidebar count tokens that changed since they were last sent
    (`cache`: sidebar.json, updated here), per workspace, each with the
    sequence number Herdr orders them by: taken here, under the lock, so
    counts worked out later always carry a higher one. Fitted to the
    sidebar's width (earmark/sidebar.py). Tokens don't survive a Herdr
    restart, so a new boot starts from nothing sent."""
    cfg = cfg or config.load()
    cache = store.load_sidebar() if cache is None else cache
    side = cfg["sidebar"]
    s = index["sessions"][session]
    mine = cache["sessions"].setdefault(session, {})
    if mine.get("boot") != s.get("boot"):
        mine.clear()
        mine["boot"] = s.get("boot")
    sent = mine.setdefault("spaces", {})
    for wid, text in (s.pop("reported", None) or {}).items():  # 1.1's "N archived", cleared once
        if isinstance(text, str) and text and not isinstance(sent.get(wid), dict):
            sent[wid] = text
    width = sidebar.sidebar_width(session)
    suspended = {}
    for pid in s.get("suspended") or {}:
        wid = (snap["panes"].get(pid) or {}).get("workspace_id") or pid.split(":")[0]
        suspended[wid] = suspended.get(wid, 0) + 1
    noted = noted_workspaces(session)
    out = []
    for wid, w in snap["workspaces"].items():
        label = w.get("label") or ""
        values = sidebar.count_values(snap, wid, suspended.get(wid, 0), len(listing(archive, session, label)),
                                      wid in noted)
        tokens = sidebar.count_tokens(sidebar.fit_counts(label, values, side["counts"], side["counts_line"], width))
        before = sent.get(wid)
        delta = sidebar.changed(tokens, before if isinstance(before, dict) else None)
        if before and not isinstance(before, dict):  # 1.1's "N archived", cleared once
            delta[sidebar.LEGACY_TOKEN] = None
        if delta:
            out.append((wid, delta, time.time_ns()))
        sent[wid] = tokens
    for wid in [wid for wid in sent if wid not in snap["workspaces"]]:
        del sent[wid]
    return out


def update_counts(session):
    """Resend any count tokens the archive's current state changes."""
    cfg = config.load()
    with store.locked():
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError:
            return
        index, archive, cache = store.load_index(), store.load_archive(), store.load_sidebar()
        store.session_state(index, session)
        before = json.dumps(index, sort_keys=True)
        reports = pending_reports(index, archive, session, snap, cfg, cache)
        store.save_sidebar(cache)
        if json.dumps(index, sort_keys=True) != before:
            store.save_index(index)
    send_reports(reports, session)


def send_reports(reports, session):
    failed = []
    for wid, tokens, seq in reports:
        try:
            sidebar.report("workspace", wid, tokens, seq)
        except herdr.HerdrError as e:
            print(f"earmark: sidebar counts for {wid}: {e}", file=sys.stderr)  # shows in `herdr plugin log`
            failed.append(wid)
    if failed:  # not shown: the next hook doesn't know what is, so it sends them whole
        with store.locked():
            cache = store.load_sidebar()
            spaces = (cache["sessions"].get(session) or {}).get("spaces") or {}
            for wid in failed:
                if wid in spaces:
                    spaces[wid] = {}
            store.save_sidebar(cache)
