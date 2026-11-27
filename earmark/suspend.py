"""Suspend tabs in place (CLAUDE.md, "Suspend"; docs/PLAN.md, phase I).

An idle agent is ended to free its memory, and its pane gets a placeholder
(`earmark.py suspended`, earmark/placeholder.py) that shows its last screen,
or a notice. The line typed into the pane's shell is `placeholder && resume
command`: on Enter the placeholder exits 0 and the shell starts the agent
again, as a new job, the way a person would.

Who does what:
- Hooks (core.handle_event) keep Earmark's notes, and at most once a minute,
  when an automatic mode is on, start a short-lived worker. They also press
  Enter for "resume on view", and start a worker to put placeholders back
  after a Herdr restart. No process outlives its job.
- The worker (`earmark.py worker`) picks the agents to suspend, checks each
  one again right before acting, and suspends it.
- The suspend key (`earmark.py suspend`) asks a worker to suspend the pane
  in view, or presses Enter in its placeholder.

Records live in index.json under their Herdr session ("suspended", by pane
id). One is written before the agent is stopped and ends only once its
session is live again, or by going to the archive (a suspended tab closed,
a placeholder left with Ctrl+C, a resume that never came back, the session
open elsewhere, a Herdr session forgotten): a suspended session is never
dropped without a trace.
"""
import hashlib
import os
import re
import shlex
import signal
import subprocess
import sys
import time

from . import agents, config, herdr, message, procs, store

QUIET = 10 * 60        # memory and count modes: quiet at least this long first
CHECK_EVERY = 60       # seconds between automatic checks
STOP_WAIT = 15         # seconds an agent gets to exit after SIGTERM (never SIGKILL)
STOP_STALE = 60        # a "stopping" record this old whose agent Herdr still sees: the stop failed
BACKOFF = 30 * 60      # after a failed stop or a placeholder that didn't start, leave the pane this long
RESUME_GRACE = 90      # a resume whose session hasn't shown up after this goes to the archive
WAKE_DWELL = 0.8       # resume on view: the pane must still be in view after this
MEMORY_MARGIN = 5      # memory mode stops once this many points above memory_below
MAX_PER_CHECK = 6      # memory mode: at most this many in one check
TIMER_GRACE = 5 * 60   # a /loop wake-up this late without a new one: the loop ended
REARM_WAIT = 30        # after a restart, how long to wait for a pane's shell
RELEASE_WAIT = 6       # after the agent exits, how long Herdr gets to let go of it
ARM_CLAIM = 15         # an arm in progress holds its record this long
STABLE = 2             # an automatic arm: the shell's screen unchanged at two looks this far apart
AWAY_GAP = 15 * 60     # Herdr quiet this long (a laptop asleep, a night away) ...
RETURN_GRACE = 5 * 60  # ... and automatic suspends wait this long after it wakes up

# Launchers that stand for the agent itself (an npm install's node, say);
# any other process between the shell and the agent is a wrapper Earmark
# can't bring back (`aws-vault exec -- claude`).
LAUNCHERS = {"node", "bun", "deno"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Herdr's process names for the agents whose process Earmark looks for by name;
# others are the foreground group's leader.
PROCESS_NAMES = {"claude": "claude", "codex": "codex", "grok": "grok"}

# Shells that can run the typed line (`a && b`, `VAR=x cmd`): bash, zsh,
# fish 3.1+, POSIX sh. nushell, elvish, csh and tcsh can't.
SHELLS_OK = {"bash", "zsh", "fish", "sh", "dash", "ksh", "mksh", "ash", "busybox"}

# Answers that aren't refusals but need the user (the key) or a retry.
CONFIRM = "confirm: "
CONFIRM_WINDOW = 10    # messages = "toast": a second press within this many seconds confirms
CONFIRM_MIN = 1        # ... and not sooner (a double tap isn't a decision)
READ_BUDGET = 2.0      # seconds a look may spend catching up on a long transcript
UNREADABLE_PROMPT = "Earmark can't read its prompt to check for unsent text"
NO_ANSWER = "Herdr didn't answer, so Earmark can't check the session isn't open elsewhere; press Enter to try again"
NOT_YET = "suspended; Herdr is still catching up, so its placeholder comes within a minute or so (or press the key again)"


def log(message):
    """One line in worker.log (the worker's stdout)."""
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


session_state = store.session_state


def record(session, pane_id):
    """The suspended record of a pane, or None."""
    s = store.load_index().get("sessions", {}).get(session) or {}
    return (s.get("suspended") or {}).get(pane_id)


def timers_file(session):
    """Claude timer offsets, one file per Herdr session (named sessions would
    otherwise keep wiping each other's)."""
    return f"timers-{hashlib.sha256(session.encode()).hexdigest()[:12]}.json"


def load_timers(session):
    return store.load_json(timers_file(session))


def save_timers(session, timers, keep=None):
    new = {k: v for k, v in timers.items() if keep is None or k in keep}
    with store.locked():
        if store.load_json(timers_file(session)) != new:  # not a write (and fsync) per check
            store.save_json(timers_file(session), new)


def screen_path(session, pane_id):
    name = hashlib.sha256(f"{session}|{pane_id}".encode()).hexdigest()[:16]
    return os.path.join(store.screens_dir(), f"{name}.ansi")


def drop_screen(rec):
    path = (rec or {}).get("screen")
    if path and os.path.dirname(path) == store.screens_dir():
        try:
            os.unlink(path)
        except OSError:
            pass


def shell_safe(path):
    return bool(path) and os.path.isabs(path) and not agents.UNTYPABLE.search(path)


def resume_command(rec):
    """The shell command that brings the session back: into its folder, with
    its Claude folder, the resume command. The shell runs it as a new job,
    the way a person would, so Herdr sees the agent start as usual. (An
    agent exec'd in the placeholder's place kept its process group, and
    Herdr then lost track of it.)"""
    parts = []
    if shell_safe(rec.get("cwd")):
        parts.append("cd " + shlex.quote(rec["cwd"]))
    parts.append(agents.env_prefix(rec.get("agent"), rec.get("config_dir")) + shlex.join(rec.get("resume") or []))
    return " && ".join(parts)


def line_safe(session, pane_id):
    """Whether the placeholder's own line can be typed into every shell: its
    Python, Earmark's folder, the state and settings folders, the session
    and pane names. Checked before anything is stopped (a backslash in HOME
    would break the line under fish with the agent already gone)."""
    paths = [ROOT, store.state_dir(), config.config_dir()] + ([sys.executable] if sys.executable else [])
    return all(shell_safe(p) for p in paths) and not any(agents.UNTYPABLE.search(w or "") for w in (session, pane_id))


def placeholder_command(session, pane_id, rec):
    """What's typed into the pane's shell: the placeholder, then (only if it
    exits 0: Enter, the session not open elsewhere) the resume command. The
    placeholder is told where Earmark's files are (a pane doesn't have
    Herdr's plugin variables). A leading space keeps the line out of the
    shell's history where the shell ignores such lines."""
    placeholder = shlex.join([sys.executable or "python3", os.path.join(ROOT, "earmark.py"),
                              "suspended", session, pane_id,
                              "--state", store.state_dir(), "--config", config.config_dir()])
    return f" {placeholder} && {resume_command(rec)}"


# ----------------------------------------------------------------- facts

def chain_to(table, main, running):
    """The agent's process and its ancestors up to the foreground group's
    leader (a wrapper such as Codex's node launcher)."""
    group = {x["pid"] for x in running}
    chain, pid = [main], main
    while True:
        parent = table.ppid(pid)
        if parent not in group or parent in chain:
            return chain
        chain.append(parent)
        pid = parent


def look(pane, note, table, t, timers):
    """What Earmark can find out about a live agent pane, for deciding
    whether to suspend it. `timers` is the cache for agents.claude_timers."""
    ref = pane.get("agent_session") or {}
    agent = ref.get("agent") or pane.get("agent") or "unknown"
    out = {"pane_id": pane["pane_id"], "agent": agent, "session_id": ref.get("value"), "why": ""}
    try:
        info = herdr.process_info(pane["pane_id"])
    except herdr.HerdrError as e:
        return dict(out, why=f"Earmark can't see its processes ({e})")
    shell, group = info.get("shell_pid"), info.get("foreground_process_group_id")
    running = [x for x in info.get("foreground_processes") or [] if isinstance(x.get("pid"), int)]
    if not group or group == shell or not running:
        return dict(out, why="the agent isn't running in the foreground")
    if any(is_placeholder(x) for x in running):
        return dict(out, why="it's suspended already")
    shell_name = (table.procs.get(shell) or (0, "", ""))[1].lstrip("-")
    if shell_name and shell_name not in SHELLS_OK:
        return dict(out, why=f"its shell ({shell_name}) can't run Earmark's resume line")
    leader = next((x for x in running if x["pid"] == group), running[0])
    parent = table.ppid(leader["pid"])
    if parent is not None and shell and parent != shell:
        # The agent runs under a second shell (`nix develop`, `bash` typed in
        # zsh): the pane's shell never comes back for the placeholder.
        return dict(out, why="it was started from a nested shell")
    named = PROCESS_NAMES.get(agent)
    main = next((x for x in running if x.get("name") == named), None) if named else leader
    if main is None:  # never stop something that isn't the agent
        return dict(out, why=f"{agent} isn't what's running in the foreground")
    out["leader_name"] = leader.get("name") or ""
    chain = chain_to(table, main["pid"], running)
    out.update(group=group, shell=shell, pid=main["pid"], chain=chain,
               tokens={pid: procs.start_token(pid) for pid in chain}, launch=main.get("argv") or [])
    if any(token is None for token in out["tokens"].values()):
        return dict(out, why="Earmark can't read its process's start time, so it can't be sure it's the same process later")
    out["cwd_unsafe"] = not shell_safe(pane.get("foreground_cwd") or pane.get("cwd") or note.get("cwd") or "")
    # Busy: a shell anywhere under the agent (a Bash tool call, a Monitor), or
    # anything else sharing its terminal's foreground group that isn't the
    # agent, its launcher or its own child (a `nohup … &` server, a pipe).
    mine = set(chain) | set(table.descendants(main["pid"]))
    strangers = [x for x in running if x["pid"] not in mine]
    out["busy"] = table.busy([main["pid"]]) or (
        f"{strangers[0].get('name')}: {(strangers[0].get('cmdline') or '')[:60]}" if strangers else "")
    kept, unknown = agents.launch_flags(agent, out["launch"])
    wrappers = [(table.procs.get(pid) or (0, "?", ""))[1] for pid in chain[1:]]
    unknown += [f"(started through {name})" for name in wrappers if name not in LAUNCHERS]
    out["flags"], out["unknown_flags"] = kept, unknown
    note = note or {}
    config_dir = note.get("config_dir")
    if agent == "claude" and config_dir is None:
        config_dir = procs.environ_var(main["pid"], "CLAUDE_CONFIG_DIR")  # None: unreadable, so unknown
    out["config_dir"] = config_dir
    out["account"] = agents.account_env(procs.environ(main["pid"]))  # None: unreadable
    facts = agents.session_facts(agent, out["session_id"], config_dir=config_dir, title=False)
    out["facts"] = facts
    activity = [note.get(k) or 0 for k in ("since", "focused_at", "status_at")]
    out["timers"], out["registry"] = "", {}
    if agent == "claude" and facts.get("source"):
        path = facts["source"]
        activity.append(agents.claude_activity(path) or 0)
        # Timers count from the process's start; unknown, every one counts.
        started = procs.started_at(main["pid"]) or 0
        cache = timers.setdefault(f"claude:{out['session_id']}", {})
        wake, tasks = agents.claude_timers(path, started, cache, t)
        # A big transcript is read on now, within a time budget (8 MB takes
        # milliseconds), so the key needn't be pressed once per 8 MB.
        budget = time.monotonic() + READ_BUDGET
        while cache.get("behind") and time.monotonic() < budget:
            before = cache.get("offset")
            wake, tasks = agents.claude_timers(path, started, cache, t)
            if cache.get("offset") == before:
                break  # a line still being written: the next look reads it
        out["mode"] = cache.get("mode", "")  # the last permission mode, from reading the whole transcript
        if cache.get("behind"):
            out["timers"] = "Earmark hasn't read its whole transcript yet"
        elif wake and wake + TIMER_GRACE + pushed_back(cache, timers.get("_away"), wake) > t:
            out["timers"] = "it's waiting on a /loop wake-up"
        elif tasks:
            out["timers"] = "it has scheduled tasks"
        if not out["timers"]:
            durable = agents.durable_tasks(pane.get("foreground_cwd") or pane.get("cwd"))
            if durable != 0:  # some, or a file Earmark can't read
                out["timers"] = "it has scheduled tasks that outlive the session"
        out["registry"] = agents.claude_registry(main["pid"], config_dir)
    elif facts.get("last_active"):
        activity.append(facts["last_active"])
    out["activity"] = max(activity)
    out["memory_kb"] = procs.memory_kb(sorted(mine))
    return out


def slept(away, since):
    """Seconds of a quiet spell (`away`: [from, to], Herdr quiet longer than
    AWAY_GAP, as when the machine sleeps) after `since`."""
    if isinstance(away, list) and len(away) == 2:
        return max(0, away[1] - max(away[0], since))
    return 0


def pushed_back(cache, away, wake):
    """How much later a /loop wake-up comes than its wall-clock time:
    Claude's timers don't run while the machine sleeps, so any sleep after
    the wake-up was set pushes it back. Counted from the machine's own
    suspended time since Earmark read the call (Linux), or a quiet spell
    since it was set, whichever is longer."""
    since = cache.get("wake_from") or wake
    shift = slept(away, since)
    now_slept, then = procs.suspended_seconds(), cache.get("wake_slept")
    if now_slept is not None and isinstance(then, (int, float)):
        shift = max(shift, now_slept - then)
    return max(0, shift)


def cant_check(found):
    """What Earmark can't check about an agent it looked at: the automatic
    modes refuse on any of these; the key asks (with an unreadable prompt
    and a status Herdr can't tell, which suspend_pane adds)."""
    out = []
    if found.get("unknown_flags"):
        out.append(f"it was started with options Earmark can't bring back ({' '.join(found['unknown_flags'])})")
    if found.get("agent") == "claude" and not (found.get("facts") or {}).get("known", True):
        out.append("Earmark can't read its Claude folder, so it can't check its timers or Remote Control")
    elif found.get("agent") == "claude" and not found.get("registry"):
        out.append("Claude's own record of this process is missing, so Earmark can't tell if it's busy "
                   "or has Remote Control on")
    return out


def refusal(found, pane, cfg, t, manual, focused_tab, note=None):
    """Why this pane mustn't be suspended now, or "" if it may (the parking
    rule; CLAUDE.md, "Suspend")."""
    if found.get("why"):
        return found["why"]
    agent, sid = found["agent"], found["session_id"]
    if not agents.safe_session_id(sid):
        return "its session id isn't safe to type into a shell"
    if not agents.resume_argv(agent, sid, cfg["resume"]):
        return f"Earmark doesn't know how to resume {agent} sessions"
    if agent == "codex" and "--no-daemon" not in (found.get("launch") or []):
        # Herdr can list another tab's session for it (herdrdev/herdr#4649):
        # suspended, the wrong conversation would come back.
        return "Codex was started without --no-daemon, so Earmark can't be sure which session it has"
    if agent not in PROCESS_NAMES and found.get("leader_name") and found["leader_name"] != agent:
        return f"Earmark can't tell which process is {agent} ({found['leader_name']} leads its terminal)"
    status = pane.get("agent_status")
    if status == "working":
        return "it's working"
    if status == "blocked":
        return "it's waiting on a question"
    if not manual:
        if status == "done" and not cfg["suspend"]["suspend_unseen"]:
            return "it has a result you haven't seen"
        if status not in ("idle", "done"):
            return f"it's {status or 'not idle'}"
        if focused_tab and pane.get("tab_id") == focused_tab:
            return "it's in view"
        if (note or {}).get("backoff_until", 0) > t:
            return "a recent try to suspend it failed"
        unsure = cant_check(found)
        if unsure:
            return unsure[0]
    facts = found.get("facts") or {}
    if facts.get("known") and not (facts.get("exists") and facts.get("has_content")):
        return "it has nothing saved to resume yet"
    if found.get("busy"):
        return f"a command is running in it ({found['busy']})"
    if found.get("timers"):
        return found["timers"]
    registry = found.get("registry") or {}
    if agent == "claude" and registry.get("session_id") and registry["session_id"] != sid:
        # Herdr can go on listing a session the pane no longer runs: Claude's
        # own record of the process says which conversation it has open.
        return "Claude has a different conversation open than the one Herdr shows"
    if agent == "claude" and found.get("config_dir") and not agents.env_prefix("claude", found["config_dir"]):
        return "its Claude folder's name can't be typed back safely, so the resume wouldn't find it"
    if found.get("cwd_unsafe"):
        return "its folder's name can't be typed back safely, so the resume would start elsewhere"
    if registry.get("remote"):
        return "Remote Control is on"
    if registry.get("status") not in (None, "idle"):
        return "it's working" if registry["status"] == "busy" else f"Claude says it's {registry['status']}"
    return ""


def focused_tab_of(snap):
    focused = next((p for p in snap["panes"].values() if p.get("focused")), None)
    return (focused or {}).get("tab_id")


def candidate_status(status, cfg):
    return status == "idle" or (status == "done" and cfg["suspend"]["suspend_unseen"])


# ---------------------------------------------------------------- choosing

def choose(looks, cfg, t, available=None, total_kb=None):
    """Which panes an automatic check suspends, oldest activity first.
    `looks` is [(pane, note, found or None)]; None marks an agent that's
    awake and not a candidate (working, in view, ...). Pure, for tests."""
    scfg = cfg["suspend"]
    mode = scfg["when"]
    ok = [(p, n, f) for p, n, f in looks if f is not None and not refusal(f, p, cfg, t, False, None, n)]
    ok.sort(key=lambda item: item[2]["activity"])
    if mode == "time":
        return [item for item in ok if t - item[2]["activity"] >= scfg["idle_minutes"] * 60]
    quiet = [item for item in ok if t - item[2]["activity"] >= QUIET]
    if mode == "count":
        recent = sorted(looks, key=lambda item: t if item[2] is None else item[2].get("activity", t), reverse=True)
        keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"]]}
        return [item for item in quiet if item[0]["pane_id"] not in keep]
    if mode == "memory":
        if available is None or available >= scfg["memory_below"] or not total_kb:
            return []
        chosen, freed = [], 0.0
        for item in quiet:
            if len(chosen) >= MAX_PER_CHECK or available + freed >= scfg["memory_below"] + MEMORY_MARGIN:
                break
            chosen.append(item)
            freed += 100.0 * item[2].get("memory_kb", 0) / total_kb
        return chosen
    return []


# ------------------------------------------------------------------ worker

def worker(session, cfg, pane_id=None, rearm=False, accept=None, pressed=None, rearm_pass_only=False):
    """`earmark.py worker`: put placeholders back after a restart, act on the
    key for one pane (`accept`: the doubt the user said `y` to in the
    popup), or run an automatic check."""
    if rearm:
        rearm_all(session)
    if rearm_pass_only:  # placeholders missing while no automatic check runs
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError:
            return
        rearm_pass(session, snap, skip_tab=focused_tab_of(snap))
        return
    if pane_id and accept is not None:
        why = confirm(session, pane_id, accept)
        if why:
            tell(session, pane_id, why, cfg, pressed)  # "suspended" or "kept running", as it really went
        return
    if pane_id:
        manual(session, pane_id, cfg, pressed=pressed)
        return
    if cfg["suspend"]["when"] not in config.AUTO_MODES:
        return
    with store.try_lock("worker-" + hashlib.sha256(session.encode()).hexdigest()[:12]) as mine:
        if mine:
            auto(session, cfg)


def auto(session, cfg):
    t = time.time()
    settings_seen = _mtime(config.config_path())  # a change from here on stops the check
    try:
        snap = herdr.snapshot()
    except herdr.HerdrError as e:
        log(f"{session}: check skipped: {e}")
        return
    from . import core
    core.settle_now(session, snap, t)
    focused_tab = focused_tab_of(snap)
    if focused_tab is None:
        log(f"{session}: no pane is in focus, so Earmark can't tell what's in view; check skipped")
        return
    rearm_pass(session, snap, skip_tab=focused_tab)  # placeholders that went missing
    mode = cfg["suspend"]["when"]
    if cfg.get("_broken"):
        log(f"{session}: config.toml has a problem ({cfg['_broken']}); no automatic suspends until it's fixed")
        return
    available = procs.available_percent()
    if mode == "memory" and (available is None or available >= cfg["suspend"]["memory_below"]):
        return  # nothing to do: don't look at anyone
    s = store.load_index().get("sessions", {}).get(session) or {}
    if t < s.get("quiet_until", 0):
        return  # Herdr just came back from a long silence: give the user a moment first
    notes, suspended = s.get("panes") or {}, s.get("suspended") or {}
    table = None  # the process table, built on the first look that needs it
    timers = load_timers(session)
    timers["_away"] = s.get("away")  # for look(): a quiet spell pushes /loop wake-ups back
    soonest = cfg["suspend"]["idle_minutes"] * 60 if mode == "time" else QUIET
    looks = []
    for pid, p in snap["panes"].items():
        if not (p.get("agent_session") or {}).get("value") or pid in suspended:
            continue
        note = notes.get(pid) or {}
        recent = max((note.get(k) or 0) for k in ("since", "focused_at", "status_at"))
        if not candidate_status(p.get("agent_status"), cfg) or p.get("tab_id") == focused_tab \
                or note.get("backoff_until", 0) > t or t - recent < soonest:
            looks.append((p, note, None))  # awake, and no need to look closer yet
            continue
        table = table or procs.Table()
        looks.append((p, note, look(p, note, table, t, timers)))
    live = {f"claude:{p['agent_session']['value']}" for p in snap["panes"].values()
            if (p.get("agent_session") or {}).get("value")}
    save_timers(session, timers, keep=live)
    last = time.time()
    for p, note, found in choose(looks, cfg, t, available, procs.total_kb()):
        if time.time() - last > AWAY_GAP:  # the machine slept mid-check: coming back isn't idleness
            log(f"{session}: the clock jumped during the check; check stopped")
            return
        last = time.time()  # each suspend takes half a minute at most
        if _mtime(config.config_path()) != settings_seen:  # changed meanwhile: obey the new settings
            cfg, settings_seen = config.load(), _mtime(config.config_path())
            if cfg.get("_broken") or cfg["suspend"]["when"] != mode:
                log(f"{session}: settings changed ({cfg.get('_broken') or cfg['suspend']['when']}); check stopped")
                return
        why = suspend_pane(session, p["pane_id"], cfg, mode, manual=False,
                           min_idle=(cfg["suspend"]["idle_minutes"] * 60 if mode == "time" else QUIET))
        idle = int((t - found.get("activity", t)) / 60)
        log(f"{session} {p['pane_id']}: {'suspended' if not why else 'kept'} ({found['agent']}, idle {idle} min, "
            f"{mode}){': ' + why if why else ''}")
        if mode == "memory" and not why:
            now = procs.available_percent()
            if now is not None and now >= cfg["suspend"]["memory_below"] + MEMORY_MARGIN:
                break


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def manual(session, pane_id, cfg, pressed=None):
    rec = record(session, pane_id)
    if rec and rec.get("state") == "suspended":
        try:
            p, info = herdr.pane(pane_id), herdr.process_info(pane_id)
        except herdr.HerdrError:
            p, info = {}, {}
        state = resumed_by_herdr(rec, p, info) if p else False
        if state == "other":
            to_archive(session, pane_id, "replaced")
        elif state:
            drop_record(session, pane_id, "the agent is running again")
        else:
            # Suspended, but its placeholder isn't up (a failed start, a
            # killed process): the key starts it again, whatever any backoff
            # says, though never while Herdr still lists the agent.
            ok = arm(session, pane_id, force=True, view_ok=True)
            log(f"{session} {pane_id}: placeholder {'started again' if ok else 'not started'} (key)")
            if not ok:
                say(cfg, "This tab is suspended", "Its placeholder can't come up yet (Herdr may still list the "
                    "stopped agent, or have just restarted). Press the key again in a moment. Closing the tab "
                    "files the session in the archive.")
            return
    refused = off_or_broken(cfg)
    if refused:
        say(cfg, *refused)
        return
    why = suspend_pane(session, pane_id, cfg, "manual", manual=True)
    if why.startswith(CONFIRM) and toast_mode(cfg) and confirmed(session, pane_id, why[len(CONFIRM):],
                                                                pressed or time.time()):
        why = suspend_pane(session, pane_id, cfg, "manual", manual=True, accept=why[len(CONFIRM):])
    log(f"{session} {pane_id}: {'suspended' if not why else 'kept'} (key){': ' + why if why else ''}")
    tell(session, pane_id, why, cfg, pressed)


def toast_mode(cfg):
    """The key answers through Herdr's toasts (messages = "toast")."""
    return cfg["suspend"].get("messages") == "toast"


LATE = 5  # seconds after the press: an answer this late doesn't take the keyboard if a toast will do


def say(cfg, title, body="", pressed=None):
    """A message from the key: in toast mode Herdr's toast, unless Herdr
    answers that it didn't show it (toasts off, rate limited, busy, no
    client) or doesn't say; then, and by default, Earmark's popup. An
    answer that comes long after the press tries a toast first in any mode
    (a popup then would take a keystroke meant for something else)."""
    late = bool(pressed) and time.time() - pressed > LATE
    if (toast_mode(cfg) or late) and herdr.notify(title, body) is True:
        return
    message.show(title, body, focus=not late)  # late: seen, but not in the way of what's being typed


def confirmed(session, pane_id, why, t):
    """messages = "toast": the key's second press. True if the same pane was
    asked about the same doubt, in a toast Herdr showed, within
    CONFIRM_WINDOW (and uses it up)."""
    with store.locked():
        index = store.load_index()
        asks = session_state(index, session).setdefault("confirm", {})
        ask = asks.pop(pane_id, None)
        store.save_index(index)
    return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why


def remember_ask(session, pane_id, why, t):
    """Start the second-press window, only after a toast Herdr showed."""
    with store.locked():
        index = store.load_index()
        asks = session_state(index, session).setdefault("confirm", {})
        for pid in [pid for pid, a in asks.items() if a.get("until", 0) < t]:
            del asks[pid]  # old asks nobody answered
        asks[pane_id] = {"why": why, "asked": t, "until": t + CONFIRM_WINDOW}
        store.save_index(index)


def off_or_broken(cfg):
    """(title, body) when the key mustn't suspend anything, else None."""
    if cfg.get("_broken"):
        return ("Earmark: config.toml has a problem",
                f"{cfg['_broken']}. Nothing is suspended until it's fixed (earmark.py check shows more).")
    if cfg["suspend"]["when"] == "off":
        return ("Earmark: suspending tabs is off",
                "Set when under [suspend] in Earmark's config.toml (earmark.py check shows where).")
    return None


def tell(session, pane_id, why, cfg, pressed=None):
    """The key's answer (say()): a doubt becomes a question, which `y`
    confirms in the popup, or a second press in toast mode."""
    if why.startswith(CONFIRM):
        doubt = why[len(CONFIRM):]
        # A question goes by toast only with Herdr's own in-app toasts (a
        # terminal or desktop notification may never be seen) and only if
        # Herdr says it showed it; otherwise the popup asks.
        shown = toast_mode(cfg) and herdr.setting("ui.toast", "delivery") == "herdr" and herdr.notify(
            "Earmark: press again to suspend",
            f"{doubt[0].upper() + doubt[1:]}. Press the key again within {CONFIRM_WINDOW} seconds to suspend it "
            "anyway.") is True
        name = tab_name(pane_id)
        if shown:
            remember_ask(session, pane_id, doubt, time.time())
        elif pressed and time.time() - pressed > LATE:
            # Long after the press the user is likely typing elsewhere: a
            # question would take the keyboard (and maybe a `y` meant for
            # something else). Say it instead; the key asks next time.
            say(cfg, f"Earmark kept {quoted(name)} running" if name else "Earmark kept the tab running",
                f"{doubt[0].upper() + doubt[1:]}. Press the key again in that tab to be asked whether to "
                "suspend it anyway.", pressed)
        else:  # never a second press for a question nobody saw: the popup asks
            message.show(f"Suspend {quoted(name)} anyway?" if name else "Suspend this tab anyway?",
                         doubt[0].upper() + doubt[1:] + ".",
                         ask={"session": session, "pane_id": pane_id, "why": doubt})
    elif why == NOT_YET:
        say(cfg, "Suspended", "Herdr is still catching up, so its placeholder comes once Herdr lets go of the agent "
            "(usually within a minute); press the key again to try now.", pressed)
    elif why and (record(session, pane_id) or {}).get("state") == "suspended":
        say(cfg, "Suspended", f"Its placeholder isn't up ({why}); press the key again to show it.", pressed)
    elif why:
        say(cfg, "Earmark can't suspend this tab", why[0].upper() + why[1:] + ".", pressed)


def tab_name(pane_id):
    """The name of the pane's tab as the user sees it, or "" (Herdr busy)."""
    try:
        tab_id = herdr.pane(pane_id).get("tab_id")
        return ((herdr.run("tab", "get", tab_id) or {}).get("tab") or {}).get("label") or ""
    except (herdr.HerdrError, AttributeError, TypeError):
        return ""


def quoted(name):
    return f"\u201c{name}\u201d"


def confirm(session, pane_id, why):
    """`y` in the popup's question: suspend, accepting exactly the doubt that
    was shown (if Earmark's doubts changed meanwhile, it asks again).
    Returns why it didn't, or ""."""
    cfg = config.load()
    refused = off_or_broken(cfg)
    if refused:
        return refused[0].replace("Earmark: ", "")  # "suspending tabs is off", "config.toml has a problem"
    out = suspend_pane(session, pane_id, cfg, "manual", manual=True, accept=why)
    log(f"{session} {pane_id}: {'suspended' if not out else 'kept'} (key, confirmed){': ' + out if out else ''}")
    if out.startswith(CONFIRM):
        return f"what Earmark isn't sure of changed: {out[len(CONFIRM):]}; press the key again"
    return out


def _set_state(session, pane_id, **fields):
    with store.locked():
        index = store.load_index()
        rec = session_state(index, session).get("suspended", {}).get(pane_id)
        if rec:
            for k, v in fields.items():
                if v is None:
                    rec.pop(k, None)  # None removes the field: absent and None never mean two things
                else:
                    rec[k] = v
            store.save_index(index)
        return dict(rec) if rec else None


def suspend_pane(session, pane_id, cfg, reason, manual, min_idle=0, accept=None):
    """Suspend one pane: look again, record it, keep its screen, stop the
    agent, and start the placeholder. Returns why it didn't, or "". The
    key's doubts (an unreadable prompt, options it can't bring back, ...)
    come back as CONFIRM + the doubt, unless `accept` is that same doubt (the
    user said `y` to it)."""
    t = time.time()
    try:
        snap = herdr.snapshot()
    except herdr.HerdrError as e:
        return str(e)
    p = snap["panes"].get(pane_id)
    if not p or not (p.get("agent_session") or {}).get("value"):
        return "there's no agent session in this pane"
    from . import core
    core.settle_now(session, snap, t)
    index = store.load_index()
    s = index.get("sessions", {}).get(session) or {}
    if pane_id in (s.get("suspended") or {}):
        return "it's already suspended"
    if not line_safe(session, pane_id):
        return "Earmark's own folders have a name the shell can't be given safely (a quote or a backslash)"
    note = (s.get("panes") or {}).get(pane_id) or {}
    timers = load_timers(session)
    timers["_away"] = s.get("away")
    found = look(p, note, procs.Table(), t, timers)
    save_timers(session, timers)
    if not manual and not any(x.get("focused") for x in snap["panes"].values()):
        return "Earmark can't tell which tab is in view"
    why = refusal(found, p, cfg, t, manual, None if manual else focused_tab_of(snap), note)
    if why:
        return why
    if not manual and t - found["activity"] < min_idle:
        return "it was active again"
    try:
        screen = screen_of(p)
    except herdr.HerdrError as e:
        return str(e)
    draft = agents.draft_text(screen, found["agent"])
    if draft:
        return "there's unsent text in its prompt"
    doubts = []
    if draft is None:
        doubts.append(UNREADABLE_PROMPT)
    if p.get("agent_status") not in ("idle", "done"):
        doubts.append(f"Herdr can't tell what it's doing (it's {p.get('agent_status') or 'unknown'})")
    doubts += cant_check(found)
    if doubts:
        if not manual:
            return doubts[0]
        if accept != "; ".join(doubts):
            return CONFIRM + "; ".join(doubts)
    mode_now = found.get("mode") or ""  # read over the whole transcript by look()
    argv = agents.live_resume_argv(found["agent"], found["session_id"], cfg["resume"],
                                   found.get("flags"), mode_now)
    ref = p["agent_session"]
    tab = snap["tabs"].get(p.get("tab_id")) or {}
    path = screen_path(session, pane_id)
    rec = {
        "pane_id": pane_id, "tab_id": p.get("tab_id"), "workspace_id": p.get("workspace_id"),
        "workspace_label": (snap["workspaces"].get(p.get("workspace_id")) or {}).get("label") or "",
        "tab_label": core._unmarked(tab.get("label"), p.get("tab_id"), s.get("marked")) or note.get("tab_label") or "",
        "tab_number": tab.get("number"),
        "pane_label": p.get("label") or "", "agent": found["agent"], "session_id": ref["value"],
        "source": ref.get("source"), "cwd": p.get("foreground_cwd") or p.get("cwd") or note.get("cwd"),
        "title": agents.clean_title(p.get("terminal_title"), found["agent"]) or note.get("title", ""),
        "config_dir": found.get("config_dir"), "account": found.get("account"), "resume": argv, "reason": reason,
        "state": "stopping", "at": t, "last_active": found["activity"], "screen": path,
        "unseen": p.get("agent_status") == "done",
    }
    # The record comes first: from here on the session can't be lost.
    with store.locked():
        index = store.load_index()
        s = session_state(index, session)
        if pane_id in s.setdefault("suspended", {}):
            return "it's already suspended"
        s["suspended"][pane_id] = rec
        store.save_index(index)
    signalled = []
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(screen)
    except OSError as e:  # nothing stopped yet: the record goes, the agent runs on
        with store.locked():
            index = store.load_index()
            session_state(index, session).get("suspended", {}).pop(pane_id, None)
            store.save_index(index)
        return f"Earmark couldn't keep a copy of its screen ({e.strerror or e})"

    def settle_mode():
        """The resume line follows the permission mode Claude was really
        in, read again now that it has exited (agents.mode_to_resume)."""
        if found["agent"] != "claude":
            return
        after = agents.claude_mode_since(transcript, size_before) if size_before is not None else None
        final = agents.mode_to_resume(after, mode_now, found.get("flags"), screen)
        if final != mode_now:
            argv_now = agents.live_resume_argv(found["agent"], found["session_id"], cfg["resume"],
                                               found.get("flags"), final)
            if argv_now:
                _set_state(session, pane_id, resume=argv_now)
                log(f"{session} {pane_id}: resumes in permission mode {final or 'as launched'} "
                    f"(read before the stop: {mode_now or 'as launched'})")

    def give_up(message, backoff=True):
        """Undo the record, unless the agent is gone already (it exited on
        its own, or the stop worked after all: then the session is
        suspended and the record stays) or was signalled (it may still be on
        its way out: the record stays "stopping", and a hook finishes it
        either way). Never dropped without a trace."""
        if procs.start_token(found["pid"]) is None:
            if not signalled:  # gone before Earmark stopped it: the user quit it (an exit, not a suspend)
                to_archive(session, pane_id, "exited")
                return "it exited on its own"
            settle_mode()
            _set_state(session, pane_id, state="suspended", at=time.time())
            started = arm(session, pane_id, view_ok=manual, just_stopped=True)
            return "" if started else f"{message}; it's suspended, without its placeholder"
        if signalled:
            _set_state(session, pane_id, state="stopping", at=time.time())
            if backoff:
                with store.locked():
                    index = store.load_index()
                    n = session_state(index, session).get("panes", {}).get(pane_id)
                    if n:
                        n["backoff_until"] = time.time() + BACKOFF
                        store.save_index(index)
            return f"{message}; Earmark finishes the suspend if it exits"
        with store.locked():
            index = store.load_index()
            s = session_state(index, session)
            s.get("suspended", {}).pop(pane_id, None)
            if backoff and pane_id in s.get("panes", {}):
                s["panes"][pane_id]["backoff_until"] = time.time() + BACKOFF
            store.save_index(index)
        drop_screen(rec)
        return message

    # The last look, right before the signal: the same processes, still not
    # in view, still idle.
    try:
        now = herdr.pane(pane_id)
        snap_now = herdr.snapshot() if not manual else None
    except herdr.HerdrError as e:
        return give_up(str(e), backoff=False)
    if now.get("agent_status") in ("working", "blocked"):
        return give_up("it got busy", backoff=False)
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None, p.get("tab_id"))
                       or not candidate_status(now.get("agent_status"), cfg)):
        return give_up("it came into view or got busy", backoff=False)
    try:  # anything typed meanwhile? (the screen was read a moment ago)
        draft = agents.draft_text(screen_of(now), found["agent"])
        if draft:
            return give_up("there's unsent text in its prompt", backoff=False)
        if draft is None and UNREADABLE_PROMPT not in doubts:  # readable a moment ago, so not a doubt the user took
            return give_up("Earmark can't read its prompt now to check for unsent text", backoff=False)
    except herdr.HerdrError as e:
        return give_up(str(e), backoff=False)
    # What runs under it, and Claude's own word, again (a command or a
    # Remote Control session may have started since the look)...
    busy = procs.Table().busy([found["pid"]])
    if busy:
        return give_up(f"a command started in it ({busy})", backoff=False)
    if found["agent"] == "claude":
        registry = agents.claude_registry(found["pid"], found.get("config_dir"))
        if registry.get("remote") or registry.get("status") not in (None, "idle"):
            return give_up("Claude says it's busy now", backoff=False)
    # ...and the start times last, right before the signal (an agent that
    # quit meanwhile is an exit, not a suspend).
    if any(procs.start_token(pid) != token for pid, token in found["tokens"].items()):
        return give_up("its process changed", backoff=False)
    # A hook may have ended this record meanwhile (a slow look under load):
    # no record, no signal.
    current = record(session, pane_id)
    if not current or current.get("state") != "stopping" or current.get("at") != t:
        drop_screen(rec)
        return "its record changed before the stop, so it was left alone"
    # Where the transcript ends before the stop: what Claude writes as it
    # exits (the permission mode in force) comes after it.
    transcript = (found.get("facts") or {}).get("source") if found["agent"] == "claude" else None
    try:
        size_before = os.path.getsize(transcript) if transcript else 0
    except OSError:
        size_before = None
    # SIGTERM to the agent and its launcher only: its own children (MCP
    # servers) are its to end; anything else in the group was refused above.
    try:
        for pid in found["chain"]:
            try:
                os.kill(pid, signal.SIGTERM)
                signalled.append(pid)
            except ProcessLookupError:
                pass
    except PermissionError as e:
        return give_up(f"Earmark may not stop it ({e})")
    try:
        deadline = time.time() + STOP_WAIT
        for _ in range(int(STOP_WAIT / 0.25) + 1):
            time.sleep(0.25)
            try:
                info = herdr.process_info(pane_id)
                back = bool(info) and info.get("foreground_process_group_id") == info.get("shell_pid")
            except herdr.HerdrError:
                back = False
            if back and procs.start_token(found["pid"]) is None:
                break
            if time.time() > deadline:
                return give_up(f"it didn't stop within {STOP_WAIT} seconds, so it was left running")
        else:
            return give_up(f"it didn't stop within {STOP_WAIT} seconds, so it was left running")
        settle_mode()
        # Herdr notices an agent is gone when the shell's prompt is back; a
        # command typed before then leaves Herdr listing the stopped agent
        # (and its restore relaunching it, or typing over Earmark's line).
        released = wait_released(pane_id, found["session_id"])
        _set_state(session, pane_id, state="suspended", at=time.time())
        if not released:
            _set_state(session, pane_id, herdr_listed=True)  # its restore may relaunch it after a restart
            log(f"{session} {pane_id}: Herdr still lists the stopped agent; placeholder left for later")
            mark_tab(session, pane_id, cfg["suspend"]["tab_mark"])
            return NOT_YET
        started = arm(session, pane_id, view_ok=manual, just_stopped=True)
        mark_tab(session, pane_id, cfg["suspend"]["tab_mark"])
        if not started:
            # The agent is stopped and its record kept, so nothing is lost: the
            # next check or the key starts the placeholder, and closing the
            # tab files the session in the archive.
            return "its placeholder didn't start"
    except Exception as e:  # after the signal nothing may lose the record
        log(f"{session} {pane_id}: after stopping: {e!r}")
        _set_state(session, pane_id, state="suspended", at=time.time())
        return f"something went wrong after stopping it ({e})"
    return ""


def wait_released(pane_id, session_id, timeout=RELEASE_WAIT):
    """Wait until Herdr no longer lists the stopped agent in the pane (a
    bounded number of looks, whatever the clock does)."""
    for _ in range(int(timeout / 0.25)):
        try:
            p = herdr.pane(pane_id)
        except herdr.HerdrError:
            return False
        if (p.get("agent_session") or {}).get("value") != session_id and not p.get("agent"):
            return True
        time.sleep(0.25)
    return False


def listed(p, rec):
    """Whether Herdr still lists the suspended session in its pane."""
    return (p.get("agent_session") or {}).get("value") == rec.get("session_id")


# ------------------------------------------------------------- tab marks

def mark_tab(session, pane_id, mark):
    """Put the sleep mark in front of a suspended pane's tab name (display
    only: Earmark strips it wherever it records a name). A tab without a
    name isn't marked (there'd be nothing to put back)."""
    if not mark:
        return
    try:
        tab_id = herdr.pane(pane_id).get("tab_id")
        label = (herdr.run("tab", "get", tab_id) or {}).get("tab", {}).get("label") or ""
        if tab_id and label and not label.startswith(mark + " "):
            with store.locked():  # listed first: only tabs Earmark marked are ever unmarked, and
                index = store.load_index()  # a hook between the two never records the mark
                session_state(index, session).setdefault("marked", {})[tab_id] = mark
                store.save_index(index)
            try:
                herdr.run("tab", "rename", tab_id, f"{mark} {label}")
            except herdr.HerdrError:
                with store.locked():
                    index = store.load_index()
                    session_state(index, session).setdefault("marked", {}).pop(tab_id, None)
                    store.save_index(index)
                raise
    except (herdr.HerdrError, AttributeError) as e:
        log(f"{session} {pane_id}: tab not marked: {e}")


def unmark_tab(tab_id, label, mark, session=None):
    """Take the mark off a tab name, if it's still there, and forget that
    Earmark marked it. A name that would start with "-" can't go on Herdr's
    command line (it reads its own flags anywhere in the argv), so that tab
    keeps its mark."""
    if mark and label.startswith(mark + " ") and tab_id:
        name = label[len(mark) + 1:]
        if name and herdr.safe_label(name):
            try:
                herdr.run("tab", "rename", tab_id, name)
            except herdr.HerdrError:
                return
    if session is not None:
        with store.locked():
            index = store.load_index()
            if session_state(index, session).get("marked", {}).pop(tab_id, None) is not None:
                store.save_index(index)


def stale_marks(snap, suspended, marked):
    """Tabs Earmark marked (`marked`: tab id -> mark) with no suspended pane
    left in them: [(tab id, label, mark)]. A tab the user named "💤 ..."
    themselves is never touched. Pure, for tests."""
    asleep = {(snap["panes"].get(pid) or rec).get("tab_id") for pid, rec in suspended.items()}
    out = []
    for tid, mark in (marked or {}).items():
        tab = snap["tabs"].get(tid)
        if tab is None or tid in asleep:
            continue
        label = tab.get("label") or ""
        if label.startswith(mark + " ") and not herdr.safe_label(label[len(mark) + 1:]):
            continue  # can't be put back on Herdr's command line: left as is
        out.append((tid, label, mark))
    return out


# ------------------------------------------------------------ placeholders

def is_placeholder(proc, session=None, pane_id=None):
    """Whether a process is an Earmark placeholder (for this session and
    pane, when given): python [options] .../earmark.py suspended <s> <p>
    [--state DIR] [--config DIR], exactly; an agent whose arguments merely
    contain that is not."""
    argv = proc.get("argv") if isinstance(proc, dict) else None
    if not isinstance(argv, list):
        return False
    for i, arg in enumerate(argv[:3]):
        if str(arg).endswith("earmark.py") and argv[i + 1:i + 2] == ["suspended"] and len(argv) >= i + 4:
            rest = argv[i + 4:]
            if len(rest) % 2 or any(opt not in ("--state", "--config") for opt in rest[::2]):
                return False
            return session is None or argv[i + 2:i + 4] == [session, pane_id]
    return False


def placeholder_pid(session, pane_id, info=None):
    """The pid of this pane's own placeholder, if it's the pane's foreground."""
    if info is None:
        try:
            info = herdr.process_info(pane_id)
        except herdr.HerdrError:
            return None
    return next((p.get("pid") for p in info.get("foreground_processes") or [] if is_placeholder(p, session, pane_id)),
                None) or None


def note_placeholder(session, pane_id, pid):
    """Remember a placeholder's pid and start time, so later checks can see
    it's still up from the process table, without asking Herdr."""
    token = procs.start_token(pid) if isinstance(pid, int) else None
    if token is not None:
        _set_state(session, pane_id, ph=[pid, token], base=None)  # a later loss starts a new baseline


def placeholder_alive(rec):
    ph = rec.get("ph") or []
    return len(ph) == 2 and ph[1] is not None and procs.start_token(ph[0]) == ph[1]


def at_bare_shell(info):
    return bool(info) and bool(info.get("shell_pid")) and \
        info.get("foreground_process_group_id") == info.get("shell_pid")


def bare_shell(info):
    """A shell Earmark can type its line into, waiting at its prompt: the
    pane's foreground is its own shell, and that's a shell Earmark knows (not
    a program exec'd in its place)."""
    if not at_bare_shell(info):
        return False
    me = next((x for x in info.get("foreground_processes") or [] if x.get("pid") == info["shell_pid"]), None)
    return me is None or (me.get("name") or "").lstrip("-") in SHELLS_OK


def arm(session, pane_id, restart=False, force=False, view_ok=False, just_stopped=False):
    """Start a suspended pane's placeholder: only into a bare shell in the
    record's own tab; never into the tab in view unless the user asked
    (`view_ok`: the key, or a suspend the key started); never while Herdr
    lists the session there (the key waits a moment for Herdr to let go);
    after a restart, not while Herdr's own restore may still relaunch it;
    only into a shell nobody has used since Earmark saw it back
    (`untouched`), unless the user asked or Earmark's own stop just brought
    it back (`just_stopped`); one arm at a time (a claim held under the
    lock), once per restart (`restart`), not again soon after one that
    didn't start (unless `force`). Returns True once it's seen running.
    What runs in the pane decides, not Herdr's agent state."""
    try:
        info = herdr.process_info(pane_id)
        pane = herdr.pane(pane_id)
        snap = herdr.snapshot() if not view_ok else None
    except herdr.HerdrError:
        return False
    rec = record(session, pane_id)
    if not rec:
        return False
    if (rec.get("tab_id") and pane.get("tab_id") and pane["tab_id"] != rec["tab_id"]) or \
            (snap is not None and not same_tab(session, rec, pane, snap)):
        # The pane id now belongs to another tab, or the tab is another one
        # with the same ids (a recreated session starts its ids again): this
        # record's tab is gone.
        to_archive(session, pane_id, "closed")
        log(f"{session} {pane_id}: its tab is gone; the session is in the archive")
        return False
    up = placeholder_pid(session, pane_id, info)
    if up:
        if restart:  # already up: this restart's work is done for it
            _set_state(session, pane_id, armed_by_rearm=True)
        note_placeholder(session, pane_id, up)
        return True
    if snap is not None and focused_tab_of(snap) == pane.get("tab_id"):
        return False  # the user may be typing there
    if listed(pane, rec):
        if not force or not wait_released(pane_id, rec.get("session_id")):
            return False
    if herdr_may_relaunch(session, pane_id, rec):
        return False  # every path: the key, a check's re-arm pass, the restart re-arm
    if not bare_shell(info):
        return False  # something else runs there: no claim, no write
    automatic = not (force or view_ok or just_stopped)
    if automatic and not untouched(session, pane_id, rec, pane, restart):
        return False
    t = time.time()
    with store.locked():
        index = store.load_index()
        rec = session_state(index, session).get("suspended", {}).get(pane_id)
        if not rec or rec.get("state") not in ("suspended", "waking"):
            return False
        if rec.get("arming", 0) > t - ARM_CLAIM:
            return False  # another arm is typing
        if restart and rec.get("armed_by_rearm"):
            return False
        if not force and not restart and rec.get("arm_failed", 0) > t - BACKOFF:
            return False
        rec["state"], rec["arming"] = "suspended", t
        if restart:
            rec["armed_by_rearm"] = True
        store.save_index(index)
        command = placeholder_command(session, pane_id, rec)
    try:  # the claim took a moment: look again before typing
        again = herdr.snapshot() if not view_ok else None
        if not bare_shell(herdr.process_info(pane_id)) or \
                (again is not None and focused_tab_of(again) == pane.get("tab_id")) or \
                (automatic and screen_print(dict(pane, pane_id=pane_id)) != (rec.get("base") or {}).get("screen")):
            _set_state(session, pane_id, arming=0)
            return False
    except herdr.HerdrError:
        _set_state(session, pane_id, arming=0)
        return False
    ok = False
    try:
        # Whatever sits unsent goes first, so nothing can run glued to the
        # placeholder: Ctrl+C cancels an unfinished command (a line ending in
        # a backslash, an open quote) in every shell Earmark types into; a
        # moment for the shell's new prompt; then Ctrl+E Ctrl+U clears the
        # line itself.
        herdr.run("pane", "send-keys", pane_id, "ctrl+c")
        time.sleep(0.3)
        herdr.run("pane", "send-keys", pane_id, "ctrl+e", "ctrl+u")  # to the line's end, then all of it
        herdr.run("pane", "run", pane_id, command)
        for _ in range(32):  # a shell just restored by Herdr can take a few seconds
            time.sleep(0.25)
            up = placeholder_pid(session, pane_id)
            if up:
                ok = True
                break
        if not ok:
            log(f"{session} {pane_id}: placeholder typed but not seen running")
    except herdr.HerdrError as e:
        log(f"{session} {pane_id}: placeholder not started: {e}")
    with store.locked():
        index = store.load_index()
        rec = session_state(index, session).get("suspended", {}).get(pane_id)
        if rec:
            rec["arming"] = 0
            if not ok:
                rec["arm_failed"] = time.time()
            else:
                rec.pop("arm_failed", None)
            store.save_index(index)
    if ok:
        note_placeholder(session, pane_id, up)
        _set_state(session, pane_id, shell_cwd=pane.get("cwd"))
    return ok


def same_tab(session, rec, pane, snap):
    """Whether the pane's tab is still the record's own: the same name (the
    sleep mark aside), number and workspace name as last seen (the record
    keeps them current: core.settle_suspended). What the record doesn't
    know isn't compared."""
    from . import core
    tab = snap["tabs"].get(pane.get("tab_id")) or {}
    ws = snap["workspaces"].get(pane.get("workspace_id")) or {}
    marked = (store.load_index().get("sessions", {}).get(session) or {}).get("marked") or {}
    if rec.get("tab_label") is not None and tab and \
            core._unmarked(tab.get("label"), pane.get("tab_id"), marked) != rec["tab_label"]:
        return False
    if rec.get("tab_number") is not None and tab.get("number") is not None and tab["number"] != rec["tab_number"]:
        return False
    if rec.get("workspace_label") and ws and (ws.get("label") or "") != rec["workspace_label"]:
        return False
    if rec.get("shell_cwd") and pane.get("cwd") and pane["cwd"] != rec["shell_cwd"]:
        return False  # a shell in another folder (Herdr restores a pane's folder)
    return True


def herdr_may_relaunch(session, pane_id, rec):
    """Right after a restart: Herdr listed the stopped session in this pane
    before it (the record says so: core.settle_suspended; or the pane's
    note, while it lasts) and the boot grace hasn't passed, so its own
    restore may be about to type the resume line."""
    from . import core
    s = store.load_index().get("sessions", {}).get(session) or {}
    if time.time() - s.get("boot", 0) >= core.grace(s):
        return False
    note = (s.get("panes") or {}).get(pane_id) or {}
    return bool(rec.get("herdr_listed")) or note.get("session_id") == rec.get("session_id")


def screen_of(pane):
    """A pane's screen from the bottom, whatever the user scrolled to."""
    return herdr.read_screen(pane["pane_id"], rows=(pane.get("scroll") or {}).get("viewport_rows"))


def screen_print(pane):
    """A fingerprint of what a pane shows, or None if Herdr didn't say."""
    try:
        text = screen_of(pane)
    except herdr.HerdrError:
        return None
    shown = "\n".join(line.rstrip() for line in text.rstrip().splitlines())
    return hashlib.sha256(shown.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def untouched(session, pane_id, rec, pane, restart):
    """Whether an automatic arm may type into this bare shell: what it shows
    the same at two looks at least STABLE seconds apart since Earmark first
    saw it back (Herdr's pane revision moves with the folder and the title,
    not with typing, so the screen decides). After a restart a change is the
    shell still starting, so it's watched again; otherwise someone used the
    shell, and it's left to the key until the placeholder is seen again or
    Herdr restarts."""
    base = rec.get("base") or {}
    if base.get("used"):
        return False
    shot = screen_print(dict(pane, pane_id=pane_id))
    if shot is None:
        return False  # can't tell: the key decides
    t = time.time()
    if base.get("screen") == shot:
        return t - base.get("at", t) >= STABLE
    _set_state(session, pane_id, base={"screen": shot, "at": t} if not base or restart else dict(base, used=True))
    return False


def waiting(rec):
    """A suspended record whose placeholder is missing and may still come
    back by itself (not one whose shell has been used since: the key's)."""
    return rec.get("state") == "suspended" and not placeholder_alive(rec) and \
        not (rec.get("base") or {}).get("used")


def resumed_by_herdr(rec, p, info):
    """What runs in a suspended pane: True when its own agent process runs
    with this session (Herdr's restore relaunched it, or the user did);
    "other" when that agent runs with another session (Claude's registry
    tells; the suspended one was left); False otherwise."""
    name = PROCESS_NAMES.get(rec.get("agent"), rec.get("agent"))
    procs_ = [x for x in info.get("foreground_processes") or [] if x.get("name") == name]
    if not procs_:
        return False
    if rec.get("agent") == "claude":
        registry = agents.claude_registry(procs_[0].get("pid"), rec.get("config_dir"))
        if registry.get("session_id"):
            return True if registry["session_id"] == rec.get("session_id") else "other"
    return True if listed(p, rec) else False


def drop_record(session, pane_id, why):
    """A suspended record whose session is live again (Herdr relaunched it)."""
    with store.locked():
        index = store.load_index()
        rec = session_state(index, session).get("suspended", {}).pop(pane_id, None)
        if rec:
            store.save_index(index)
    if rec:
        drop_screen(rec)
        log(f"{session} {pane_id}: no longer suspended: {why}")


def check_pane(session, pid, rec, p, skip_tab=None, restart=False):
    """Bring one suspended record in line with what runs in its pane: the
    agent relaunched by Herdr ends the record; a bare shell gets the
    placeholder. Returns True when the placeholder is up."""
    if not p or (skip_tab and p.get("tab_id") == skip_tab):
        return False
    try:
        info = herdr.process_info(pid)
    except herdr.HerdrError:
        return False
    state = resumed_by_herdr(rec, p, info)
    if state == "other":
        to_archive(session, pid, "replaced")
        log(f"{session} {pid}: another session runs there now; the suspended one is in the archive")
        return False
    if state:
        drop_record(session, pid, "Herdr resumed it")
        return False
    return arm(session, pid, restart=restart)


def rearm_pass(session, snap, skip_tab=None):
    """One pass over suspended records whose placeholder isn't running:
    start it where the pane is back at a bare shell. `skip_tab` (the tab in
    view) is left alone, so nothing is typed where the user may be typing."""
    s = store.load_index().get("sessions", {}).get(session) or {}
    for pid, rec in list((s.get("suspended") or {}).items()):
        if rec.get("state") not in ("suspended", "waking"):
            continue
        if rec.get("state") == "waking" and time.time() - (rec.get("waking_at") or 0) < RESUME_GRACE:
            continue  # being resumed right now
        if placeholder_alive(rec):
            continue  # still up (pid and start time): nothing to ask Herdr
        up = placeholder_pid(session, pid)
        if up:
            note_placeholder(session, pid, up)
            continue
        if check_pane(session, pid, rec, snap["panes"].get(pid), skip_tab=skip_tab):
            log(f"{session} {pid}: placeholder started again")


def rearm_all(session):
    """After a Herdr restart the placeholders are gone and their panes are
    plain shells: start them again as the panes come back (only into a bare
    shell, never into something the user started; not where Herdr still
    lists the session, since its own restore may be about to relaunch it)."""
    from . import core
    s = store.load_index().get("sessions", {}).get(session) or {}
    deadline = max(time.time() + REARM_WAIT, s.get("boot", 0) + core.grace(s) + 15)
    for _ in range(int(deadline - time.time()) + 30):  # bounded: a clock stepped back can't stretch it
        if time.time() >= deadline:
            break
        s = store.load_index().get("sessions", {}).get(session) or {}
        pending = [pid for pid, rec in (s.get("suspended") or {}).items()
                   if rec.get("state") in ("suspended", "waking") and not rec.get("armed_by_rearm")]
        if not pending:
            return
        try:
            snap = herdr.snapshot()
        except herdr.HerdrError:
            time.sleep(1)
            continue
        for pid in pending:
            if check_pane(session, pid, s["suspended"][pid], snap["panes"].get(pid), restart=True):
                log(f"{session} {pid}: placeholder back after a restart")
        time.sleep(1)


# ------------------------------------------------------- placeholder side

def _open_elsewhere(rec, pane_id, snap):
    """Whether the session runs anywhere but this pane: another pane of this
    Herdr session, or (for Claude Code) any process Claude's own registry
    lists, which covers other Herdr sessions and plain terminals."""
    if rec.get("agent") == "claude":  # Claude's own registry knows; Herdr's listing can be stale
        return agents.claude_running(rec["session_id"], rec.get("config_dir"))
    key = f"{rec['agent']}:{rec['session_id']}"
    for pid, p in snap["panes"].items():
        ref = p.get("agent_session") or {}
        if pid != pane_id and ref.get("value") and f"{ref.get('agent') or p.get('agent')}:{ref['value']}" == key:
            return True
    return False


def mark_waking(session, pane_id, fallback=None):
    """The placeholder is about to hand over to the resume command. Returns
    "" to go ahead, or why not: the session is open somewhere already
    (never resume it twice; the record goes to the archive, where a live
    session leaves it again), or Herdr can't be asked (NO_ANSWER: try
    again). A record that's gone meanwhile (`fallback` is the one the
    placeholder started with) doesn't strand the session."""
    snap = None
    for _ in range(3):
        try:
            snap = herdr.snapshot()
            break
        except herdr.HerdrError:
            time.sleep(0.5)
    if snap is None:
        return NO_ANSWER
    from . import core
    with store.locked():
        index, archive = store.load_index(), store.load_archive()
        s = session_state(index, session)
        rec = s.get("suspended", {}).get(pane_id)
        if not rec and not fallback:
            return "nothing is suspended here"
        if _open_elsewhere(rec or fallback, pane_id, snap):
            if rec:
                s["suspended"].pop(pane_id, None)
                core.archive_note(archive.setdefault("entries", {}), session, rec, time.time(), "exited")
                store.save_archive(archive)
                store.save_index(index)
                drop_screen(rec)
            return "this session is open somewhere else already, so it isn't resumed here"
        if rec:
            rec["state"], rec["waking_at"] = "waking", time.time()
            rec["herdr_listed"] = True  # the resumed agent: a restart now has Herdr relaunch it
            store.save_index(index)
        return ""


def to_archive(session, pane_id, reason):
    """Move a suspended session to the archive (the placeholder was left, or
    its resume failed). Returns True if there was one."""
    from . import core
    with store.locked():
        index, archive = store.load_index(), store.load_archive()
        s = session_state(index, session)
        rec = s.get("suspended", {}).pop(pane_id, None)
        if not rec:
            return False
        core.archive_note(archive.setdefault("entries", {}), session, rec, time.time(), reason)
        store.save_archive(archive)
        store.save_index(index)
    drop_screen(rec)
    return True


# ------------------------------------------------------------ hooks' side

def spawn_worker(args=()):
    """Start a worker in the background (its own session, so it outlives the
    hook or action that started it, never the job it was given). Returns
    whether it started."""
    path = os.path.join(store.state_dir(), "worker.log")
    try:
        if os.path.getsize(path) > 256 * 1024:
            os.replace(path, path + ".1")
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    except OSError:
        fd = subprocess.DEVNULL
    try:
        subprocess.Popen([sys.executable or "python3", os.path.join(ROOT, "earmark.py"), "worker", *args],
                         stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, start_new_session=True,
                         close_fds=True, cwd=ROOT)
        return True
    except OSError as e:
        print(f"earmark: worker didn't start: {e}", file=sys.stderr)
        return False
    finally:
        if fd != subprocess.DEVNULL:
            os.close(fd)


def press_enter(session, pane_id):
    """Press Enter in a suspended pane, only if its own placeholder is the
    pane's foreground process (never into an agent or a shell)."""
    try:
        if not placeholder_pid(session, pane_id):
            return False
        herdr.send_enter(pane_id)
        return True
    except herdr.HerdrError:
        return False


def key(session, pane_id):
    """The suspend key: Enter into the pane's placeholder when it's up;
    otherwise hand the pane to a worker (suspend it, or start its missing
    placeholder)."""
    if press_enter(session, pane_id):
        return
    spawn_worker(["--pane", pane_id, "--pressed", repr(time.time())])  # the press's own time, for the answer's lateness


def wake_on_view(session, pane_id):
    """Resume on view: if the pane is still in view after a moment, press
    Enter in its placeholder (a tab only passed through stays suspended)."""
    time.sleep(WAKE_DWELL)
    try:
        if not herdr.pane(pane_id).get("focused"):
            return
    except herdr.HerdrError:
        return
    with store.locked():
        index = store.load_index()
        rec = session_state(index, session).get("suspended", {}).get(pane_id)
        if not rec or rec.get("state") != "suspended" or time.time() - rec.get("enter_sent", 0) < 5:
            return
        rec["enter_sent"] = time.time()
        store.save_index(index)
    press_enter(session, pane_id)
