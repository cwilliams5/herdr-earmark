# Mutations (tests/mutate.py plants each one and runs the suite)

One-line regressions of Earmark's core behaviour. Each must make the unit
suite fail. Add one for every review finding fixed and every rule in
CLAUDE.md; when code moves, fix the pattern (a pattern that no longer
matches counts as a failure). Never plant one that could make the code
act on a real process (a `killpg`, say): the suite fakes `os.kill` only.
Format: `### name`, `file: path`, then an `old` and a `new` fenced block
holding the exact text.

### final focus/idle re-check
file: earmark/suspend.py
```old
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None, p.get("tab_id"))
                       or not candidate_status(now.get("agent_status"), cfg)):
```
```new
    if False:
```
### process identity re-check
file: earmark/suspend.py
```old
if any(procs.start_token(pid) != token for pid, token in found["tokens"].items()):
```
```new
if False:
```

### doubts ignored (unreadable prompt, unknown options)
file: earmark/suspend.py
```old
    if doubts:
        if not manual:
```
```new
    if False:
        if not manual:
```

### confirm window ignored
file: earmark/suspend.py
```old
    return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why
```
```new
    return bool(ask)
```
### in-view filter in auto()
file: earmark/suspend.py
```old
        if not candidate_status(p.get("agent_status"), cfg) or p.get("tab_id") == focused_tab \
```
```new
        if not candidate_status(p.get("agent_status"), cfg) or False \
```

### min_idle re-check
file: earmark/suspend.py
```old
    if not manual and t - found["activity"] < min_idle:
```
```new
    if False:
```

### unsent text refused
file: earmark/suspend.py
```old
    if draft:
        return "there's unsent text in its prompt"
```
```new
    if False:
        return "there's unsent text in its prompt"
```

### refusal: in view
file: earmark/suspend.py
```old
        if focused_tab and pane.get("tab_id") == focused_tab:
            return "it's in view"
```
```new
        if False:
            return "it's in view"
```

### refusal: busy
file: earmark/suspend.py
```old
    if found.get("busy"):
```
```new
    if False:
```

### refusal: Claude timers
file: earmark/suspend.py
```old
    if found.get("timers"):
```
```new
    if False:
```

### refusal: Remote Control
file: earmark/suspend.py
```old
    if registry.get("remote"):
```
```new
    if False:
```

### refusal: Claude's own status (shell)
file: earmark/suspend.py
```old
    if registry.get("status") not in (None, "idle"):
```
```new
    if registry.get("status") == "busy":
```

### refusal: unknown options in auto
file: earmark/suspend.py
```old
    if found.get("unknown_flags"):
        out.append(f"it was started
```
```new
    if False:
        out.append(f"it was started
```

### refusal: unseen setting
file: earmark/suspend.py
```old
        if status == "done" and not cfg["suspend"]["suspend_unseen"]:
```
```new
        if False:
```

### look: busy dropped
file: earmark/suspend.py
```old
    out["busy"] = table.busy([main["pid"]]) or (
```
```new
    out["busy"] = "" and (
```

### look: strangers in the group ignored
file: earmark/suspend.py
```old
    strangers = [x for x in running if x["pid"] not in mine]
```
```new
    strangers = []
```

### look: placeholder taken for the agent
file: earmark/suspend.py
```old
    if any(is_placeholder(x) for x in running):
```
```new
    if False:
```

### look: anything taken for the agent
file: earmark/suspend.py
```old
    if main is None:  # never stop something that isn't the agent
```
```new
    if False:
```

### look: shell check
file: earmark/suspend.py
```old
    if shell_name and shell_name not in SHELLS_OK:
```
```new
    if False:
```

### look: timer grace flipped
file: earmark/suspend.py
```old
        elif wake and wake + TIMER_GRACE + pushed_back(cache, timers.get("_away"), wake) > t:
```
```new
        elif wake and wake + TIMER_GRACE + pushed_back(cache, timers.get("_away"), wake) < t:
```
### look: scheduled tasks ignored
file: earmark/suspend.py
```old
        elif tasks:
```
```new
        elif False:
```

### look: activity as min
file: earmark/suspend.py
```old
    out["activity"] = max(activity)
```
```new
    out["activity"] = min(activity)
```

### look: transcript activity dropped
file: earmark/suspend.py
```old
        activity.append(agents.claude_activity(path) or 0)
```
```new
        activity.append(0)
```

### look: registry dropped
file: earmark/suspend.py
```old
        out["registry"] = agents.claude_registry(main["pid"], config_dir)
```
```new
        out["registry"] = {}
```

### look: CLAUDE_CONFIG_DIR not read
file: earmark/suspend.py
```old
        config_dir = procs.environ_var(main["pid"], "CLAUDE_CONFIG_DIR")  # None: unreadable, so unknown
```
```new
        config_dir = ""
```
### procs: plain shells not work
file: earmark/procs.py
```old
                if name.lstrip("-") in SHELLS or "shell-snapshots" in cmd:
```
```new
                if "shell-snapshots" in cmd:
```

### count mode keeps one too many
file: earmark/suspend.py
```old
        keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"]]}
```
```new
        keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"] + 1]}
```

### count mode with turned-down looks
file: earmark/suspend.py
```old
item[2].get("activity", t)
```
```new
item[2]["activity"]
```

### memory mode looks when it can't act
file: earmark/suspend.py
```old
    if mode == "memory" and (available is None or available >= cfg["suspend"]["memory_below"]):
        return  # nothing to do
```
```new
    if False:
        return  # nothing to do
```

### stop waits for the shell
file: earmark/suspend.py
```old
            if back and procs.start_token(found["pid"]) is None:
```
```new
            if procs.start_token(found["pid"]) is None:
```

### stop waits for the agent
file: earmark/suspend.py
```old
            if back and procs.start_token(found["pid"]) is None:
```
```new
            if back:
```

### give_up keeps a dead agent's record
file: earmark/suspend.py
```old
            _set_state(session, pane_id, state="suspended", at=time.time())
            started = arm(session, pane_id, view_ok=manual, just_stopped=True)
            return "" if started else f"{message}; it's suspended, without its placeholder"
```
```new
            return message
```
### wait for Herdr to let go
file: earmark/suspend.py
```old
        released = wait_released(pane_id, found["session_id"])
```
```new
        released = True
```

### Herdr lets go: agent half
file: earmark/suspend.py
```old
        if (p.get("agent_session") or {}).get("value") != session_id and not p.get("agent"):
```
```new
        if (p.get("agent_session") or {}).get("value") != session_id:
```

### Herdr lets go: session half
file: earmark/suspend.py
```old
        if (p.get("agent_session") or {}).get("value") != session_id and not p.get("agent"):
```
```new
        if not p.get("agent"):
```

### bare-shell check before typing
file: earmark/suspend.py
```old
        if not bare_shell(herdr.process_info(pane_id)) or \
```
```new
        if False or \
```
### bare-shell check before the claim
file: earmark/suspend.py
```old
    if not bare_shell(info):
        return False  # something else runs there: no claim, no write
```
```new
    pass
```
### arm: one at a time
file: earmark/suspend.py
```old
        if rec.get("arming", 0) > t - ARM_CLAIM:
```
```new
        if False:
```

### arm: once per restart
file: earmark/suspend.py
```old
        if restart and rec.get("armed_by_rearm"):
```
```new
        if False:
```

### arm: wait while Herdr lists it
file: earmark/suspend.py
```old
    if listed(pane, rec):
        if not force or not wait_released(pane_id, rec.get("session_id")):
            return False
```
```new
    if False:
        if not force or not wait_released(pane_id, rec.get("session_id")):
            return False
```
### arm: backoff after a failed start
file: earmark/suspend.py
```old
        if not force and not restart and rec.get("arm_failed", 0) > t - BACKOFF:
```
```new
        if False:
```
### arm: failure remembered
file: earmark/suspend.py
```old
            if not ok:
                rec["arm_failed"] = time.time()
```
```new
            if False:
                rec["arm_failed"] = time.time()
```

### line cleared before typing
file: earmark/suspend.py
```old
        herdr.run("pane", "send-keys", pane_id, "ctrl+e", "ctrl+u")  # to the line's end, then all of it
```
```new
        pass
```
### state folders on the line
file: earmark/suspend.py
```old
"--state", store.state_dir(), "--config", config.config_dir()])
```
```new
])
```

### rearm skips the tab in view
file: earmark/suspend.py
```old
    if not p or (skip_tab and p.get("tab_id") == skip_tab):
```
```new
    if not p:
```

### rearm leaves a resume in progress
file: earmark/suspend.py
```old
        if rec.get("state") == "waking" and time.time() - (rec.get("waking_at") or 0) < RESUME_GRACE:
            continue  # being resumed right now
```
```new
        if False:
            continue  # being resumed right now
```

### Herdr relaunch ends the record
file: earmark/suspend.py
```old
    state = resumed_by_herdr(rec, p, info)
    if state == "other":
```
```new
    state = False
    if state == "other":
```
### placeholder recognized exactly
file: earmark/suspend.py
```old
    for i, arg in enumerate(argv[:3]):
```
```new
    for i, arg in enumerate(argv):
```

### Enter only into the placeholder
file: earmark/suspend.py
```old
        if not placeholder_pid(session, pane_id):
            return False
        herdr.send_enter(pane_id)
```
```new
        if False:
            return False
        herdr.send_enter(pane_id)
```

### view resume needs the pane in view
file: earmark/suspend.py
```old
        if not herdr.pane(pane_id).get("focused"):
```
```new
        if False:
```

### open in a plain terminal
file: earmark/suspend.py
```old
        return agents.claude_running(rec["session_id"], rec.get("config_dir"))
```
```new
        return False
```

### no answer is no resume
file: earmark/suspend.py
```old
    if snap is None:
        return NO_ANSWER
```
```new
    if snap is None:
        snap = {"panes": {}}
```

### a vanished record doesn't strand
file: earmark/suspend.py
```old
        if not rec and not fallback:
```
```new
        if not rec:
```

### open elsewhere archived, not dropped
file: earmark/suspend.py
```old
                core.archive_note(archive.setdefault("entries", {}), session, rec, time.time(), "exited")

```
```new

```

### registry start-time check
file: earmark/agents.py
```old
        if isinstance(recorded, (int, float)) and started is not None and abs(started - recorded / 1000) > 30:
```
```new
        if False:
```

### Ctrl+C resumes
file: earmark/placeholder.py
```old
    if CTRL_C.search(data):
        return "leave"
```
```new
    if CTRL_C.search(data):
        return "resume"
```

### hangup resumes nothing
file: earmark/placeholder.py
```old
    if action == "hangup":
        return 1
```
```new
    if action == "hangup":
        return 0
```

### refusal resumes nothing
file: earmark/placeholder.py
```old
        print(f"Earmark: {why}.")
        return 1
```
```new
        print(f"Earmark: {why}.")
        return 0
```

### placeholder retries when Herdr didn't answer
file: earmark/placeholder.py
```old
            if why != suspend.NO_ANSWER:
                break
```
```new
            break
```

### suspend's stop isn't an exit
file: earmark/core.py
```old
            if own_stop:
                s["panes"].pop(pid)
```
```new
            if False:
                s["panes"].pop(pid)
```

### another session's exit
file: earmark/core.py
```old
            own_stop = rec.get("session_id") == note.get("session_id") and (
```
```new
            own_stop = True and (
```

### a user's exit over a stale record
file: earmark/core.py
```old
            elif pid in suspended and released:
```
```new
            elif False:
```

### another session in its pane archived
file: earmark/core.py
```old
        elif other:  # something else runs in its pane now
```
```new
        elif False:  # something else runs in its pane now
```

### stale view keeps a suspended record
file: earmark/core.py
```old
            if state != "waking" and not stop_failed:
```
```new
            if state != "waking" and t - since < suspend.STOP_STALE:
```

### a stalled stop finished
file: earmark/core.py
```old
        elif state == "stopping" and pid in snap["panes"] and t - since > suspend.STOP_STALE:
```
```new
        elif False:
```

### boot grace for missing panes
file: earmark/core.py
```old
            if flags is not None and t - flags.get("boot", 0) < grace(flags) \
```
```new
            if False \
```
### forgotten session archives its tabs
file: earmark/core.py
```old
            changed |= archive_note(entries, other, dict(rec), t, "closed")
```
```new
            pass
```

### one rearm per server
file: earmark/core.py
```old
        if suspended and (server_pid is None or s.get("rearm_pid") != server_pid):
```
```new
        if suspended:
```

### mark never recorded
file: earmark/core.py
```old
"tab_label": _unmarked(tab.get("label"), p.get("tab_id"), marked),
```
```new
"tab_label": tab.get("label") or "",
```
### reopen keeps the Claude folder
file: earmark/core.py
```old
        herdr.run_in_pane(pane_id, argv, agents.env_prefix(entry["agent"], entry.get("config_dir")))
```
```new
        herdr.run_in_pane(pane_id, argv)
```

### checks at most once a minute
file: earmark/core.py
```old
            due = checks_run and t - s.get("suspend_checked", 0) >= suspend.CHECK_EVERY
```
```new
            due = checks_run
```

### resume on view only when asked
file: earmark/core.py
```old
            if event == "pane.focused" and scfg["resume_on"] == "view":
```
```new
            if event == "pane.focused":
```

### failed worker start keeps the restart
file: earmark/core.py
```old
        if worker_args is not None and not suspend.spawn_worker(worker_args) and "--rearm" in worker_args:
```
```new
        if worker_args is not None and suspend.spawn_worker(worker_args) and False:
```

### default mode after bypass
file: earmark/agents.py
```old
    if mode != "default":
        out += ["--permission-mode", mode]
```
```new
    out += ["--permission-mode", mode]
```

### resume gets its Claude folder
file: earmark/agents.py
```old
    return "CLAUDE_CONFIG_DIR=" + shlex.quote(config_dir) + " "
```
```new
    return ""
```

### dropped options dropped
file: earmark/agents.py
```old
        if keep:

```
```new
        if True:

```
### box needs the prompt
file: earmark/agents.py
```old
        if any(plain(line).lstrip().startswith(("❯", ">")) for line in lines[top + 1:bottom]):
```
```new
        if True:
```

### one-shot tasks expire
file: earmark/agents.py
```old
    return sum(1 for c in cache["created"].values() if c.get("recurring") or c.get("stamp", 0) > one_shot_after)
```
```new
    return len(cache["created"])
```
### a dash name never reaches Herdr
file: earmark/suspend.py
```old
        if name and herdr.safe_label(name):
```
```new
        if name:
```
### an unnamed tab isn't marked
file: earmark/suspend.py
```old
        if tab_id and label and not label.startswith(mark + " "):
```
```new
        if tab_id and not label.startswith(mark + " "):
```

### keys typed during start-up kept
file: earmark/placeholder.py
```old
        tty.setraw(self.fd, termios.TCSANOW)
```
```new
        tty.setraw(self.fd)
```

### boot grace only for tabs not seen since
file: earmark/core.py
```old
                    and rec.get("seen_at", 0) < flags.get("boot", 0):
```
```new
                    and True:
```

<!-- Strict review 2: the reviewers' own mutations (safety, then fit), kept so every later round re-runs them. -->

### r2-safety: A boot grace release
file: earmark/core.py
```old
    return pid in s.get("boot_panes", []) and t - s.get("boot", 0) < grace(s)
```
```new
    return False
```
### r2-safety: A rename carries archive
file: earmark/core.py
```old
                    e["workspace_label"] = new
                    changed = True
```
```new
                    changed = True
```

### r2-safety: A restart via new server pid
file: earmark/core.py
```old
        else:
            restarted = True
```
```new
        else:
            restarted = False
```
### r2-safety: A live again leaves archive
file: earmark/core.py
```old
    for key in [k for k, e in entries.items() if f"{e['agent']}:{e['session_id']}" in live]:
```
```new
    for key in []:
```

### r2-safety: A replaced session archived
file: earmark/core.py
```old
                changed |= archive_note(entries, session, current(note), t, "replaced")
                note = None
```
```new
                note = None
```

### r2-safety: A archive_note unsafe id
file: earmark/core.py
```old
    if not agents.safe_session_id(note.get("session_id")):
        return False
    facts
```
```new
    facts
```

### r2-safety: A closed workspace recorded
file: earmark/core.py
```old
            else:
                changed |= record_closed_workspace(archive, session, wid, layout, t)
```
```new
            else:
                pass
```
### r2-safety: A restore skips live
file: earmark/core.py
```old
    tabs = [tb for tb in tabs if not (tb.get("session_id") and f"{tb.get('agent')}:{tb['session_id']}" in live)]
```
```new
    tabs = list(tabs)
```

### r2-safety: A layout remembers suspended
file: earmark/core.py
```old
        return {"agent": rec.get("agent"), "value": rec.get("session_id")} if rec else {}
```
```new
        return {}
```

### r2-safety: A prune needs content
file: earmark/core.py
```old
                if not (facts["exists"] and facts["has_content"]):
                    del entries[key]
```
```new
                if not facts["exists"]:
                    del entries[key]
```

### r2-safety: A status_at only on change
file: earmark/core.py
```old
            if idle_clock and new.get("status") != p.get("agent_status"):
```
```new
            if idle_clock:
```

### r2-safety: A tab name kept across list race
file: earmark/core.py
```old
                tab = {"label": note.get("tab_label"), "number": note.get("tab_number")}
```
```new
                tab = {}
```

### r2-safety: S refusal working
file: earmark/suspend.py
```old
    if status == "working":
        return "it's working"
```
```new
    if False:
        return "it's working"
```

### r2-safety: S refusal blocked
file: earmark/suspend.py
```old
    if status == "blocked":
```
```new
    if False:
```

### r2-safety: S refusal auto not idle
file: earmark/suspend.py
```old
        if status not in ("idle", "done"):
```
```new
        if False:
```

### r2-safety: S refusal nothing saved
file: earmark/suspend.py
```old
    if facts.get("known") and not (facts.get("exists") and facts.get("has_content")):
```
```new
    if False:
```

### r2-safety: S refusal backoff
file: earmark/suspend.py
```old
        if (note or {}).get("backoff_until", 0) > t:
```
```new
        if False:
```

### r2-safety: S refusal registry busy only shell
file: earmark/suspend.py
```old
    if registry.get("status") not in (None, "idle"):
```
```new
    if registry.get("status") == "shell":
```

### r2-safety: S refusal no resume argv
file: earmark/suspend.py
```old
    if not agents.resume_argv(agent, sid, cfg["resume"]):
```
```new
    if False:
```

### r2-safety: S already-suspended recheck under lock
file: earmark/suspend.py
```old
        if pane_id in s.setdefault("suspended", {}):
            return "it's already suspended"
        s["suspended"][pane_id] = rec
```
```new
        s.setdefault("suspended", {})[pane_id] = rec
```

### r2-safety: S auto refusal sees focus
file: earmark/suspend.py
```old
None if manual else focused_tab_of(snap), note)
```
```new
None, note)
```

### r2-safety: S suspended state before arm
file: earmark/suspend.py
```old
        released = wait_released(pane_id, found["session_id"])
        _set_state(session, pane_id, state="suspended", at=time.time())
```
```new
        released = wait_released(pane_id, found["session_id"])
```

### r2-safety: S give_up backoff
file: earmark/suspend.py
```old
            if backoff and pane_id in s.get("panes", {}):
```
```new
            if False:
```

### r2-safety: S chain stops at the group
file: earmark/suspend.py
```old
        if parent not in group or parent in chain:
```
```new
        if parent is None or parent in chain:
```

### r2-safety: S auto mode change stops
file: earmark/suspend.py
```old
            if cfg.get("_broken") or cfg["suspend"]["when"] != mode:
```
```new
            if cfg.get("_broken"):
```
### r2-safety: S choose applies refusal
file: earmark/suspend.py
```old
    ok = [(p, n, f) for p, n, f in looks if f is not None and not refusal(f, p, cfg, t, False, None, n)]
```
```new
    ok = [(p, n, f) for p, n, f in looks if f is not None]
```

### r2-safety: S memory hysteresis margin
file: earmark/suspend.py
```old
            if len(chosen) >= MAX_PER_CHECK or available + freed >= scfg["memory_below"] + MEMORY_MARGIN:
```
```new
            if len(chosen) >= MAX_PER_CHECK or available + freed >= scfg["memory_below"]:
```

### r2-safety: S memory max per check
file: earmark/suspend.py
```old
            if len(chosen) >= MAX_PER_CHECK or available
```
```new
            if False or available
```

### r2-safety: S key returns after Enter
file: earmark/suspend.py
```old
    if press_enter(session, pane_id):
        return
    spawn_worker
```
```new
    press_enter(session, pane_id)
    spawn_worker
```

### r2-safety: S view resume only suspended state
file: earmark/suspend.py
```old
        if not rec or rec.get("state") != "suspended" or time.time() - rec.get("enter_sent", 0) < 5:
```
```new
        if not rec:
```

### r2-safety: S hook wake only for suspended
file: earmark/core.py
```old
                wake = data.get("pane_id") if rec and rec.get("state") == "suspended" else None
```
```new
                wake = data.get("pane_id") if rec else None
```

### r2-safety: S manual rearm only for suspended
file: earmark/suspend.py
```old
    rec = record(session, pane_id)
    if rec and rec.get("state") == "suspended":
```
```new
    rec = record(session, pane_id)
    if rec:
```

### r2-safety: S arm only suspended/waking records
file: earmark/suspend.py
```old
        if not rec or rec.get("state") not in ("suspended", "waking"):
            return False
        if rec.get("arming"
```
```new
        if not rec:
            return False
        if rec.get("arming"
```

### r2-safety: S rearm_all once per restart
file: earmark/suspend.py
```old
            if check_pane(session, pid, s["suspended"][pid], snap["panes"].get(pid), restart=True):
```
```new
            if check_pane(session, pid, s["suspended"][pid], snap["panes"].get(pid), restart=False):
```

### r2-safety: S resumed_by_herdr needs the process
file: earmark/suspend.py
```old
    if not procs_:
        return False
```
```new
    if False:
        return False
```
### r2-safety: S stale marks only without suspended
file: earmark/suspend.py
```old
        if tab is None or tid in asleep:
```
```new
        if tab is None:
```
### r2-safety: S mark_waking sets waking
file: earmark/suspend.py
```old
            rec["state"], rec["waking_at"] = "waking", time.time()
            rec["herdr_listed"] = True
```
```new
            rec["herdr_listed"] = True
```

### r2-safety: S mark_waking fail-open
file: earmark/suspend.py
```old
    if snap is None:
        return NO_ANSWER
```
```new
    if snap is None:
        return ""
```

### r2-safety: S to_archive archives
file: earmark/suspend.py
```old
        core.archive_note(archive.setdefault("entries", {}), session, rec, time.time(), reason)
        store.save_archive(archive)
        store.save_index(index)
    drop_screen(rec)
    return True
```
```new
        store.save_index(index)
    drop_screen(rec)
    return True
```

### r2-safety: S open elsewhere other panes
file: earmark/suspend.py
```old
        if pid != pane_id and ref.get("value") and f"{ref.get('agent') or p.get('agent')}:{ref['value']}" == key:
```
```new
        if False:
```

### r2-safety: C settle open elsewhere
file: earmark/core.py
```old
        if panes - {pid} and runs_elsewhere():
```
```new
        if False:
```
### r2-safety: C settle waking expiry archived
file: earmark/core.py
```old
            changed |= archive_note(entries, session, current(dict(rec)), t, "exited")
            del suspended[pid]
        else:
```
```new
            del suspended[pid]
        else:
```

### r2-safety: C settle closed archived
file: earmark/core.py
```old
            changed |= archive_note(entries, session, current(dict(rec)), t, "closed")
            del suspended[pid]
        elif state == "waking"
```
```new
            del suspended[pid]
        elif state == "waking"
```

### r2-safety: C settle stop_failed needs staleness
file: earmark/core.py
```old
            stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE
```
```new
            stop_failed = state == "stopping" and here.get("agent")
```

### r2-safety: G timers since process start
file: earmark/agents.py
```old
        if record.get("type") != "assistant" or stamp is None or stamp < since:
```
```new
        if record.get("type") != "assistant" or stamp is None:
```

### r2-safety: G cron delete
file: earmark/agents.py
```old
                if match:
                    del created[match]
```
```new
                if False:
                    del created[match]
```
### r2-safety: G unknown flags kept silently
file: earmark/agents.py
```old
            unknown.append(arg)
```
```new
            kept.append(arg)
```

### r2-safety: G env_prefix unsafe chars
file: earmark/agents.py
```old
or not os.path.isabs(config_dir) or UNTYPABLE.search(config_dir):
```
```new
or not os.path.isabs(config_dir):
```
### r2-safety: G registry dead pid
file: earmark/agents.py
```old
        except ProcessLookupError:
            continue
        except PermissionError:
```
```new
        except ProcessLookupError:
            pass
        except PermissionError:
```

### r2-safety: G safe id backslash
file: earmark/agents.py
```old
_SAFE_ID = re.compile(r"[^\s'\\-][^'\\\x00-\x1f\x7f]{0,511}")
```
```new
_SAFE_ID = re.compile(r"[^\s'\\-][^'\x00-\x1f\x7f]{0,511}")
```

### r2-safety: G draft box last pair
file: earmark/agents.py
```old
    for top, bottom in reversed(list(zip(rules, rules[1:]))):
```
```new
    for top, bottom in list(zip(rules, rules[1:])):
```

### r2-safety: G draft hint reset by 0
file: earmark/agents.py
```old
        if n in (0, 22, 23):
```
```new
        if n in (22, 23):
```
### r2-safety: P busy only direct children
file: earmark/procs.py
```old
            for p in self.descendants(root):
```
```new
            for p in self.kids.get(root, []):
```

### r2-safety: P start token field
file: earmark/procs.py
```old
            return stat[stat.rfind(")") + 2:].split()[19]
```
```new
            return stat[stat.rfind(")") + 2:].split()[18]
```

### r2-safety: P ppid parse
file: earmark/procs.py
```old
                procs[int(d)] = (int(rest[1]), name, cmd)
```
```new
                procs[int(d)] = (int(rest[2]), name, cmd)
```

### r2-safety: P resume cd kept
file: earmark/suspend.py
```old
    if shell_safe(rec.get("cwd")):
```
```new
    if False:
```

### r2-safety: P shell_safe backslash
file: earmark/agents.py
```old
UNTYPABLE = re.compile(r"['\\\x00-\x1f\x7f]")
```
```new
UNTYPABLE = re.compile(r"['\x00-\x1f\x7f]")
```
### r2-safety: PH Ctrl+C before Enter
file: earmark/placeholder.py
```old
    if CTRL_C.search(data):
        return "leave"
    if ENTER.search(data):
        return "resume"
```
```new
    if ENTER.search(data):
        return "resume"
    if CTRL_C.search(data):
        return "leave"
```

### r2-safety: PH leave archives
file: earmark/placeholder.py
```old
        if suspend.to_archive(session, pane_id, "exited"):
```
```new
        if False:
```

### r2-fit: SIGKILL instead of SIGTERM
file: earmark/suspend.py
```old
os.kill(pid, signal.SIGTERM)
```
```new
os.kill(pid, signal.SIGKILL)
```

### r2-fit: unknown status taken by automatic modes
file: earmark/suspend.py
```old
if status not in ("idle", "done"):
```
```new
if status not in ("idle", "done", "unknown", None):
```

### r2-fit: mode switched off mid-check ignored
file: earmark/suspend.py
```old
        if _mtime(config.config_path()) != settings_seen:
```
```new
        if False:
```

### r2-fit: unseen flag never recorded
file: earmark/suspend.py
```old
"unseen": p.get("agent_status") == "done",
```
```new
"unseen": False,
```

### r2-fit: resume folder: shell cwd, not the agent's
file: earmark/suspend.py
```old
"cwd": p.get("foreground_cwd") or p.get("cwd") or note.get("cwd"),
```
```new
"cwd": p.get("cwd") or note.get("cwd"),
```

### r2-fit: record keeps the mark in tab_label
file: earmark/suspend.py
```old
"tab_label": core._unmarked(tab.get("label"), p.get("tab_id"), s.get("marked")) or note.get("tab_label") or "",
```
```new
"tab_label": tab.get("label") or note.get("tab_label") or "",
```
### r2-fit: mark doubled
file: earmark/suspend.py
```old
if tab_id and label and not label.startswith(mark + " "):
```
```new
if tab_id and label:
```

### r2-fit: unknown agent with no resume command suspended
file: earmark/suspend.py
```old
    if not agents.resume_argv(agent, sid, cfg["resume"]):
        return f"Earmark doesn't know how to resume {agent} sessions"
```
```new
    if False:
        return f"Earmark doesn't know how to resume {agent} sessions"
```

### r2-fit: memory mode: MAX_PER_CHECK ignored
file: earmark/suspend.py
```old
if len(chosen) >= MAX_PER_CHECK or available + freed
```
```new
if available + freed
```

### r2-fit: memory mode: margin ignored (stops at the line)
file: earmark/suspend.py
```old
available + freed >= scfg["memory_below"] + MEMORY_MARGIN:
```
```new
available + freed >= scfg["memory_below"]:
```

### r2-fit: view resume never throttled
file: earmark/suspend.py
```old
time.time() - rec.get("enter_sent", 0) < 5
```
```new
False
```

### r2-fit: confirm: any earlier doubt confirms a different one
file: earmark/suspend.py
```old
    return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why
```
```new
    return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN
```
### r2-fit: auto: suspended panes looked at again
file: earmark/suspend.py
```old
if not (p.get("agent_session") or {}).get("value") or pid in suspended:
```
```new
if not (p.get("agent_session") or {}).get("value"):
```

### r2-fit: refusal: backoff ignored
file: earmark/suspend.py
```old
        if (note or {}).get("backoff_until", 0) > t:
            return "a recent try to suspend it failed"
```
```new
        if False:
            return "a recent try to suspend it failed"
```

### r2-fit: arm: waking reset to suspended kept
file: earmark/suspend.py
```old
if not rec or rec.get("state") not in ("suspended", "waking"):
```
```new
if not rec:
```

### r2-fit: rearm_all stops after first pass
file: earmark/suspend.py
```old
                log(f"{session} {pid}: placeholder back after a restart")
        time.sleep(1)
```
```new
                log(f"{session} {pid}: placeholder back after a restart")
        return
```

### r2-fit: terminal left raw after the placeholder
file: earmark/placeholder.py
```old
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
```
```new
        pass
```

### r2-fit: alternate screen never left
file: earmark/placeholder.py
```old
LEAVE_SCREEN = "\x1b[?2004l\x1b[0m\x1b[?25h\x1b[?1049l"
```
```new
LEAVE_SCREEN = ""
```

### r2-fit: agent's terminal modes not reset
file: earmark/placeholder.py
```old
RESET_MODES = ("\x1b[?1000l
```
```new
RESET_MODES = "" and ("\x1b[?1000l
```

### r2-fit: placeholder wakes every second (R18 back)
file: earmark/placeholder.py
```old
60.5 - time.time() % 60
```
```new
1
```

### r2-fit: EOF busy-loops instead of exiting
file: earmark/placeholder.py
```old
            if not data:
                return "hangup"
```
```new
            if False:
                return "hangup"
```

### r2-fit: frozen view anchored at the top (bottom cut)
file: earmark/placeholder.py
```old
for line in lines][-room:] if room else []
```
```new
for line in lines][:room] if room else []
```

### r2-fit: frozen view not dimmed after a reset
file: earmark/placeholder.py
```old
return DIM + line.replace("\x1b[0m", "\x1b[0m" + DIM)
```
```new
return DIM + line.replace("\x1b[0m", "\x1b[0m")
```

### r2-fit: title OSC not cleared on exit
file: earmark/placeholder.py
```old
    sys.stdout.write("\x1b]2;\x07")
    if action == "hangup":
```
```new
    if action == "hangup":
```

### r2-fit: tab never unmarked on resume
file: earmark/placeholder.py
```old
    unmark(session, pane_id)
    if action == "leave":
```
```new
    if action == "leave":
```
### r2-fit: other Herdr sessions forgotten at once
file: earmark/core.py
```old
if k != session and t - v.get("seen", t) > FORGET_SESSION_DAYS * 86400]
```
```new
if k != session and t - v.get("seen", t) > 0]
```

### r2-fit: seen never refreshed
file: earmark/core.py
```old
    if t - s.get("seen", 0) > 600:
```
```new
    if not s.get("seen"):
```

### r2-fit: config_dir never kept in notes
file: earmark/core.py
```old
            if p.get("_config_dir") is not None:
                new["config_dir"]
```
```new
            if False:
                new["config_dir"]
```

### r2-fit: reopen: same id, other name taken
file: earmark/core.py
```old
if w and (w.get("label") or "") == entry["workspace_label"]:
```
```new
if w:
```

### r2-fit: sidebar tokens resent on every hook
file: earmark/core.py
```old
        if sent.get(wid) != text:
```
```new
        if True:
```

### r2-fit: index rewritten on every hook (R23)
file: earmark/core.py
```old
        if json.dumps(index, sort_keys=True) != before:
            store.save_index(index)
```
```new
        if True:
            store.save_index(index)
```

### r2-fit: restart resets reported tokens never
file: earmark/core.py
```old
        s["reported"] = {wid: "" for wid in snap["workspaces"]}
```
```new
        pass
```
### r2-fit: closed workspace keeps no record when its tabs were plain
file: earmark/core.py
```old
    if not layout.get("tabs"):
        return False
```
```new
    if not any(tb.get("session_id") for tb in layout.get("tabs") or []):
        return False
```

### r2-fit: prune: closed workspaces never age out
file: earmark/core.py
```old
        if days and t - closed[key].get("closed_at", t) > days * 86400:
```
```new
        if False:
```

### r2-fit: prune: cache trusted for unknown agents too
file: earmark/core.py
```old
            facts = {"known": True}  # same file
```
```new
            facts = {"known": False}  # same file
```

### r2-fit: waking without session: grace ignored
file: earmark/core.py
```old
        elif state == "waking" and t - since > suspend.RESUME_GRACE:
```
```new
        elif state == "waking":
```

### r2-fit: focused_pane never remembered
file: earmark/core.py
```old
    s["focused_tab"] = tab_now
```
```new
    s["focused_tab"] = None
```
### r2-fit: hook: memory mode can_act ignored
file: earmark/core.py
```old
                can_act = available is not None and available < scfg["memory_below"]
```
```new
                can_act = True
```
### r2-fit: timer cache kept across a restart of the agent
file: earmark/agents.py
```old
    if cache.get("path") != path or cache.get("since") != since or cache.get("v") != 2:
```
```new
    if cache.get("path") != path or cache.get("v") != 2:
```
### r2-fit: ScheduleWakeup stop ignored
file: earmark/agents.py
```old
stopped = args.get("stop") is True or not isinstance(delay, (int, float))
```
```new
stopped = not isinstance(delay, (int, float))
```

### r2-fit: rewritten transcript not re-read
file: earmark/agents.py
```old
            if size < cache["offset"] or (cache.get("head") and head != cache["head"] and cache["offset"]):
```
```new
            if cache.get("head") and head != cache["head"] and cache["offset"]:
```
### r2-fit: italic hint counted as typed
file: earmark/agents.py
```old
        elif n in (2, 3):
```
```new
        elif n in (2,):
```
### r2-fit: SGR 22 doesn't end a hint
file: earmark/agents.py
```old
        if n in (0, 22, 23):
```
```new
        if n in (0,):
```
### r2-fit: subagent folder not scanned
file: earmark/agents.py
```old
    folder = path[:-len(".jsonl")]
```
```new
    folder = path + ".none"
```

### r2-fit: --add-dir eats the next option's values
file: earmark/agents.py
```old
                while i < len(args) and not args[i].startswith("-"):
```
```new
                while i < len(args):
```

### r2-fit: node launcher not skipped
file: earmark/agents.py
```old
    if args and os.path.basename(args[0]) in ("node", "bun", "deno"):
```
```new
    if False:
```

### r2-fit: codex flags after the id
file: earmark/agents.py
```old
return argv[:at] + flags + argv[at:] if agent == "codex" else argv + flags
```
```new
return argv + flags
```

### r2-fit: start token: itrealvalue (constant) not starttime
file: earmark/procs.py
```old
return stat[stat.rfind(")") + 2:].split()[19]
```
```new
return stat[stat.rfind(")") + 2:].split()[18]
```

### r2-fit: memory: swap not counted
file: earmark/procs.py
```old
if line.startswith(("VmRSS:", "VmSwap:")):
```
```new
if line.startswith(("VmRSS:",)):
```

### r2-fit: busy: dash-prefixed login shells missed
file: earmark/procs.py
```old
if name.lstrip("-") in SHELLS or "shell-snapshots" in cmd:
```
```new
if name in SHELLS or "shell-snapshots" in cmd:
```

### r2-fit: tab_mark with a space accepted
file: earmark/config.py
```old
            and " " not in mark:
```
```new
            and True:
```

### r2-fit: idle_minutes 0 accepted
file: earmark/config.py
```old
if _int(raw.get("idle_minutes"), 1, 100000):
```
```new
if _int(raw.get("idle_minutes"), 0, 100000):
```

### r2-fit: popup: every click asks to forget
file: earmark/ui.py
```old
            if on_forget:  # the ×
```
```new
            if True:  # the ×
```

### r2-fit: popup: forget without confirm key
file: earmark/ui.py
```old
            if key in ("y", "Y"):
```
```new
            if True:
```

### r2-fit: popup: Esc with a filter closes
file: earmark/ui.py
```old
            if self.filter and key == "\x1b":
```
```new
            if False:
```

### r2-fit: popup: double-click doesn't open
file: earmark/ui.py
```old
        if b & curses.BUTTON1_DOUBLE_CLICKED and not on_forget:
```
```new
        if False:
```

### r2-fit: herdr: pane read of the scrollback, not the screen
file: earmark/herdr.py
```old
"--source", "visible"
```
```new
"--source", "recent"
```

<!-- Strict review 2: one per fix (R27-R51). -->

### R27 Herdr's restore goes first after a restart
file: earmark/suspend.py
```old
    if herdr_may_relaunch(session, pane_id, rec):
        return False  # every path
```
```new
    if False:
        return False  # every path
```
### R29 a split beside the pane in use is on screen
file: earmark/suspend.py
```old
        if not candidate_status(p.get("agent_status"), cfg) or p.get("tab_id") == focused_tab \
```
```new
        if not candidate_status(p.get("agent_status"), cfg) or p.get("focused") \
```
### R30 untypable values aren't kept
file: earmark/agents.py
```old
            if any(UNTYPABLE.search(w) or w.startswith(("=", "%")) for w in words):
```
```new
            if any(w.startswith(("=", "%")) for w in words):
```
### R31 a signalled agent keeps its record
file: earmark/suspend.py
```old
        if signalled:
            _set_state(session, pane_id, state="stopping", at=time.time())
```
```new
        if signalled:
            _set_state(session, pane_id, state=None, at=time.time())
```

### R32 resume goes round an alias
file: earmark/agents.py
```old
    "claude": ["command", "claude", "--resume", "{id}"],
```
```new
    "claude": ["claude", "--resume", "{id}"],
```

### R33 nested shells refused
file: earmark/suspend.py
```old
    if parent is not None and shell and parent != shell:
```
```new
    if False:
```

### R34 return grace after a long silence
file: earmark/suspend.py
```old
    if t < s.get("quiet_until", 0):
        return
```
```new
    if False:
        return
```

### R34 the silence starts the grace
file: earmark/core.py
```old
                s["quiet_until"] = t + suspend.RETURN_GRACE
```
```new
                pass
```

### R35 never into the tab in view
file: earmark/suspend.py
```old
    if snap is not None and focused_tab_of(snap) == pane.get("tab_id"):
        return False  # the user may be typing there
```
```new
    if False:
        return False  # the user may be typing there
```

### R36 wrappers count as options
file: earmark/suspend.py
```old
    unknown += [f"(started through {name})" for name in wrappers if name not in LAUNCHERS]
```
```new
    pass
```

### R37 a pane id in another tab archives the record
file: earmark/suspend.py
```old
    if (rec.get("tab_id") and pane.get("tab_id") and pane["tab_id"] != rec["tab_id"]) or \
```
```new
    if False or \
```
### R38 a deleted conversation isn't offered
file: earmark/placeholder.py
```old
    if rec.get("config_dir") is not None and facts.get("known") and not facts.get("exists"):
```
```new
    if False:
```
### R40 note seen throttled
file: earmark/core.py
```old
                "seen": s["seen"],
```
```new
                "seen": t,
```

### R41 another session in the pane archives the suspended one
file: earmark/suspend.py
```old
            return True if registry["session_id"] == rec.get("session_id") else "other"
```
```new
            return True
```

### R42 no signal once the record changed
file: earmark/suspend.py
```old
    if not current or current.get("state") != "stopping" or current.get("at") != t:
```
```new
    if False:
```

### R43 the key notices an agent running again
file: earmark/suspend.py
```old
        state = resumed_by_herdr(rec, p, info) if p else False
```
```new
        state = False
```

### R44 the key checks the status before the signal
file: earmark/suspend.py
```old
    if now.get("agent_status") in ("working", "blocked"):
        return give_up("it got busy", backoff=False)
```
```new
    if False:
        return give_up("it got busy", backoff=False)
```

### R45 reopen never twice
file: earmark/core.py
```old
    if entry["agent"] == "claude" and agents.claude_running(entry["session_id"], entry.get("config_dir")):
```
```new
    if False:
```

### R46 restore uses the suspended tab's own resume
file: earmark/core.py
```old
                    argv = tab.get("resume") or agents.resume_argv(
```
```new
                    argv = agents.resume_argv(
```

### R47 unreadable Claude folder refused
file: earmark/suspend.py
```old
    if found.get("agent") == "claude" and not (found.get("facts") or {}).get("known", True):
```
```new
    if False:
```

### R48 an unnamed agent must lead its terminal
file: earmark/suspend.py
```old
    if agent not in PROCESS_NAMES and found.get("leader_name") and found["leader_name"] != agent:
```
```new
    if False:
```

### R49 a missing workspace waits out the boot grace
file: earmark/core.py
```old
            if (booting and not said_closed(workspace_id=wid)) or partial:
```
```new
            if partial:
```
### R50 timers per Herdr session
file: earmark/suspend.py
```old
    return f"timers-{hashlib.sha256(session.encode()).hexdigest()[:12]}.json"
```
```new
    return "timers.json"
```

### R51 broken config: no automatic suspends
file: earmark/suspend.py
```old
    if cfg.get("_broken"):
        log(f"{session}: config.toml has a problem
```
```new
    if False:
        log(f"{session}: config.toml has a problem
```

### R51 broken config: no pruning
file: earmark/core.py
```old
        if event == "startup" and not cfg.get("_broken"):
```
```new
        if event == "startup":
```

### R51 broken config: the key says so
file: earmark/suspend.py
```old
    if cfg.get("_broken"):
        return ("Earmark: config.toml has a problem",
```
```new
    if False:
        return ("Earmark: config.toml has a problem",
```
### R51 a mistyped value is flagged
file: earmark/config.py
```old
    problems = errors + settings_problems(data)
    return data, "; ".join(problems) or None
```
```new
    problems = errors
    return data, "; ".join(problems) or None
```
### fit L9 the placeholder's line is checked before the stop
file: earmark/suspend.py
```old
    if not line_safe(session, pane_id):
        return "Earmark's own folders
```
```new
    if False:
        return "Earmark's own folders
```

### live: a workspace Herdr says closed is recorded at once after a restart
file: earmark/core.py
```old
            if (booting and not said_closed(workspace_id=wid)) or partial:
```
```new
            if booting or partial:
```
### live: a pane Herdr says closed is archived at once after a restart
file: earmark/core.py
```old
                       and not said_closed(pid, note.get("tab_id"), note.get("workspace_id"))):
```
```new
                       ):
```
### r3-safety: arm: in-view = the pane only, not its tab (a split)
file: earmark/suspend.py
```old
if snap is not None and focused_tab_of(snap) == pane.get("tab_id"):
```
```new
if snap is not None and pane.get("focused"):
```

### r3-safety: last look: launcher's start time not checked
file: earmark/suspend.py
```old
if any(procs.start_token(pid) != token for pid, token in found["tokens"].items()):
```
```new
if any(procs.start_token(pid) != token for pid, token in list(found["tokens"].items())[:1]):
```

### r3-safety: placeholder line goes to history (no leading space)
file: earmark/suspend.py
```old
return f" {placeholder} && {resume_command(rec)}"
```
```new
return f"{placeholder} && {resume_command(rec)}"
```

### r3-safety: resume folder typed unquoted
file: earmark/suspend.py
```old
parts.append("cd " + shlex.quote(rec["cwd"]))
```
```new
parts.append("cd " + rec["cwd"])
```

### r3-safety: CLAUDE_CONFIG_DIR typed unquoted
file: earmark/agents.py
```old
return "CLAUDE_CONFIG_DIR=" + shlex.quote(config_dir) + " "
```
```new
return "CLAUDE_CONFIG_DIR=" + config_dir + " "
```

### r3-safety: shell_safe lets a single quote through
file: earmark/agents.py
```old
UNTYPABLE = re.compile(r"['\\\x00-\x1f\x7f]")
```
```new
UNTYPABLE = re.compile(r"[\\\x00-\x1f\x7f]")
```
### r3-safety: session id may start with a dash
file: earmark/agents.py
```old
_SAFE_ID = re.compile(r"[^\s'\\-][^'\\\x00-\x1f\x7f]{0,511}")
```
```new
_SAFE_ID = re.compile(r"[^\s'\\][^'\\\x00-\x1f\x7f]{0,511}")
```

### r3-safety: Enter into any placeholder (not this session/pane's)
file: earmark/suspend.py
```old
if is_placeholder(p, session, pane_id)),
```
```new
if is_placeholder(p)),
```

### r3-safety: away gap four times longer
file: earmark/core.py
```old
if s.get("last_event") and t - s["last_event"] > suspend.AWAY_GAP:
```
```new
if s.get("last_event") and t - s["last_event"] > 4 * suspend.AWAY_GAP:
```

### r3-safety: return grace halved
file: earmark/suspend.py
```old
if t < s.get("quiet_until", 0):
```
```new
if t < s.get("quiet_until", 0) - 150:
```

### r3-safety: time mode: minutes read as seconds
file: earmark/suspend.py
```old
return [item for item in ok if t - item[2]["activity"] >= scfg["idle_minutes"] * 60]
```
```new
return [item for item in ok if t - item[2]["activity"] >= scfg["idle_minutes"]]
```

### r3-safety: draft starting with Try is ignored
file: earmark/agents.py
```old
if text.startswith('Try "') and text.endswith('"'):
```
```new
if text.startswith('Try'):
```

### r3-safety: rearm_all ends before the boot grace does
file: earmark/suspend.py
```old
    deadline = max(time.time() + REARM_WAIT, s.get("boot", 0) + core.grace(s) + 15)
```
```new
    deadline = max(time.time() + REARM_WAIT, s.get("boot", 0) + core.grace(s) - 45)
```
### r3-safety: check_pane doesn't tell arm it's a restart
file: earmark/suspend.py
```old
return arm(session, pid, restart=restart)
```
```new
return arm(session, pid, restart=False)
```

### r3-safety: Remote Control never seen in the registry
file: earmark/agents.py
```old
"remote": bool(data.get("bridgeSessionId")),
```
```new
"remote": bool(data.get("bridgeSessionID")),
```

### r3-safety: registry status never read
file: earmark/agents.py
```old
"status": data.get("status") if isinstance(data.get("status"), str) else None,
```
```new
"status": None,
```

### r3-safety: CronCreate without recurring read as a one-shot
file: earmark/agents.py
```old
                    "stamp": stamp, "recurring": args.get("recurring") is not False,
```
```new
                    "stamp": stamp, "recurring": bool(args.get("recurring")),
```
### r3-safety: any same-named agent process counts as resumed
file: earmark/suspend.py
```old
return True if listed(p, rec) else False
```
```new
return True
```

### r3-safety: the focused tab is taken from agent panes only
file: earmark/suspend.py
```old
focused = next((p for p in snap["panes"].values() if p.get("focused")), None)
    return (focused or {}).get("tab_id")
```
```new
focused = next((p for p in snap["panes"].values() if p.get("focused") and p.get("agent_session")), None)
    return (focused or {}).get("tab_id")
```

### r3-safety: settle drops a replaced suspended session unarchived
file: earmark/core.py
```old
changed |= archive_note(entries, session, current(dict(rec)), t, "replaced")
```
```new
changed |= False
```

### r3-safety: process start time in ticks read as seconds
file: earmark/procs.py
```old
return btime + int(token) / os.sysconf("SC_CLK_TCK")
```
```new
return btime + int(token)
```

### r3-safety: transcript times read as local time
file: earmark/agents.py
```old
return calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(sec))) + float(f"0.{frac or 0}")
```
```new
return time.mktime((int(y), int(mo), int(d), int(h), int(mi), int(sec), 0, 0, -1)) + float(f"0.{frac or 0}")
```

### r3-safety: missing Claude folder read as a deleted session
file: earmark/agents.py
```old
    if not os.path.isdir(os.path.join(_claude_dir(config_dir), "projects")):
        return dict(UNKNOWN)
    path = claude_transcript
```
```new
    path = claude_transcript
```

### r3-safety: a busy check under the launcher too (none: main only)
file: earmark/procs.py
```old
if name.lstrip("-") in SHELLS or "shell-snapshots" in cmd:
```
```new
if name.lstrip("-") in SHELLS:
```

### r3-safety: drop_screen deletes any path the index names
file: earmark/suspend.py
```old
if path and os.path.dirname(path) == store.screens_dir():
```
```new
if path:
```

### r3-safety: screen copy readable by everyone
file: earmark/suspend.py
```old
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
```
```new
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
```

### r3-safety: screens folder readable by everyone
file: earmark/store.py
```old
    path = os.path.join(state_dir(), "screens")
    os.makedirs(path, mode=0o700, exist_ok=True)
```
```new
    path = os.path.join(state_dir(), "screens")
    os.makedirs(path, mode=0o755, exist_ok=True)
```

### r3-safety: the key works with suspending off
file: earmark/suspend.py
```old
if cfg["suspend"]["when"] == "off":
```
```new
if cfg["suspend"]["when"] == "of":
```

### r3-safety: automatic checks run in manual mode
file: earmark/suspend.py
```old
if cfg["suspend"]["when"] not in config.AUTO_MODES:
```
```new
if cfg["suspend"]["when"] not in config.SUSPEND_MODES:
```

### r3-safety: restart grace for suspended tabs ten times longer
file: earmark/core.py
```old
            if flags is not None and t - flags.get("boot", 0) < grace(flags) \
```
```new
            if flags is not None and t - flags.get("boot", 0) < 10 * grace(flags) \
```
### r3-safety: a stalled stop finished at once (no STOP_STALE)
file: earmark/core.py
```old
elif state == "stopping" and pid in snap["panes"] and t - since > suspend.STOP_STALE:
```
```new
elif state == "stopping" and pid in snap["panes"]:
```

### r3-fit: forget-quiet-session-after-hours
file: earmark/core.py
```old
if k != session and t - v.get("seen", t) > FORGET_SESSION_DAYS * 86400]
```
```new
if k != session and t - v.get("seen", t) > FORGET_SESSION_DAYS * 3600]
```

### r3-fit: rename-doesnt-carry-archive
file: earmark/core.py
```old
if new and old and new != old:
```
```new
if new and old and new != old and False:
```

### r3-fit: workspace-closed-event-not-trusted-in-grace
file: earmark/core.py
```old
or (event == "workspace.closed" and workspace_id and data.get("workspace_id") == workspace_id))
```
```new
or False)
```

### r3-fit: cwd-ignores-foreground-cwd
file: earmark/core.py
```old
"cwd": p.get("foreground_cwd") or p.get("cwd"),
```
```new
"cwd": p.get("cwd"),
```

### r3-fit: own-stop-since-compare-flipped
file: earmark/core.py
```old
rec.get("state") == "stopping" or note.get("since", 0) <= rec.get("at", 0))
```
```new
rec.get("state") == "stopping" or note.get("since", 0) >= rec.get("at", 0))
```

### r3-fit: release-in-boot-grace-archived
file: earmark/core.py
```old
elif released and not boot_protected(s, pid, t):
```
```new
elif released:
```

### r3-fit: waking-never-archived
file: earmark/core.py
```old
elif state == "waking" and t - since > suspend.RESUME_GRACE:
```
```new
elif False:
```

### r3-fit: stop-failed-never-detected
file: earmark/core.py
```old
stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE
```
```new
stop_failed = False
```

### r3-fit: layout-cwd-of-suspended-from-pane
file: earmark/core.py
```old
"cwd": (source.get("cwd") if agent_pane and agent_pane["pane_id"] in suspended else None)
```
```new
"cwd": (None)
```

### r3-fit: archive-sessions-without-content
file: earmark/core.py
```old
if facts["known"] and not (facts["exists"] and facts["has_content"]):
        return False
```
```new
if facts["known"] and not facts["exists"]:
        return False
```

### r3-fit: last-active-is-close-time
file: earmark/core.py
```old
"last_active": facts["last_active"] or note.get("seen") or t,
```
```new
"last_active": t,
```

### r3-fit: known-agents-pruned-at-30-days
file: earmark/core.py
```old
(0 if facts["known"] else config.FALLBACK_DAYS)
```
```new
(config.FALLBACK_DAYS)
```

### r3-fit: closed-workspaces-never-age-out-by-default
file: earmark/core.py
```old
days = cfg["keep_days"] if cfg["keep_days"] is not None else config.FALLBACK_DAYS
        if days and t - closed[key]
```
```new
days = cfg["keep_days"]
        if days and t - closed[key]
```

### r3-fit: restore-ignores-registry
file: earmark/core.py
```old
elsewhere = tab["agent"] == "claude" and agents.claude_running(tab["session_id"], tab.get("config_dir"))
```
```new
elsewhere = False
```

### r3-fit: restore-drops-suspended-options
file: earmark/core.py
```old
argv = tab.get("resume") or agents.resume_argv(tab["agent"], tab["session_id"], cfg["resume"])
```
```new
argv = agents.resume_argv(tab["agent"], tab["session_id"], cfg["resume"])
```

### r3-fit: mark-never-stripped-from-names
file: earmark/core.py
```old
return label[len(mark) + 1:] if mark and label.startswith(mark + " ") else label
```
```new
return label
```

### r3-fit: blocked-not-refused
file: earmark/suspend.py
```old
if status == "blocked":
```
```new
if status == "blockedX":
```

### r3-fit: registry-busy-ignored
file: earmark/suspend.py
```old
if registry.get("status") not in (None, "idle"):
```
```new
if registry.get("status") not in (None, "idle", "busy"):
```

### r3-fit: key-ignores-busy-children
file: earmark/suspend.py
```old
if found.get("busy"):
```
```new
if found.get("busy") and not manual:
```

### r3-fit: wrappers-not-unknown
file: earmark/suspend.py
```old
unknown += [f"(started through {name})" for name in wrappers if name not in LAUNCHERS]
```
```new
unknown += []
```

### r3-fit: focus-not-activity
file: earmark/suspend.py
```old
activity = [note.get(k) or 0 for k in ("since", "focused_at", "status_at")]
```
```new
activity = [note.get(k) or 0 for k in ("since", "status_at")]
```

### r3-fit: wakeup-no-grace
file: earmark/suspend.py
```old
        elif wake and wake + TIMER_GRACE + pushed_back(cache, timers.get("_away"), wake) > t:
```
```new
        elif wake and wake + pushed_back(cache, timers.get("_away"), wake) > t:
```
### r3-fit: transcript-behind-ok
file: earmark/suspend.py
```old
if cache.get("behind"):
```
```new
if False:
```

### r3-fit: count-keeps-one-fewer
file: earmark/suspend.py
```old
keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"]]}
```
```new
keep = {item[0]["pane_id"] for item in recent[:max(0, scfg["keep_awake"] - 1)]}
```

### r3-fit: memory-threshold-off-by-one
file: earmark/suspend.py
```old
if available is None or available >= scfg["memory_below"] or not total_kb:
```
```new
if available is None or available > scfg["memory_below"] or not total_kb:
```

### r3-fit: return-grace-ignored
file: earmark/suspend.py
```old
if t < s.get("quiet_until", 0):
```
```new
if False:
```

### r3-fit: key-suspends-with-draft
file: earmark/suspend.py
```old
    if draft:
        return "there's unsent text in its prompt"
```
```new
    if draft and not manual:
        return "there's unsent text in its prompt"
```

### r3-fit: last-look-blocked-ok
file: earmark/suspend.py
```old
if now.get("agent_status") in ("working", "blocked"):
```
```new
if now.get("agent_status") in ("working",):
```

### r3-fit: record-changed-check-weak
file: earmark/suspend.py
```old
if not current or current.get("state") != "stopping" or current.get("at") != t:
```
```new
if not current:
```

### r3-fit: arm-into-view
file: earmark/suspend.py
```old
if snap is not None and focused_tab_of(snap) == pane.get("tab_id"):
```
```new
if False:
```

### r3-fit: arm-no-recheck-after-claim
file: earmark/suspend.py
```old
        if not bare_shell(herdr.process_info(pane_id)) or \
                (again is not None and focused_tab_of(again) == pane.get("tab_id")) or \
                (automatic and screen_print(dict(pane, pane_id=pane_id)) != (rec.get("base") or {}).get("screen")):
```
```new
        if False:
```
### r3-fit: herdr-may-relaunch-never
file: earmark/suspend.py
```old
    return bool(rec.get("herdr_listed")) or note.get("session_id") == rec.get("session_id")
```
```new
    return False
```
### r3-fit: own-pane-counts-as-elsewhere
file: earmark/suspend.py
```old
if pid != pane_id and ref.get("value") and f"{ref.get('agent') or p.get('agent')}:{ref['value']}" == key:
```
```new
if ref.get("value") and f"{ref.get('agent') or p.get('agent')}:{ref['value']}" == key:
```

### r3-fit: resume-runs-after-ctrl-c
file: earmark/suspend.py
```old
return f" {placeholder} && {resume_command(rec)}"
```
```new
return f" {placeholder} ; {resume_command(rec)}"
```

### r3-fit: line-safe-always
file: earmark/suspend.py
```old
    return all(shell_safe(p) for p in paths) and not any(agents.UNTYPABLE.search(w or "") for w in (session, pane_id))
```
```new
    return True
```
### r3-fit: placeholder-match-loose
file: earmark/suspend.py
```old
if len(rest) % 2 or any(opt not in ("--state", "--config") for opt in rest[::2]):
```
```new
if False:
```

### r3-fit: key-works-when-off
file: earmark/suspend.py
```old
if cfg["suspend"]["when"] == "off":
```
```new
if False:
```

### r3-fit: command-noise-is-content
file: earmark/agents.py
```old
if not content or content.startswith(_COMMAND_NOISE):
```
```new
if not content:
```

### r3-fit: transcript-rewrite-not-noticed
file: earmark/agents.py
```old
            if size < cache["offset"] or (cache.get("head") and head != cache["head"] and cache["offset"]):
```
```new
            if size < cache["offset"]:
```
### r3-fit: double-dash-not-end
file: earmark/agents.py
```old
break  # everything after is the prompt
```
```new
i += 1; continue
```

### r3-fit: bypass-allow-not-kept
file: earmark/agents.py
```old
if bypass_allowed:
        out.append("--allow-dangerously-skip-permissions")
```
```new
if False:
        out.append("--allow-dangerously-skip-permissions")
```

### r3-fit: plan-mode-not-resumable
file: earmark/agents.py
```old
RESUMABLE_MODES = {"acceptEdits", "plan", "auto", "dontAsk"}
```
```new
RESUMABLE_MODES = {"acceptEdits", "auto", "dontAsk"}
```

### r3-fit: frozen-keeps-input-box
file: earmark/agents.py
```old
return lines[:box[0]]
```
```new
return lines
```

### r3-fit: memfree-not-available
file: earmark/procs.py
```old
return 100.0 * info["MemAvailable"] / info["MemTotal"]
```
```new
return 100.0 * info["MemFree"] / info["MemTotal"]
```

### r3-fit: children-only
file: earmark/procs.py
```old
stack.extend(self.kids.get(p, []))
```
```new
pass
```

### r3-fit: any-key-resumes
file: earmark/placeholder.py
```old
ENTER = re.compile(rb"[\r\n]|\x1b\[13(;1(:1)?)?u")
```
```new
ENTER = re.compile(rb".")
```

### r3-fit: refusal-still-resumes
file: earmark/placeholder.py
```old
    if why:
        print(f"Earmark: {why}.")
        return 1
```
```new
    if False:
        print(f"Earmark: {why}.")
        return 1
```

### r3-fit: crop-one-column-over
file: earmark/placeholder.py
```old
if used + w > cols:
```
```new
if used + w > cols + 1:
```

### r3-fit: suspend-problems-not-broken
file: earmark/config.py
```old
    if problem:
        cfg["_broken"] = problem
```
```new
    if False:
        cfg["_broken"] = problem
```
### r3-fit: hash-in-string-is-comment
file: earmark/config.py
```old
elif ch == "#" and not in_string:
```
```new
elif ch == "#":
```

### r3-fit: tab-mark-dash-ok
file: earmark/config.py
```old
if isinstance(mark, str) and len(mark) <= 8 and not mark.startswith("-") and mark.isprintable() \
```
```new
if isinstance(mark, str) and len(mark) <= 8 and mark.isprintable() \
```

### r3-fit: damaged-file-overwritten
file: earmark/store.py
```old
os.replace(path, aside if n == 1 else f"{aside}-{n}")
```
```new
pass
```

### r3-fit: dash-labels-passed
file: earmark/herdr.py
```old
return "" if label.startswith("-") else label
```
```new
return label
```

### r3-fit: popup-clicks-act-during-confirm
file: earmark/ui.py
```old
            if clicked and y == h - 1:
                for name, (x0, x1) in self.buttons.items():
```
```new
            if clicked:
                for name, (x0, x1) in self.buttons.items():
```

### r3-fit: key-pane-from-env-first
file: earmark.py
```old
pane_id = ctx.get("focused_pane_id") or os.environ.get("HERDR_PANE_ID")
```
```new
pane_id = os.environ.get("HERDR_PANE_ID") or ctx.get("focused_pane_id")
```

### r3-fit: config-dir-never-read-from-process
file: earmark/core.py
```old
claude = next((x for x in info.get("foreground_processes") or [] if x.get("name") == "claude"), None)
```
```new
claude = None
```

### r3-fit: config-dir-looked-up-every-hook
file: earmark/core.py
```old
            if note.get("config_dir") is not None or t - note.get("config_dir_tried", 0) < CONFIG_DIR_RETRY:
                continue
```
```new
            if False:
                continue
```
### r3-fit: config-dir-not-noted
file: earmark/core.py
```old
if p.get("_config_dir") is not None:
                new["config_dir"] = p["_config_dir"]
```
```new
if False:
                new["config_dir"] = p["_config_dir"]
```

### r3-fit: layout-drops-config-dir
file: earmark/core.py
```old
if source.get("config_dir") is not None:
            entry["config_dir"] = source["config_dir"]
```
```new
if False:
            entry["config_dir"] = source["config_dir"]
```

### r3-fit: archive-drops-config-dir
file: earmark/core.py
```old
if note.get("config_dir") is not None:
        entries[key]["config_dir"] = note["config_dir"]
```
```new
if False:
        entries[key]["config_dir"] = note["config_dir"]
```

### r3-fit: sidebar-seq-zero
file: earmark/core.py
```old
out.append((wid, text, time.time_ns()))
```
```new
out.append((wid, text, 0))
```

### r3-fit: settle-now-never-saves
file: earmark/core.py
```old
if json.dumps(s["suspended"], sort_keys=True) != before:
```
```new
if False:
```

### r3-fit: worker-every-hook
file: earmark/core.py
```old
t - s.get("suspend_checked", 0) >= suspend.CHECK_EVERY
```
```new
t - s.get("suspend_checked", 0) >= 0
```

### r3-fit: away-gap-ten-times
file: earmark/core.py
```old
if s.get("last_event") and t - s["last_event"] > suspend.AWAY_GAP:
```
```new
if s.get("last_event") and t - s["last_event"] > suspend.AWAY_GAP * 10:
```

### r3-fit: process-info-unfiltered
file: earmark/herdr.py
```old
info["foreground_processes"] = [x for x in info.get("foreground_processes") or [] if isinstance(x, dict)]
```
```new
info["foreground_processes"] = info.get("foreground_processes") or []
```

### r3-fit: index-sessions-unfiltered
file: earmark/store.py
```old
if isinstance(v, dict) and isinstance(v.get("panes", {}), dict)}
```
```new
if isinstance(v, dict)}
```

### r3-fit: fit-ellipsis-overflows
file: earmark/text.py
```old
if used + char_cols(ch) > width - 1:  # leave a column for …
```
```new
if used + char_cols(ch) > width:
```

### r3-fit: frozen-shows-top-of-screen
file: earmark/placeholder.py
```old
        body = [dimmed(crop(line, cols)) for line in lines][-room:] if room else []
```
```new
        body = [dimmed(crop(line, cols)) for line in lines][:room] if room else []
```

### r3-fit: memory-mode-looks-when-fine
file: earmark/suspend.py
```old
if mode == "memory" and (available is None or available >= cfg["suspend"]["memory_below"]):
        return
```
```new
if False:
        return
```

### r3-fit: auto-looks-at-agents-not-due
file: earmark/suspend.py
```old
or note.get("backoff_until", 0) > t or t - recent < soonest:
```
```new
or note.get("backoff_until", 0) > t or False:
```

### r3-fit: rearm-pass-into-waking
file: earmark/suspend.py
```old
if rec.get("state") == "waking" and time.time() - (rec.get("waking_at") or 0) < RESUME_GRACE:
            continue
```
```new
if False:
            continue
```

### r3-fit: placeholder-wakes-every-second
file: earmark/placeholder.py
```old
ready, _, _ = select.select([fd, wake_r], [], [], 60.5 - time.time() % 60)
```
```new
ready, _, _ = select.select([fd, wake_r], [], [], 1)
```

### r3-fit: listing-oldest-first
file: earmark/core.py
```old
return sorted(rows, key=lambda e: e.get("last_active") or 0, reverse=True)
```
```new
return sorted(rows, key=lambda e: e.get("last_active") or 0, reverse=False)
```

<!-- Strict review 3: one per fix (R53-R68). -->

### R53 Herdr listing the stopped session is kept on the record
file: earmark/core.py
```old
        if pid in panes and state in ("suspended", "stopping", "waking"):
            rec["herdr_listed"] = True
```
```new
        if False:
            rec["herdr_listed"] = True
```

### R53 the listing mark lasts through the boot grace
file: earmark/core.py
```old
        elif pid in snap["panes"] and not other and not booting and state == "suspended":
```
```new
        elif pid in snap["panes"] and not other and state == "suspended":
```

### R53 every arm path waits for Herdr's restore
file: earmark/suspend.py
```old
    if herdr_may_relaunch(session, pane_id, rec):
        return False  # every path
```
```new
    if restart and herdr_may_relaunch(session, pane_id, rec):
        return False  # every path
```

### R53 the record, not the note, says Herdr listed it
file: earmark/suspend.py
```old
    return bool(rec.get("herdr_listed")) or note.get("session_id") == rec.get("session_id")
```
```new
    return note.get("session_id") == rec.get("session_id")
```

### R54 the popup never prunes with a broken config
file: earmark/ui.py
```old
            if not self.pruned and not self.cfg.get("_broken") and core.prune(archive, self.cfg, time.time()):
```
```new
            if not self.pruned and core.prune(archive, self.cfg, time.time()):
```
### R54 a link to nowhere is a problem
file: earmark/config.py
```old
        if isinstance(e, FileNotFoundError) and not os.path.lexists(path):
```
```new
        if isinstance(e, FileNotFoundError):
```

### R54 keep_days is checked
file: earmark/config.py
```old
            if not _int(value, 0, 10 ** 6):
```
```new
            if False:
```

### R54 an unknown key is a problem
file: earmark/config.py
```old
            out.append(f"{key} isn't a setting")
```
```new
            pass
```

### R55 the tab in view is looked at again after the claim
file: earmark/suspend.py
```old
                (again is not None and focused_tab_of(again) == pane.get("tab_id")) or \
```
```new
                False or \
```

### R56 an unknown status is asked about
file: earmark/suspend.py
```old
    if p.get("agent_status") not in ("idle", "done"):
        doubts.append(
```
```new
    if False:
        doubts.append(
```

### R56 an unreadable Claude folder is asked about
file: earmark/suspend.py
```old
    doubts += cant_check(found)
```
```new
    doubts += []
```

### R57 a failed folder lookup records nothing
file: earmark/core.py
```old
        p["_config_dir_tried"] = t

```
```new
        p["_config_dir_tried"] = t
        p["_config_dir"] = ""

```

### R58 Codex without --no-daemon isn't suspended
file: earmark/suspend.py
```old
    if agent == "codex" and "--no-daemon" not in (found.get("launch") or []):
```
```new
    if False:
```

### R59 a line longer than the window is skipped
file: earmark/agents.py
```old
    elif len(chunk) == TIMER_READ and b"\n" not in chunk:
```
```new
    elif False:
```

### R60 the placeholder unmarks in its own session
file: earmark/placeholder.py
```old
            suspend.unmark_tab(tab_id, label, mark, session=session)
```
```new
            suspend.unmark_tab(tab_id, label, mark, session=next(iter(store.load_index().get("sessions", {})), None))
```

### R61 a failed rename unlists the tab
file: earmark/suspend.py
```old
                    session_state(index, session).setdefault("marked", {}).pop(tab_id, None)
```
```new
                    pass
```

### R61 only a known shell is typed into
file: earmark/suspend.py
```old
    return me is None or (me.get("name") or "").lstrip("-") in SHELLS_OK
```
```new
    return True
```

### R64 only the doubt shown is accepted
file: earmark/suspend.py
```old
        if accept != "; ".join(doubts):
```
```new
        if accept is None:
```

### R64 the key asks in its popup
file: earmark/suspend.py
```old
                     ask={"session": session, "pane_id": pane_id, "why": doubt})
```
```new
                     ask=None)
```

### R66 seen_at isn't rewritten every hook
file: earmark/core.py
```old
        if pid in snap["panes"] and (t - rec.get("seen_at", 0) >= 600 or rec.get("seen_at", 0) < (flags or {}).get("boot", 0)):
```
```new
        if pid in snap["panes"]:
```

### R66 unchanged timers aren't rewritten
file: earmark/suspend.py
```old
        if store.load_json(timers_file(session)) != new:
```
```new
        if True:
```

### R67 clicks hit only rows on screen
file: earmark/ui.py
```old
        return n if 2 <= y < min(2 + len(self.rows) - self.top, h - 2) and 0 <= n < len(self.rows) else None
```
```new
        return n if 2 <= y < 2 + len(self.rows) - self.top and 0 <= n < len(self.rows) else None
```

### R68 Claude facts don't load sqlite3
file: earmark/agents.py
```old
    reader = {"claude": _claude_facts, "codex": _codex_facts, "grok": _grok_facts}.get(agent)
```
```new
    import sqlite3  # noqa: F401
    reader = {"claude": _claude_facts, "codex": _codex_facts, "grok": _grok_facts}.get(agent)
```

<!-- messages = "toast" (Cody, 2026-11-26). -->

### toast: falls back to the popup when Herdr's toasts are off
file: earmark/suspend.py
```old
    if (toast_mode(cfg) or late) and herdr.notify(title, body) is True:
```
```new
    if (toast_mode(cfg) or late) and herdr.notify(title, body) is not False:
```
### toast: the popup is the default
file: earmark/config.py
```old
                    "messages": "popup"}
```
```new
                    "messages": "toast"}
```

### toast: Herdr's toasts are off unless set
file: earmark/herdr.py
```old
    return (setting("ui.toast", "delivery") or "off") != "off"
```
```new
    return setting("ui.toast", "delivery") != "off"
```
### toast: the second press has a deadline
file: earmark/suspend.py
```old
    return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why
```
```new
    return bool(ask) and t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why
```
### r4-fit: store: worker lock always granted
file: earmark/store.py
```old
            yield False
            return
```
```new
            yield True
            return
```

### r4-fit: store: damaged file not set aside
file: earmark/store.py
```old
        os.replace(path, aside if n == 1 else f"{aside}-{n}")
```
```new
        pass
```

### r4-fit: herdr: error replies taken as results
file: earmark/herdr.py
```old
    if isinstance(reply, dict) and "error" in reply:
```
```new
    if False:
```

### r4-fit: herdr: new tab gets a missing folder
file: earmark/herdr.py
```old
    if cwd and os.path.isdir(cwd):
```
```new
    if cwd:
```

### r4-fit: herdr: zero count never clears the token
file: earmark/herdr.py
```old
    args += ["--token", f"earmark={text}"] if text else ["--clear-token", "earmark"]
```
```new
    args += ["--token", f"earmark={text}"]
```

### r4-fit: config: idle_minutes 0 accepted
file: earmark/config.py
```old
    if _int(raw.get("idle_minutes"), 1, 100000):
```
```new
    if _int(raw.get("idle_minutes"), 0, 100000):
```

### r4-fit: config: memory_below up to 100
file: earmark/config.py
```old
    if _int(raw.get("memory_below"), 1, 90):
```
```new
    if _int(raw.get("memory_below"), 1, 100):
```

### r4-fit: config: long tab marks accepted
file: earmark/config.py
```old
    if isinstance(mark, str) and len(mark) <= 8 and not mark.startswith("-") and mark.isprintable() \
```
```new
    if isinstance(mark, str) and not mark.startswith("-") and mark.isprintable() \
```

### r4-fit: config: keep_days 0 ignored
file: earmark/config.py
```old
    if isinstance(days, int) and not isinstance(days, bool) and days >= 0:
```
```new
    if isinstance(days, int) and not isinstance(days, bool) and days > 0:
```

### r4-fit: core: away gap as short as the return grace
file: earmark/core.py
```old
            if s.get("last_event") and t - s["last_event"] > suspend.AWAY_GAP:
```
```new
            if s.get("last_event") and t - s["last_event"] > suspend.RETURN_GRACE:
```

### r4-fit: core: released events also wait for a session
file: earmark/core.py
```old
    if event == "pane.agent_detected" and not data.get("released") and data.get("pane_id"):
```
```new
    if event == "pane.agent_detected" and data.get("pane_id"):
```

### r4-fit: core: session wait ignores a pane without agent
file: earmark/core.py
```old
        if (p.get("agent_session") or {}).get("value") or not p.get("agent"):
```
```new
        if (p.get("agent_session") or {}).get("value"):
```

### r4-fit: core: reopen leaves the entry in the archive
file: earmark/core.py
```old
    forget(entry["key"])
    note_started(
```
```new
    note_started(
```

### r4-fit: core: restore names default tabs
file: earmark/core.py
```old
            label = "" if is_default_tab_label(tab.get("label"), tab.get("number")) else herdr.safe_label(tab["label"])
```
```new
            label = herdr.safe_label(tab.get("label") or "")
```

### r4-fit: core: restore focuses every tab
file: earmark/core.py
```old
                tab_id, pane_id = herdr.new_tab(target, tab.get("cwd"), label, focus=(i == 0))
```
```new
                tab_id, pane_id = herdr.new_tab(target, tab.get("cwd"), label, focus=True)
```

### r4-fit: core: duplicate names shown twice
file: earmark/core.py
```old
    if secondary.strip().lower() == primary.strip().lower():
```
```new
    if secondary == primary:
```

### r4-fit: core: zero count text
file: earmark/core.py
```old
    return f"{n} archived" if n else ""
```
```new
    return f"{n} archived"
```

### r4-fit: core: reopen ignores the label check on the id
file: earmark/core.py
```old
    if w and (w.get("label") or "") == entry["workspace_label"]:
```
```new
    if w:
```

### r4-fit: core: workspace rename not carried
file: earmark/core.py
```old
                if e["herdr_session"] == session and e["workspace_id"] == wid and e["workspace_label"] == old:
```
```new
                if False:
```

### r4-fit: core: report_count off still reports
file: earmark/core.py
```old
        if cfg["report_count"]:
            reports = pending_reports(index, archive, session, snap)
```
```new
        if True:
            reports = pending_reports(index, archive, session, snap)
```
### r4-fit: core: focus stamp every hook
file: earmark/core.py
```old
        if (left and note.get("tab_id") == left) or (event == "pane.focused" and data.get("pane_id") == pid):
```
```new
        if (left and note.get("tab_id") == left) or note.get("tab_id") == tab_now or (event == "pane.focused" and data.get("pane_id") == pid):
```
### r4-fit: core: left tab not stamped
file: earmark/core.py
```old
        if (left and note.get("tab_id") == left) or (event == "pane.focused" and data.get("pane_id") == pid):
```
```new
        if (event == "pane.focused" and data.get("pane_id") == pid):
```
### r4-fit: suspend: memory mode stops after the first suspend
file: earmark/suspend.py
```old
            if now is not None and now >= cfg["suspend"]["memory_below"] + MEMORY_MARGIN:
```
```new
            if now is not None:
```

### r4-fit: suspend: timers of closed sessions kept for ever
file: earmark/suspend.py
```old
    save_timers(session, timers, keep=live)
```
```new
    save_timers(session, timers)
```

### r4-fit: suspend: worker log never rotated
file: earmark/suspend.py
```old
        if os.path.getsize(path) > 256 * 1024:
```
```new
        if False:
```

### r4-fit: suspend: worker in the hook's own session
file: earmark/suspend.py
```old
                         stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, start_new_session=True,
```
```new
                         stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, start_new_session=False,
```

### r4-fit: suspend: placeholder given one look only
file: earmark/suspend.py
```old
        for _ in range(32):  # a shell just restored by Herdr can take a few seconds
```
```new
        for _ in range(1):
```

### r4-fit: suspend: memory counts the agent only
file: earmark/suspend.py
```old
    out["memory_kb"] = procs.memory_kb(sorted(mine))
```
```new
    out["memory_kb"] = procs.memory_kb([main["pid"]])
```

### r4-fit: suspend: auto check without the worker lock
file: earmark/suspend.py
```old
        if mine:
            auto(session, cfg)
```
```new
        if True:
            auto(session, cfg)
```

### r4-fit: suspend: a stopped-but-unarmed key gets the plain refusal
file: earmark/suspend.py
```old
    elif why and (record(session, pane_id) or {}).get("state") == "suspended":
```
```new
    elif False:
```

### r4-fit: suspend: unmark leaves a space
file: earmark/suspend.py
```old
        name = label[len(mark) + 1:]
```
```new
        name = label[len(mark):]
```

### r4-fit: suspend: count mode keeps none of the in-view
file: earmark/suspend.py
```old
        recent = sorted(looks, key=lambda item: t if item[2] is None else item[2].get("activity", t), reverse=True)
```
```new
        recent = sorted([x for x in looks if x[2] is not None], key=lambda item: item[2].get("activity", t), reverse=True)
```

### r4-fit: suspend: arm claim window zero
file: earmark/suspend.py
```old
        if rec.get("arming", 0) > t - ARM_CLAIM:
```
```new
        if rec.get("arming", 0) > t:
```

### r4-fit: suspend: confirm keeps the window after use
file: earmark/suspend.py
```old
        ask = asks.pop(pane_id, None)
```
```new
        ask = asks.get(pane_id)
```

### r4-fit: message: Enter confirms
file: earmark/message.py
```old
                return "y" if typed.lower() == "y" else ""
```
```new
                return "y"
```
### r4-fit: message: question gives up at once
file: earmark/message.py
```old
        if read_answer(fd, ASK_WAIT, echo=echoed) != "y":
```
```new
        if read_answer(fd, 0, echo=echoed) != "y":
```
### r4-fit: placeholder: Enter only as CR
file: earmark/placeholder.py
```old
ENTER = re.compile(rb"[\r\n]|\x1b\[13(;1(:1)?)?u")
```
```new
ENTER = re.compile(rb"[\r]")
```

### r4-fit: placeholder: frozen view in a tiny pane
file: earmark/placeholder.py
```old
    if lines and rows >= 6 and cols >= 30:
```
```new
    if lines:
```

### r4-fit: placeholder: unmark with another split still asleep
file: earmark/placeholder.py
```old
        if mark and not others:
```
```new
        if mark:
```

### r4-fit: placeholder: frozen view not dimmed after resets
file: earmark/placeholder.py
```old
    return DIM + line.replace("\x1b[0m", "\x1b[0m" + DIM).replace("\x1b[m", "\x1b[m" + DIM) \
```
```new
    return DIM + line.replace("\x1b[0m", "\x1b[0m").replace("\x1b[m", "\x1b[m" + DIM) \
```

### r4-fit: placeholder: title not cleared
file: earmark/placeholder.py
```old
    sys.stdout.write("\x1b]2;\x07")
```
```new
    pass
```

### r4-fit: text: fullwidth forms one column
file: earmark/text.py
```old
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
```
```new
    return 2 if unicodedata.east_asian_width(ch) in ("W",) else 1
```

### r4-fit: text: just now for 89 s -> 59
file: earmark/text.py
```old
    if seconds < 90:
```
```new
    if seconds < 60:
```

### r4-fit: ui: Enter forgets while asking
file: earmark/ui.py
```old
            if key in ("y", "Y"):
```
```new
            if key in ("y", "Y", "\n"):
```

### r4-fit: ui: wide forget hit area
file: earmark/ui.py
```old
        on_forget = x >= w - FORGET_COL - 1
```
```new
        on_forget = x >= w - FORGET_COL - 12
```

### r4-fit: ui: wheel up goes down
file: earmark/ui.py
```old
        if b & curses.BUTTON4_PRESSED:
            self.sel -= 1
```
```new
        if b & curses.BUTTON4_PRESSED:
            self.sel += 1
```

### r4-fit: ui: filter ignores the tab name
file: earmark/ui.py
```old
                        (r.get("title"), core.custom_name(r), r.get("workspace_label")))]
```
```new
                        (r.get("title"), r.get("workspace_label")))]
```

### r4-fit: ui: reopen leaves sidebar count stale
file: earmark/ui.py
```old
        core.update_counts(self.session)
        return True
```
```new
        return True
```

### r4-fit: agents: AI title beats the user's custom title
file: earmark/agents.py
```old
    title = custom or ai or prompt
```
```new
    title = ai or custom or prompt
```

### r4-fit: agents: + options take one value
file: earmark/agents.py
```old
                while i < len(args) and not args[i].startswith("-"):
```
```new
                while i < len(args) and not args[i].startswith("-") and len(words) < 2:
```

### r4-fit: agents: timers from non-assistant records
file: earmark/agents.py
```old
        if record.get("type") != "assistant" or stamp is None or stamp < since:
```
```new
        if stamp is None or stamp < since:
```

### r4-fit: agents: relative CLAUDE_CONFIG_DIR typed
file: earmark/agents.py
```old
    if agent != "claude" or not config_dir or not os.path.isabs(config_dir) or UNTYPABLE.search(config_dir):
```
```new
    if agent != "claude" or not config_dir or UNTYPABLE.search(config_dir):
```

### r4-fit: agents: registry start-time tolerance huge
file: earmark/agents.py
```old
        if isinstance(recorded, (int, float)) and started is not None and abs(started - recorded / 1000) > 30:
```
```new
        if isinstance(recorded, (int, float)) and started is not None and abs(started - recorded / 1000) > 30000:
```

### r4-fit: agents: bypass switch not kept
file: earmark/agents.py
```old
    if bypass_allowed:
        out.append("--allow-dangerously-skip-permissions")
```
```new
    if False:
        out.append("--allow-dangerously-skip-permissions")
```

### r4-fit: agents: one-shot crons last a week
file: earmark/agents.py
```old
ONE_SHOT_HOURS = 24  # a one-shot scheduled task counts as pending this long
```
```new
ONE_SHOT_HOURS = 24 * 7
```

### r4-fit: agents: codex draft keeps the prompt glyph
file: earmark/agents.py
```old
        text = line[1:].strip() if line.startswith("›") else line
```
```new
        text = line.strip()
```
### r4-fit: procs: environ prefix without =
file: earmark/procs.py
```old
    return None if env is None else env.get(name, "")
```
```new
    return None if env is None else next((v for k, v in env.items() if k.startswith(name)), "")
```

### r4-fit: procs: macOS etime days ignored
file: earmark/procs.py
```old
        return time.time() - seconds - int(days or 0) * 86400
```
```new
        return time.time() - seconds
```

<!-- Strict review 4: one per fix (R69-R76). -->

### R69 the second-press window starts only after a toast Herdr showed
file: earmark/suspend.py
```old
        if shown:
            remember_ask(session, pane_id, doubt, time.time())
```
```new
        if toast_mode(cfg):
            remember_ask(session, pane_id, doubt, time.time())
```

### R70 an unknown mode never resumes bypassing
file: earmark/agents.py
```old
            if f == "--dangerously-skip-permissions":
                out.append("--allow-dangerously-skip-permissions")
```
```new
            if f == "--dangerously-skip-permissions":
                out.append(f)
```
### R70 the mode is tracked over the whole transcript
file: earmark/agents.py
```old
            if isinstance(value, str):
                cache["mode"] = value
```
```new
            if isinstance(value, str):
                pass
```

### R70 look keeps the tracked mode
file: earmark/suspend.py
```old
        out["mode"] = cache.get("mode", "")
```
```new
        out["mode"] = ""
```

### R70 the suspend uses the tracked mode
file: earmark/suspend.py
```old
    mode_now = found.get("mode") or ""
```
```new
    mode_now = ""
```

### R71 last_event only with an automatic mode
file: earmark/core.py
```old
            if scfg["when"] in config.AUTO_MODES:  # nothing else reads it
```
```new
            if True:  # nothing else reads it
```

### R72 a live placeholder is seen without Herdr
file: earmark/suspend.py
```old
        if placeholder_alive(rec):
            continue
```
```new
        if False:
            continue
```

### R72 arm remembers the placeholder
file: earmark/suspend.py
```old
    if ok:
        note_placeholder(session, pane_id, up)
```
```new
    if False:
        note_placeholder(session, pane_id, up)
```

### R72 no process scan unless a look needs it
file: earmark/suspend.py
```old
    table = None  # the process table, built on the first look that needs it
```
```new
    table = procs.Table()  # the process table, built on the first look that needs it
```

### R73 parent pids that change every hook stop counting
file: earmark/core.py
```old
        if len(recent) >= 3:
```
```new
        if False:
```

### R74 the popup's body is cut to fit
file: earmark/message.py
```old
    room = max(1, height - 2 - len(out))
```
```new
    room = 10 ** 6
```

### R75 unset and unreadable differ
file: earmark/procs.py
```old
        except OSError:
            return None
        out = {}
```
```new
        except OSError:
            return {}
        out = {}
```

### R75 a value with spaces on macOS
file: earmark/procs.py
```old
            value.append(word)
```
```new
            pass
```

### R75 an unreadable environment is asked again
file: earmark/core.py
```old
            if value is not None:  # None: its environment couldn't be read; asked again later
```
```new
            if True:  # None: its environment couldn't be read; asked again later
```

### R76 the grace follows Herdr's restore delay
file: earmark/core.py
```old
    return max(BOOT_GRACE, 30 + n_panes * max(0.0, delay) / 1000)
```
```new
    return BOOT_GRACE
```

<!-- Strict review 4: the safety reviewer's 3 survivors (its list wasn't kept), and one per fix (R79-R88). -->

### r4-safety: the record's own time isn't checked before the signal
file: earmark/suspend.py
```old
    if not current or current.get("state") != "stopping" or current.get("at") != t:
```
```new
    if not current or current.get("state") != "stopping":
```

### r4-safety: last_event never refreshed
file: earmark/core.py
```old
                if t - s.get("last_event", 0) > 60:
                    s["last_event"] = t
```
```new
                if not s.get("last_event"):
                    s["last_event"] = t
```

### r4-safety: the placeholder accepts any record state
file: earmark/placeholder.py
```old
    if not rec or rec.get("state") not in ("stopping", "suspended", "waking"):
```
```new
    if not rec:
```

### R79 Claude's own session must match Herdr's
file: earmark/suspend.py
```old
    if agent == "claude" and registry.get("session_id") and registry["session_id"] != sid:
```
```new
    if False:
```

### R80 a toast question only with Herdr's own toasts
file: earmark/suspend.py
```old
        shown = toast_mode(cfg) and herdr.setting("ui.toast", "delivery") == "herdr" and herdr.notify(
```
```new
        shown = toast_mode(cfg) and herdr.notify(
```

### R80 a double tap isn't a second press
file: earmark/suspend.py
```old
    return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why
```
```new
    return bool(ask) and ask.get("until", 0) >= t and ask.get("why") == why
```

### R80 old asks are pruned
file: earmark/suspend.py
```old
        for pid in [pid for pid, a in asks.items() if a.get("until", 0) < t]:
            del asks[pid]  # old asks nobody answered
```
```new
        for pid in []:
            del asks[pid]  # old asks nobody answered
```

### R81 a delete takes only the task it names
file: earmark/agents.py
```old
                if match:
                    del created[match]
```
```new
                if created:
                    del created[next(iter(created))]
```

### R81 a create's answer is read
file: earmark/agents.py
```old
                    created[item["tool_use_id"]]["result"] = _result_text(item)
```
```new
                    pass
```

### R82 an untypable Claude folder is refused
file: earmark/suspend.py
```old
    if agent == "claude" and found.get("config_dir") and not agents.env_prefix("claude", found["config_dir"]):
```
```new
    if False:
```

### R82 an untypable folder is refused
file: earmark/suspend.py
```old
    if found.get("cwd_unsafe"):
```
```new
    if False:
```

### R83 a partial pane list closes no pane
file: earmark/core.py
```old
        if partial or (booting and pid in s.get("boot_panes", [])
```
```new
        if (booting and pid in s.get("boot_panes", [])
```

### R83 a partial pane list closes no suspended tab
file: earmark/core.py
```old
            if partial_snapshot(snap):
                continue  # a snapshot that can't be whole closes nothing
```
```new
            if False:
                continue  # a snapshot that can't be whole closes nothing
```

### R83 a tab without panes means a partial list
file: earmark/core.py
```old
    return not snap["workspaces"] or any(tid not in tabs_with_panes for tid in snap["tabs"])
```
```new
    return not snap["workspaces"]
```

### R84 Ctrl+E before Ctrl+U
file: earmark/suspend.py
```old
        herdr.run("pane", "send-keys", pane_id, "ctrl+e", "ctrl+u")
```
```new
        herdr.run("pane", "send-keys", pane_id, "ctrl+u")
```

### R84 the periodic re-arm waits for an idle shell
file: earmark/suspend.py
```old
    if automatic and not untouched(session, pane_id, rec, pane, restart):
```
```new
    if False:
```
### R85 the placeholder drops queued keys
file: earmark/placeholder.py
```old
    discard_input(fd)  # an Enter queued since
```
```new
    pass  # an Enter queued since
```

### R86 a clock jump stops the check
file: earmark/suspend.py
```old
        if time.time() - last > AWAY_GAP:  # the machine slept mid-check
```
```new
        if False:  # the machine slept mid-check
```

### R86 a config broken mid-check stops it
file: earmark/suspend.py
```old
            if cfg.get("_broken") or cfg["suspend"]["when"] != mode:
```
```new
            if cfg["suspend"]["when"] != mode:
```

### R86 a wake-up due while asleep is pushed back
file: earmark/suspend.py
```old
        return max(0, away[1] - max(away[0], since))
```
```new
        return 0
```
### R86 the absence is recorded
file: earmark/core.py
```old
                    s["away"] = [s["last_event"], t]
```
```new
                    pass
```

### R87 a missing Claude record refuses automatic suspends
file: earmark/suspend.py
```old
    elif found.get("agent") == "claude" and not found.get("registry"):
```
```new
    elif False:
```

### R87 an unreadable start time fails identity
file: earmark/suspend.py
```old
    if any(token is None for token in out["tokens"].values()):
```
```new
    if False:
```

### R88 the session wait is bounded
file: earmark/core.py
```old
    for _ in range(int(SESSION_WAIT / 0.4) + 1):  # bounded
```
```new
    for _ in iter(int, 1):  # bounded
```

### R88 a file another reader set aside
file: earmark/store.py
```old
        except FileNotFoundError:
            pass  # another reader set it aside first
```
```new
        except IsADirectoryError:
            pass  # another reader set it aside first
```

<!-- Strict review 5: the fit reviewer's own mutations. -->

### r5-fit: store: damaged file not set aside
file: earmark/store.py
```old
            os.replace(path, aside if n == 1 else f"{aside}-{n}")
```
```new
            pass
```

### r5-fit: store: shared lock for read-modify-write
file: earmark/store.py
```old
    with os.fdopen(fd, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield

```
```new
    with os.fdopen(fd, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            yield

```

### r5-fit: store: state dir world-readable
file: earmark/store.py
```old
        "herdr", "plugins", "io.github.cwilliams5.earmark")
    os.makedirs(path, mode=0o700, exist_ok=True)
```
```new
        "herdr", "plugins", "io.github.cwilliams5.earmark")
    os.makedirs(path, mode=0o755, exist_ok=True)
```

### r5-fit: store: malformed archive entries kept
file: earmark/store.py
```old
    data["entries"] = {k: v for k, v in entries.items() if _valid(v, ENTRY_KEYS)}
```
```new
    data["entries"] = dict(entries)
```

### r5-fit: herdr: failed notify counts as shown
file: earmark/herdr.py
```old
    except HerdrError:
        return False
    shown
```
```new
    except HerdrError:
        return True
    shown
```

### r5-fit: herdr: dotted table lookup broken
file: earmark/herdr.py
```old
            for part in table.split("."):
```
```new
            for part in [table]:
```

### r5-fit: config: quote tracking in comments
file: earmark/config.py
```old
        elif ch == '"':
            in_string = not in_string
```
```new
        elif ch == '"':
            in_string = in_string
```

### r5-fit: config: memory_below 95 accepted
file: earmark/config.py
```old
    if _int(raw.get("memory_below"), 1, 90):
```
```new
    if _int(raw.get("memory_below"), 1, 99):
```

### r5-fit: core: notes record the sleep mark
file: earmark/core.py
```old
                "tab_label": _unmarked(tab.get("label"), p.get("tab_id"), marked),
```
```new
                "tab_label": tab.get("label") or "",
```

### r5-fit: core: unmark leaves a space
file: earmark/core.py
```old
    return label[len(mark) + 1:] if mark and label.startswith(mark + " ") else label
```
```new
    return label[len(mark):] if mark and label.startswith(mark + " ") else label
```

### r5-fit: core: resume grace x10
file: earmark/core.py
```old
        elif state == "waking" and t - since > suspend.RESUME_GRACE:
```
```new
        elif state == "waking" and t - since > suspend.RESUME_GRACE * 10:
```

### r5-fit: core: boot grace in ms
file: earmark/core.py
```old
    return max(BOOT_GRACE, 30 + n_panes * max(0.0, delay) / 1000)
```
```new
    return max(BOOT_GRACE, 30 + n_panes * max(0.0, delay))
```

### r5-fit: core: contentless sessions archived
file: earmark/core.py
```old
    if facts["known"] and not (facts["exists"] and facts["has_content"]):
        return False
    key
```
```new
    if facts["known"] and not facts["exists"]:
        return False
    key
```

### r5-fit: core: last_active = close time
file: earmark/core.py
```old
        "last_active": facts["last_active"] or note.get("seen") or t,
```
```new
        "last_active": t,
```

### r5-fit: core: known sessions pruned after 30 days
file: earmark/core.py
```old
(0 if facts["known"] else config.FALLBACK_DAYS)
```
```new
(config.FALLBACK_DAYS if facts["known"] else config.FALLBACK_DAYS)
```

### r5-fit: core: closed workspaces aged in hours
file: earmark/core.py
```old
        if days and t - closed[key].get("closed_at", t) > days * 86400:
```
```new
        if days and t - closed[key].get("closed_at", t) > days * 3600:
```

### r5-fit: core: listing oldest first
file: earmark/core.py
```old
    return sorted(rows, key=lambda e: e.get("last_active") or 0, reverse=True)
```
```new
    return sorted(rows, key=lambda e: e.get("last_active") or 0)
```

### r5-fit: core: duplicate secondary name kept
file: earmark/core.py
```old
    if secondary.strip().lower() == primary.strip().lower():
        secondary = ""
```
```new
    if False:
        secondary = ""
```

### r5-fit: core: numbered tabs count as named
file: earmark/core.py
```old
    return not label or label == "Initial" or label.isdigit() or (number is not None and label == str(number))
```
```new
    return not label or label == "Initial" or (number is not None and label == str(number))
```

### r5-fit: suspend: count keeps one fewer
file: earmark/suspend.py
```old
        keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"]]}
```
```new
        keep = {item[0]["pane_id"] for item in recent[:max(0, scfg["keep_awake"] - 1)]}
```

### r5-fit: suspend: auto looks at everyone (cost)
file: earmark/suspend.py
```old
    soonest = cfg["suspend"]["idle_minutes"] * 60 if mode == "time" else QUIET
```
```new
    soonest = 0
```

### r5-fit: suspend: leader is the first process
file: earmark/suspend.py
```old
    leader = next((x for x in running if x["pid"] == group), running[0])
```
```new
    leader = running[0]
```

### r5-fit: suspend: short drafts ignored
file: earmark/suspend.py
```old
    if draft:
        return "there's unsent text in its prompt"
```
```new
    if draft and len(draft) > 3:
        return "there's unsent text in its prompt"
```

### r5-fit: suspend: unseen never recorded
file: earmark/suspend.py
```old
        "unseen": p.get("agent_status") == "done",
```
```new
        "unseen": False,
```

### r5-fit: suspend: stop wait trusts the shell alone
file: earmark/suspend.py
```old
            if back and procs.start_token(found["pid"]) is None:
                break
```
```new
            if back:
                break
```

### r5-fit: suspend: tab marked twice
file: earmark/suspend.py
```old
        if tab_id and label and not label.startswith(mark + " "):
```
```new
        if tab_id and label:
```

### r5-fit: suspend: stale mark taken off a sleeping tab
file: earmark/suspend.py
```old
        if tab is None or tid in asleep:
            continue
```
```new
        if tab is None:
            continue
```

### r5-fit: suspend: rearm_all spins to its deadline
file: earmark/suspend.py
```old
        if not pending:
            return
        try:
```
```new
        if not pending:
            time.sleep(1)
            continue
        try:
```

### r5-fit: suspend: any claude counts as resumed
file: earmark/suspend.py
```old
    return True if listed(p, rec) else False
```
```new
    return True
```

### r5-fit: suspend: view resume repeats Enter
file: earmark/suspend.py
```old
        if not rec or rec.get("state") != "suspended" or time.time() - rec.get("enter_sent", 0) < 5:
```
```new
        if not rec or rec.get("state") != "suspended":
```

### r5-fit: suspend: worker log never rotated
file: earmark/suspend.py
```old
        if os.path.getsize(path) > 256 * 1024:
```
```new
        if os.path.getsize(path) > 256 * 1024 ** 3:
```

### r5-fit: suspend: own pane counts as elsewhere
file: earmark/suspend.py
```old
        if pid != pane_id and ref.get("value") and f"{ref.get('agent') or p.get('agent')}:{ref['value']}" == key:
```
```new
        if ref.get("value") and f"{ref.get('agent') or p.get('agent')}:{ref['value']}" == key:
```

### r5-fit: suspend: old asks never pruned
file: earmark/suspend.py
```old
        for pid in [pid for pid, a in asks.items() if a.get("until", 0) < t]:
```
```new
        for pid in []:
```

### r5-fit: placeholder: LF no longer resumes
file: earmark/placeholder.py
```old
ENTER = re.compile(rb"[\r\n]|\x1b\[13(;1(:1)?)?u")
```
```new
ENTER = re.compile(rb"\r|\x1b\[13(;1(:1)?)?u")
```

### r5-fit: placeholder: frozen view on a tiny pane
file: earmark/placeholder.py
```old
    if lines and rows >= 6 and cols >= 30:
```
```new
    if lines and rows >= 1 and cols >= 1:
```

### r5-fit: placeholder: crop one column over
file: earmark/placeholder.py
```old
        if used + w > cols:
            break
```
```new
        if used + w > cols + 1:
            break
```

### r5-fit: text: fit no room for the ellipsis
file: earmark/text.py
```old
        if used + char_cols(ch) > width - 1:  # leave a column for …
```
```new
        if used + char_cols(ch) > width:  # leave a column for …
```

### r5-fit: ui: Enter confirms forget
file: earmark/ui.py
```old
            if key in ("y", "Y"):
                self.do_forget(key_to_forget)
```
```new
            if key in ("y", "Y", "\n", "\r"):
                self.do_forget(key_to_forget)
```

### r5-fit: ui: Esc keeps the filter text
file: earmark/ui.py
```old
                self.filtering, self.filter = False, ""
```
```new
                self.filtering = False
```

### r5-fit: ui: small-popup guard too small
file: earmark/ui.py
```old
        if h < 5 or w < 40:
```
```new
        if h < 3 or w < 10:
```

### r5-fit: ui: no forget mark drawn
file: earmark/ui.py
```old
        put(scr, y, w - FORGET_COL, " ×", attr)
```
```new
        pass
```

### r5-fit: message: body cut to full height
file: earmark/message.py
```old
    room = max(1, height - 2 - len(out))
```
```new
    room = max(1, height - len(out))
```

### r5-fit: message: popup not focused
file: earmark/message.py
```old
                  "--focus" if (focus or ask) else "--no-focus",
```
```new
                  "--no-focus",
```
### r5-fit: procs: name cut at first paren
file: earmark/procs.py
```old
            name = stat[stat.find("(") + 1:stat.rfind(")")]
```
```new
            name = stat[stat.find("(") + 1:stat.find(")")]
```

### r5-fit: procs: environment without the var unreadable
file: earmark/procs.py
```old
    return None if env is None else env.get(name, "")
```
```new
    return None if env is None else env.get(name)
```

### r5-fit: procs: swap not counted
file: earmark/procs.py
```old
                    if line.startswith(("VmRSS:", "VmSwap:")):
```
```new
                    if line.startswith(("VmRSS:",)):
```

### r5-fit: agents: codex folder suffix kept
file: earmark/agents.py
```old
    if agent == "codex" and " | " in title:
        title = title.rsplit(" | ", 1)[0].strip()
```
```new
    if False:
        title = title.rsplit(" | ", 1)[0].strip()
```

### r5-fit: agents: long transcripts have no content
file: earmark/agents.py
```old
                if n >= max_lines:
                    return True
```
```new
                if n >= max_lines:
                    return False
```

### r5-fit: agents: empty config dir falls to env
file: earmark/agents.py
```old
    if config_dir == "":
        return os.path.expanduser("~/.claude")
```
```new
    if False:
        return os.path.expanduser("~/.claude")
```

### r5-fit: agents: options after -- read
file: earmark/agents.py
```old
        if arg == "--":
            break  # everything after is the prompt
```
```new
        if arg == "--":
            i += 1
            continue
```

### r5-fit: agents: one dash is a rule
file: earmark/agents.py
```old
    return run > 0 and (run >= 3 or not t[run:].strip())
```
```new
    return run > 0
```

### r5-fit: agents: oldest codex db
file: earmark/agents.py
```old
    return max(dbs, key=number) if dbs else None
```
```new
    return min(dbs, key=number) if dbs else None
```

### r5-fit: entry: key suspends the hook's pane, not the focused one
file: earmark.py
```old
    pane_id = ctx.get("focused_pane_id") or os.environ.get("HERDR_PANE_ID")
```
```new
    pane_id = os.environ.get("HERDR_PANE_ID") or ctx.get("focused_pane_id")
```

### r5-fit: entry: startup hook misread
file: earmark.py
```old
    event = os.environ.get("HERDR_PLUGIN_EVENT") or "startup"
```
```new
    event = os.environ.get("HERDR_PLUGIN_EVENT") or "pane.focused"
```

### r5-fit: entry: worker ignores --rearm
file: earmark.py
```old
                   rearm="--rearm" in args, accept=_arg(args, "--accept"), pressed=pressed,
```
```new
                   rearm=False, accept=_arg(args, "--accept"), pressed=pressed,
```
### r5-fit: entry: worker drops the accepted doubt
file: earmark.py
```old
                   rearm="--rearm" in args, accept=_arg(args, "--accept"), pressed=pressed,
```
```new
                   rearm="--rearm" in args, accept=None, pressed=pressed,
```
### r5-fit: entry: placeholder ignores --state
file: earmark.py
```old
        if option == "--state":
            os.environ["HERDR_PLUGIN_STATE_DIR"] = value
```
```new
        if option == "--state":
            pass
```

### r5-fit: entry: open-workspaces opens sessions
file: earmark.py
```old
              "--env", f"EARMARK_VIEW={view}")
```
```new
              "--env", "EARMARK_VIEW=sessions")
```

### r5-fit: message: question times out like a message
file: earmark/message.py
```old
        if read_answer(fd, ASK_WAIT, echo=echoed) != "y":
```
```new
        if read_answer(fd, SHOW_WAIT, echo=echoed) != "y":
```
### r5-fit: message: question sent as a plain message
file: earmark/message.py
```old
    if ask:
        payload["ask"] = ask
```
```new
    if False:
        payload["ask"] = ask
```

### r5-fit: message: y hands an empty doubt to the worker
file: earmark/message.py
```old
                                 "--accept", str(ask.get("why")), "--pressed", repr(time.time())]):
```
```new
                                 "--accept", "", "--pressed", repr(time.time())]):
```

### r5-fit: placeholder: EOF spins
file: earmark/placeholder.py
```old
            if not data:
                return "hangup"
```
```new
            if not data:
                continue
```

### r5-fit: placeholder: unseen text swapped
file: earmark/placeholder.py
```old
    state = (f"Finished while you were away, not read yet · suspended {when}" if rec.get("unseen")
```
```new
    state = (f"Finished while you were away, not read yet · suspended {when}" if not rec.get("unseen")
```

### r5-fit: placeholder: notice drops the second name
file: earmark/placeholder.py
```old
    if other:
        block.insert(1, (DIM, fit(other, cols - 2)))
```
```new
    if False:
        block.insert(1, (DIM, fit(other, cols - 2)))
```

### r5-fit: placeholder: trailing blank lines kept
file: earmark/placeholder.py
```old
    while lines and not agents.plain(lines[-1]).strip():
        lines.pop()
```
```new
    while False:
        lines.pop()
```

### r5-fit: placeholder: raw name in the OSC title
file: earmark/placeholder.py
```old
    sys.stdout.write(f"\x1b]2;{fit('Suspended: ' + name, 80)}\x07")
```
```new
    sys.stdout.write(f"\x1b]2;Suspended: {name}\x07")
```

### r5-fit: ui: a always shows all
file: earmark/ui.py
```old
            self.all = not self.all
```
```new
            self.all = True
```

### r5-fit: ui: reopen leaves the sidebar count stale
file: earmark/ui.py
```old
        core.update_counts(self.session)
        return True  # the restored tabs have focus
```
```new
        return True  # the restored tabs have focus
```

### r5-fit: ui: PgDn moves one row
file: earmark/ui.py
```old
            self.sel = min(len(self.rows) - 1, self.sel + 10)
```
```new
            self.sel = min(len(self.rows) - 1, self.sel + 1)
```

### r5-fit: ui: double-click leaves the popup open
file: earmark/ui.py
```old
            self.sel = n
            return self.do_open()
```
```new
            self.sel = n
            self.do_open()
            return False
```

### r5-fit: ui: forget in workspaces view forgets a session
file: earmark/ui.py
```old
        if self.view == "workspaces":
            core.forget_workspace(key)
```
```new
        if self.view == "workspaces":
            core.forget(key)
```

### r5-fit: ui: workspace filter ignores tab names
file: earmark/ui.py
```old
                rows = [r for r in rows if needle in r["label"].lower()
                        or any(needle in (tb.get("label") or "").lower() for tb in r.get("tabs") or [])]
```
```new
                rows = [r for r in rows if needle in r["label"].lower()]
```

### r5-fit: text: C1 controls pass
file: earmark/text.py
```old
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
```
```new
_CONTROL = re.compile(r"[\x00-\x1f]")
```

### r5-fit: procs: macOS names keep the path
file: earmark/procs.py
```old
                names[int(parts[0])] = (int(parts[1]), os.path.basename(parts[2].strip()))
```
```new
                names[int(parts[0])] = (int(parts[1]), parts[2].strip())
```

### r5-fit: procs: macOS etime parsed wrong
file: earmark/procs.py
```old
            seconds = seconds * 60 + int(part)
```
```new
            seconds = seconds + int(part)
```

### r5-fit: procs: login shells not busy
file: earmark/procs.py
```old
                if name.lstrip("-") in SHELLS or "shell-snapshots" in cmd:
```
```new
                if name in SHELLS or "shell-snapshots" in cmd:
```

### r5-fit: agents: meta records count as prompts
file: earmark/agents.py
```old
    if record.get("type") != "user" or record.get("isMeta"):
```
```new
    if record.get("type") != "user":
```

### r5-fit: agents: one-shot tasks pending for ever
file: earmark/agents.py
```old
    return sum(1 for c in cache["created"].values() if c.get("recurring") or c.get("stamp", 0) > one_shot_after)
```
```new
    return sum(1 for c in cache["created"].values())
```

### r5-fit: agents: '+' options take one value
file: earmark/agents.py
```old
                while i < len(args) and not args[i].startswith("-"):
                    words.append(args[i])
                    i += 1
```
```new
                if i < len(args) and not args[i].startswith("-"):
                    words.append(args[i])
                    i += 1
```

### r5-fit: agents: grok one message has content
file: earmark/agents.py
```old
    return {"known": True, "exists": True, "has_content": bool(title) or messages >= 2,
```
```new
    return {"known": True, "exists": True, "has_content": bool(title) or messages >= 1,
```

### r5-fit: herdr: missing cwd passed to tab create
file: earmark/herdr.py
```old
    if cwd and os.path.isdir(cwd):
        args += ["--cwd", cwd]
```
```new
    if cwd:
        args += ["--cwd", cwd]
```

### r5-fit: herdr: screen read from recent output
file: earmark/herdr.py
```old
    source = ["--source", "recent", "--lines", str(int(rows))] if rows else ["--source", "visible"]
```
```new
    source = ["--source", "recent"] if rows else ["--source", "visible"]
```

### r5-fit: store: debug log world-readable
file: earmark/store.py
```old
    fd = os.open(os.path.join(state_dir(), "events.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
```
```new
    fd = os.open(os.path.join(state_dir(), "events.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
```

### r5-fit: store: try_lock blocks
file: earmark/store.py
```old
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
```
```new
            fcntl.flock(f, fcntl.LOCK_EX)
```

### r5-fit: core: session wait never ends early
file: earmark/core.py
```old
        if (p.get("agent_session") or {}).get("value") or not p.get("agent"):
            return
        time.sleep(0.4)
```
```new
        time.sleep(0.4)
```

### r5-fit: core: debug log always on
file: earmark/core.py
```old
    if cfg["debug_log"]:
        store.debug_log(
```
```new
    if True:
        store.debug_log(
```

### r5-fit: core: config dir looked up every hook
file: earmark/core.py
```old
            if note.get("config_dir") is not None or t - note.get("config_dir_tried", 0) < CONFIG_DIR_RETRY:
```
```new
            if note.get("config_dir") is not None:
```

### r5-fit: core: suspended tab's folder not kept in layouts
file: earmark/core.py
```old
            "cwd": (source.get("cwd") if agent_pane and agent_pane["pane_id"] in suspended else None)
```
```new
            "cwd": None
```

### r5-fit: core: empty workspace recorded
file: earmark/core.py
```old
    if not layout.get("tabs"):
        return False
    key = f"{session}|{wid}|{int(t)}"
```
```new
    key = f"{session}|{wid}|{int(t)}"
```

### r5-fit: core: tab name beats pane name
file: earmark/core.py
```old
    if entry.get("pane_label"):
        return entry["pane_label"]
```
```new
    if False:
        return entry["pane_label"]
```

### r5-fit: suspend: login shell refused
file: earmark/suspend.py
```old
    shell_name = (table.procs.get(shell) or (0, "", ""))[1].lstrip("-")
```
```new
    shell_name = (table.procs.get(shell) or (0, "", ""))[1]
```

### r5-fit: suspend: line goes into history
file: earmark/suspend.py
```old
    return f" {placeholder} && {resume_command(rec)}"
```
```new
    return f"{placeholder} && {resume_command(rec)}"
```

### r5-fit: suspend: resume forgets the folder
file: earmark/suspend.py
```old
        parts.append("cd " + shlex.quote(rec["cwd"]))
```
```new
        pass
```

### r5-fit: suspend: screens shared across sessions
file: earmark/suspend.py
```old
    name = hashlib.sha256(f"{session}|{pane_id}".encode()).hexdigest()[:16]
```
```new
    name = hashlib.sha256(f"{pane_id}".encode()).hexdigest()[:16]
```

### r5-fit: suspend: worker log world-readable
file: earmark/suspend.py
```old
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
```
```new
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
```

<!-- Strict review 5: the safety reviewer's own mutations. -->

### r5-safety: arm in-view check gone (first)
file: earmark/suspend.py
```old
    if snap is not None and focused_tab_of(snap) == pane.get("tab_id"):
        return False  # the user may be typing there
```
```new
    if False:
        return False
```

### r5-safety: registry busy ignored
file: earmark/suspend.py
```old
    if registry.get("status") not in (None, "idle"):
```
```new
    if False:
```

### r5-safety: remote control ignored
file: earmark/suspend.py
```old
    if registry.get("remote"):
        return "Remote Control is on"
```
```new
    if False:
        return "Remote Control is on"
```

### r5-safety: record-changed check before stop gone
file: earmark/suspend.py
```old
    if not current or current.get("state") != "stopping" or current.get("at") != t:
```
```new
    if not current:
```

### r5-safety: placeholder discard_input gone
file: earmark/placeholder.py
```old
    discard_input(fd)  # an Enter queued since
```
```new
    pass  # discard_input(fd)  # an Enter queued since
```

### r5-safety: mark_waking open-elsewhere ignored
file: earmark/suspend.py
```old
        if _open_elsewhere(rec or fallback, pane_id, snap):
```
```new
        if False:
```

### r5-safety: settle partial snapshot closes suspended
file: earmark/core.py
```old
            if partial_snapshot(snap):
                continue  # a snapshot that can't be whole closes nothing
```
```new
            if False:
                continue
```

### r5-safety: settle boot guard for suspended gone
file: earmark/core.py
```old
                    and rec.get("seen_at", 0) < flags.get("boot", 0):
                continue  # right after a restart
```
```new
                    and False:
                continue  # right after a restart
```

### r5-safety: chain is whole fg group
file: earmark/suspend.py
```old
    group = {x["pid"] for x in running}
    chain, pid = [main], main
```
```new
    return [x["pid"] for x in running]
    chain, pid = [main], main
```

### r5-safety: wake_on_view focus re-check gone
file: earmark/suspend.py
```old
        if not herdr.pane(pane_id).get("focused"):
            return
```
```new
        if False:
            return
```

### r5-safety: confirm min gone
file: earmark/suspend.py
```old
CONFIRM_MIN = 1  
```
```new
CONFIRM_MIN = 0  
```

### r5-safety: confirm why compare gone
file: earmark/suspend.py
```old
and ask.get("why") == why
```
```new

```

### r5-safety: unknown status doubt gone
file: earmark/suspend.py
```old
    if p.get("agent_status") not in ("idle", "done"):
        doubts.append
```
```new
    if False:
        doubts.append
```

### r5-safety: quiet_until ignored
file: earmark/suspend.py
```old
    if t < s.get("quiet_until", 0):
```
```new
    if False:
```

### r5-safety: clock jump in check ignored
file: earmark/suspend.py
```old
        if time.time() - last > AWAY_GAP:
```
```new
        if False:
```

### r5-safety: settings change mid-check ignored
file: earmark/suspend.py
```old
            if cfg.get("_broken") or cfg["suspend"]["when"] != mode:
```
```new
            if False:
```

### r5-safety: is_placeholder any session/pane
file: earmark/suspend.py
```old
            return session is None or argv[i + 2:i + 4] == [session, pane_id]
```
```new
            return True
```

### r5-safety: arm ignores listing
file: earmark/suspend.py
```old
    if listed(pane, rec):
        if not force or not wait_released(pane_id, rec.get("session_id")):
```
```new
    if False:
        if not force or not wait_released(pane_id, rec.get("session_id")):
```

### r5-safety: env_prefix untypable allowed
file: earmark/agents.py
```old
    if agent != "claude" or not config_dir or not os.path.isabs(config_dir) or UNTYPABLE.search(config_dir):
```
```new
    if agent != "claude" or not config_dir:
```

### r5-safety: drop_screen any path
file: earmark/suspend.py
```old
    if path and os.path.dirname(path) == store.screens_dir():
```
```new
    if path:
```

### r5-safety: timers behind ignored
file: earmark/suspend.py
```old
        if cache.get("behind"):
            out["timers"] = "Earmark hasn't read its whole transcript yet"
```
```new
        if False:
            out["timers"] = "Earmark hasn't read its whole transcript yet"
```

### r5-safety: timers slept ignored
file: earmark/suspend.py
```old
        elif wake and wake + TIMER_GRACE + pushed_back(cache, timers.get("_away"), wake) > t:
```
```new
        elif wake and wake + TIMER_GRACE > t:
```
### r5-safety: memory max per check gone
file: earmark/suspend.py
```old
            if len(chosen) >= MAX_PER_CHECK or available + freed
```
```new
            if False or available + freed
```

### r5-safety: give_up gone-agent arms placeholder dropped
file: earmark/suspend.py
```old
        if procs.start_token(found["pid"]) is None:
            if not signalled:
```
```new
        if False:
            if not signalled:
```
### r5-safety: settle stop_failed needs no agent
file: earmark/core.py
```old
            stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE
```
```new
            stop_failed = state == "stopping" and t - since > suspend.STOP_STALE
```

### r5-safety: open elsewhere other pane deletes without check
file: earmark/core.py
```old
        if panes - {pid} and runs_elsewhere():
            del suspended[pid]  # open somewhere else now
```
```new
        if panes - {pid} and runs_elsewhere():
            continue  # open somewhere else now
```
### r5-safety: note config dir none recorded
file: earmark/core.py
```old
            if value is not None:  # None: its environment couldn't be read; asked again later
```
```new
            if True:
```

### r5-safety: own_stop requires session match gone
file: earmark/core.py
```old
            own_stop = rec.get("session_id") == note.get("session_id") and (
```
```new
            own_stop = bool(rec) and (
```

### r5-safety: away gap never set
file: earmark/core.py
```old
                if s.get("last_event") and t - s["last_event"] > suspend.AWAY_GAP:
```
```new
                if False:
```

<!-- Strict review 5: one per fix (R93-R113). -->

### R93 a placeholder goes back only into the record's own tab
file: earmark/suspend.py
```old
            (snap is not None and not same_tab(session, rec, pane, snap)):
```
```new
            False:
```

### R93 the tab's name is compared
file: earmark/suspend.py
```old
            core._unmarked(tab.get("label"), pane.get("tab_id"), marked) != rec["tab_label"]:
```
```new
            False:
```

### R93 the workspace's name is compared
file: earmark/suspend.py
```old
    if rec.get("workspace_label") and ws and (ws.get("label") or "") != rec["workspace_label"]:
```
```new
    if False:
```

### R93 records follow their tab's renames
file: earmark/core.py
```old
                    if rec.get(k) != v:
                        rec[k] = v
```
```new
                    if False:
                        rec[k] = v
```

### R94 the machine's own sleep pushes a wake-up back
file: earmark/suspend.py
```old
        shift = max(shift, now_slept - then)
```
```new
        shift = shift
```

### R94 the sleep baseline is read with the call
file: earmark/agents.py
```old
                cache["wake_from"], cache["wake_slept"] = stamp, procs.suspended_seconds()
```
```new
                cache["wake_from"], cache["wake_slept"] = stamp, None
```

### R94 the key's look knows the absences too
file: earmark/suspend.py
```old
    timers = load_timers(session)
    timers["_away"] = s.get("away")
    found = look(p, note, procs.Table(), t, timers)
```
```new
    timers = load_timers(session)
    found = look(p, note, procs.Table(), t, timers)
```

### R95 the press's own time decides
file: earmark/suspend.py
```old
                                                                pressed or time.time()):
```
```new
                                                                time.time()):
```

### R96 Claude's registry confirms a listing elsewhere
file: earmark/core.py
```old
            return rec.get("agent") != "claude" or agents.claude_running(rec.get("session_id"), rec.get("config_dir"))
```
```new
            return True
```

### R96 the placeholder asks Claude's registry first
file: earmark/suspend.py
```old
    if rec.get("agent") == "claude":  # Claude's own registry knows; Herdr's listing can be stale
        return agents.claude_running(rec["session_id"], rec.get("config_dir"))
```
```new
    if False:
        return agents.claude_running(rec["session_id"], rec.get("config_dir"))
```

### R97 an unknown folder never drops the record
file: earmark/placeholder.py
```old
    if rec.get("config_dir") is not None and facts.get("known") and not facts.get("exists"):
```
```new
    if facts.get("known") and not facts.get("exists"):
```

### R98 gone before the signal is an exit
file: earmark/suspend.py
```old
            if not signalled:  # gone before Earmark stopped it
```
```new
            if False:  # gone before Earmark stopped it
```

### R99 no automatic stop without a pane in focus
file: earmark/suspend.py
```old
    if not manual and not any(x.get("focused") for x in snap["panes"].values()):
```
```new
    if False:
```

### R99 no automatic check without a pane in focus
file: earmark/suspend.py
```old
    if focused_tab is None:
        log(f"{session}: no pane is in focus
```
```new
    if False:
        log(f"{session}: no pane is in focus
```

### R100 NOT_YET remembers Herdr's listing
file: earmark/suspend.py
```old
            _set_state(session, pane_id, herdr_listed=True)  # its restore
```
```new
            pass  # its restore
```

### R101 hooks rearm outside the automatic modes
file: earmark/core.py
```old
                worker_args = ["--rearm-pass"]
```
```new
                worker_args = None
```

### R101 a restart ignores the start backoff
file: earmark/suspend.py
```old
        if not force and not restart and rec.get("arm_failed", 0) > t - BACKOFF:
```
```new
        if not force and rec.get("arm_failed", 0) > t - BACKOFF:
```

### R102 the popup's first moment doesn't answer
file: earmark/message.py
```old
        time.sleep(KEY_DELAY)  # a word being typed as the popup opened isn't an answer
        termios.tcflush(fd, termios.TCIFLUSH)
```
```new
        pass  # a word being typed as the popup opened isn't an answer
```

### R102 the draft is read again before the signal
file: earmark/suspend.py
```old
        draft = agents.draft_text(screen_of(now), found["agent"])
        if draft:
```
```new
        draft = ""
        if draft:
```

### R108 a config problem is logged
file: earmark/core.py
```old
                if cfg.get("_broken"):
                    suspend.log(f"{session}: config.toml has a problem
```
```new
                if False:
                    suspend.log(f"{session}: config.toml has a problem
```

### R108 the popup says the config has a problem
file: earmark/ui.py
```old
        if self.cfg.get("_broken"):  # said where the user looks
```
```new
        if False:  # said where the user looks
```

### R110 marks of closed tabs are forgotten
file: earmark/core.py
```old
            del s["marked"][tid]
```
```new
            pass
```

### R111 a late answer tries a toast
file: earmark/suspend.py
```old
    if (toast_mode(cfg) or late) and herdr.notify(title, body) is True:
```
```new
    if toast_mode(cfg) and herdr.notify(title, body) is True:
```
### R113 settle_now reads no archive for nothing
file: earmark/core.py
```old
            return  # nothing suspended: no need to read the archive
```
```new
            store.load_archive()
            return  # nothing suspended: no need to read the archive
```

### R113 the restore delay's default
file: earmark/core.py
```old
        delay = float(100 if value is None else value)  # Herdr's default is 100 ms
```
```new
        delay = float(0 if value is None else value)  # Herdr's default is 100 ms
```

### R113 the popup prunes once
file: earmark/ui.py
```old
            self.pruned = True
```
```new
            self.pruned = False
```

### R113 a missing revision fails closed
file: earmark/suspend.py
```old
    if shot is None:
        return False  # can't tell: the key decides
```
```new
    if shot is None:
        return True
```

<!-- Strict review 6: the fit reviewer's own mutations. -->

### r6-fit: core_seen_every_hook
file: earmark/core.py
```old
    if t - s.get("seen", 0) > 600:  # rewriting
```
```new
    if True:  # rewriting
```

### r6-fit: core_note_seen_fresh
file: earmark/core.py
```old
    if t - s.get("seen", 0) > 600:
```
```new
    if True:
```

### r6-fit: core_stamp_tab_in_view
file: earmark/core.py
```old
left = s.get("focused_tab") if s.get("focused_tab") != tab_now else None
```
```new
left = s.get("focused_tab")
```

### r6-fit: core_prune_every_hook
file: earmark/core.py
```old
if event == "startup" and not cfg.get("_broken"):
```
```new
if not cfg.get("_broken"):
```

### r6-fit: core_prune_cache_off
file: earmark/core.py
```old
        elif unchanged_since_last_look(e):
```
```new
        elif False:
```

### r6-fit: core_config_dir_retry_every_hook
file: earmark/core.py
```old
if note.get("config_dir") is not None or t - note.get("config_dir_tried", 0) < CONFIG_DIR_RETRY:
```
```new
if note.get("config_dir") is not None:
```

### r6-fit: core_boot_grace_fixed
file: earmark/core.py
```old
return max(BOOT_GRACE, 30 + n_panes * max(0.0, delay) / 1000)
```
```new
return BOOT_GRACE
```

### r6-fit: core_names_case
file: earmark/core.py
```old
if secondary.strip().lower() == primary.strip().lower():
```
```new
if secondary == primary:
```

### r6-fit: core_partial_no_workspaces
file: earmark/core.py
```old
return not snap["workspaces"] or any(
```
```new
return any(
```

### r6-fit: core_seen_at_every_hook
file: earmark/core.py
```old
if pid in snap["panes"] and (t - rec.get("seen_at", 0) >= 600 or rec.get("seen_at", 0) < (flags or {}).get("boot", 0)):
```
```new
if pid in snap["panes"]:
```

### r6-fit: core_rename_any_session
file: earmark/core.py
```old
if e["herdr_session"] == session and e["workspace_id"] == wid and e["workspace_label"] == old:
```
```new
if e["workspace_id"] == wid and e["workspace_label"] == old:
```

### r6-fit: core_listing_any_session
file: earmark/core.py
```old
            if e["herdr_session"] == session
            and (workspace_label is None
```
```new
            if True
            and (workspace_label is None
```

### r6-fit: core_closed_ws_any_session
file: earmark/core.py
```old
for k, w in archive.get("workspaces", {}).items() if w["herdr_session"] == session]
```
```new
for k, w in archive.get("workspaces", {}).items()]
```

### r6-fit: core_forget_session_1day
file: earmark/core.py
```old
> FORGET_SESSION_DAYS * 86400]
```
```new
> 86400]
```

### r6-fit: core_rearm_pass_every_hook
file: earmark/core.py
```old
elif not checks_run and t - s.get("rearm_checked", 0) >= suspend.CHECK_EVERY and any(
```
```new
elif not checks_run and any(
```

### r6-fit: suspend_dwell_zero
file: earmark/suspend.py
```old
    time.sleep(WAKE_DWELL)
```
```new
    pass
```

### r6-fit: suspend_enter_twice
file: earmark/suspend.py
```old
time.time() - rec.get("enter_sent", 0) < 5:
```
```new
time.time() - rec.get("enter_sent", 0) < 0:
```

### r6-fit: suspend_log_unbounded
file: earmark/suspend.py
```old
if os.path.getsize(path) > 256 * 1024:
```
```new
if False:
```

### r6-fit: suspend_no_ctrl_e
file: earmark/suspend.py
```old
herdr.run("pane", "send-keys", pane_id, "ctrl+e", "ctrl+u")
```
```new
herdr.run("pane", "send-keys", pane_id, "ctrl+u")
```

### r6-fit: suspend_say_none_is_shown
file: earmark/suspend.py
```old
and herdr.notify(title, body) is True:
```
```new
and herdr.notify(title, body) is not False:
```

### r6-fit: suspend_late_window
file: earmark/suspend.py
```old
LATE = 5  #
```
```new
LATE = 500  #
```

### r6-fit: suspend_count_keep_off_by_one
file: earmark/suspend.py
```old
for item in recent[:scfg["keep_awake"]]}
```
```new
for item in recent[:max(0, scfg["keep_awake"] - 1)]}
```

### r6-fit: suspend_memory_margin
file: earmark/suspend.py
```old
or available + freed >= scfg["memory_below"] + MEMORY_MARGIN:
```
```new
or available + freed >= scfg["memory_below"]:
```

### r6-fit: suspend_memory_fine_looks
file: earmark/suspend.py
```old
        return  # nothing to do: don't look at anyone
```
```new
        pass  # nothing to do: don't look at anyone
```

### r6-fit: suspend_settings_change_ignored
file: earmark/suspend.py
```old
if _mtime(config.config_path()) != settings_seen:
```
```new
if False:
```

### r6-fit: suspend_clock_jump_ignored
file: earmark/suspend.py
```old
if time.time() - last > AWAY_GAP:
```
```new
if False:
```

### r6-fit: suspend_placeholder_alive_skip
file: earmark/suspend.py
```old
        if placeholder_alive(rec):
            continue  # still up
```
```new
        if False:
            continue  # still up
```

### r6-fit: suspend_mark_empty_label
file: earmark/suspend.py
```old
if tab_id and label and not label.startswith(mark + " "):
```
```new
if tab_id and not label.startswith(mark + " "):
```

### r6-fit: suspend_unmark_asleep
file: earmark/suspend.py
```old
if tab is None or tid in asleep:
```
```new
if tab is None:
```

### r6-fit: suspend_is_placeholder_loose
file: earmark/suspend.py
```old
return session is None or argv[i + 2:i + 4] == [session, pane_id]
```
```new
return True
```

### r6-fit: suspend_bare_shell_any
file: earmark/suspend.py
```old
return me is None or (me.get("name") or "").lstrip("-") in SHELLS_OK
```
```new
return True
```

### r6-fit: suspend_shell_name_any
file: earmark/suspend.py
```old
if shell_name and shell_name not in SHELLS_OK:
```
```new
if False:
```

### r6-fit: suspend_resume_cd_unsafe
file: earmark/suspend.py
```old
    if shell_safe(rec.get("cwd")):
        parts.append("cd "
```
```new
    if rec.get("cwd"):
        parts.append("cd "
```

### r6-fit: suspend_stop_wait_short
file: earmark/suspend.py
```old
STOP_WAIT = 15 
```
```new
STOP_WAIT = 1 
```

### r6-fit: suspend_check_every_5s
file: earmark/suspend.py
```old
CHECK_EVERY = 60 
```
```new
CHECK_EVERY = 5 
```

### r6-fit: ph_wake_every_second
file: earmark/placeholder.py
```old
[], 60.5 - time.time() % 60)
```
```new
[], 1.0)
```

### r6-fit: ph_cursor_hidden
file: earmark/placeholder.py
```old
LEAVE_SCREEN = "\x1b[?2004l\x1b[0m\x1b[?25h\x1b[?1049l"
```
```new
LEAVE_SCREEN = "\x1b[?2004l\x1b[0m\x1b[?1049l"
```

### r6-fit: ph_dim_22
file: earmark/placeholder.py
```old
.replace("\x1b[22m", "\x1b[22m" + DIM)
```
```new
.replace("\x1b[22m", "\x1b[22m")
```

### r6-fit: ph_tiny_frozen
file: earmark/placeholder.py
```old
if lines and rows >= 6 and cols >= 30:
```
```new
if lines:
```

### r6-fit: ph_title_raw
file: earmark/placeholder.py
```old
{fit('Suspended: ' + name, 80)}
```
```new
{'Suspended: ' + name}
```

### r6-fit: ui_enter_forgets
file: earmark/ui.py
```old
            if key in ("y", "Y"):
                self.do_forget
```
```new
            if key in ("y", "Y", "\n"):
                self.do_forget
```

### r6-fit: ui_prune_each_key
file: earmark/ui.py
```old
if not self.pruned and not self.cfg.get("_broken")
```
```new
if not self.cfg.get("_broken")
```

### r6-fit: ui_small_guard
file: earmark/ui.py
```old
if h < 5 or w < 40:
```
```new
if h < 2 or w < 10:
```

### r6-fit: ui_forget_click_wide
file: earmark/ui.py
```old
        on_forget = x >= w - FORGET_COL - 1
```
```new
        on_forget = x >= w - FORGET_COL - 8
```

### r6-fit: store_no_lock
file: earmark/store.py
```old
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield

```
```new
        try:
            yield

```

### r6-fit: agents_sgr_operands
file: earmark/agents.py
```old
            i += 3 if mode == "5" else 5 if mode == "2" else 1
```
```new
            i += 2 if mode == "5" else 4 if mode == "2" else 1
```
### r6-fit: text_combining_one
file: earmark/text.py
```old
    if unicodedata.combining(ch):
        return 0
```
```new
    if unicodedata.combining(ch):
        return 1
```

### r6-fit: cfg_typo_not_broken
file: earmark/config.py
```old
    if problem:
        cfg["_broken"] = problem
```
```new
    if problem and data is None:
        cfg["_broken"] = problem
```

<!-- Strict review 6: one per fix (R114-R120). -->

### R114 a colon group is one attribute
file: earmark/agents.py
```old
        if ":" in p:
            i += 1
            continue
```
```new
        if False:
            i += 1
            continue
```

### R114 an empty parameter is a reset
file: earmark/agents.py
```old
        n = int(p) if p.isdigit() else 0
```
```new
        n = int(p) if p.isdigit() else -1
```

### R115 a big transcript is read on within the look
file: earmark/suspend.py
```old
        while cache.get("behind") and time.monotonic() < budget:
```
```new
        while False:
```

### R115 a line still being written ends the catch-up
file: earmark/suspend.py
```old
            if cache.get("offset") == before:
                break  # a line still being written
```
```new
            if False:
                break  # a line still being written
```

### R116 the parent-pid fallback expires
file: earmark/core.py
```old
        del s["ppid_unreliable"]  # give parent pids another chance
```
```new
        pass  # give parent pids another chance
```

### R118 a late popup doesn't take focus
file: earmark/suspend.py
```old
    message.show(title, body, focus=not late)
```
```new
    message.show(title, body)
```

### R118 the popup opens unfocused when asked
file: earmark/message.py
```old
                  "--focus" if (focus or ask) else "--no-focus",
```
```new
                  "--focus",
```

### R119 memory mode starts a worker only when memory is low
file: earmark/core.py
```old
                can_act = available is not None and available < scfg["memory_below"]
```
```new
                can_act = available is not None
```

### R119 the placeholder redraws only what changed
file: earmark/placeholder.py
```old
                if resized[0] or rows != drawn:
```
```new
                if True:
```

### R120 the popup wraps by columns
file: earmark/text.py
```old
        if cols(candidate) <= width:
```
```new
        if len(candidate) <= width:
```

<!-- Strict review 6: the safety reviewer's own mutations. -->

### r6-safety: r6s03 registry remote flag never read
file: earmark/agents.py
```old
            "remote": bool(data.get("bridgeSessionId")),
```
```new
            "remote": False,
```

### r6-safety: r6s04 registry status never read
file: earmark/agents.py
```old
    return {"status": data.get("status") if isinstance(data.get("status"), str) else None,
```
```new
    return {"status": None,
```

### r6-safety: r6s05 last look ignores blocked
file: earmark/suspend.py
```old
    if now.get("agent_status") in ("working", "blocked"):
```
```new
    if now.get("agent_status") == "working":
```

### r6-safety: r6s07 sleep never pushes a wake-up back
file: earmark/suspend.py
```old
    return max(0, shift)
```
```new
    return 0
```

### r6-safety: r6s08 tab number not compared on re-arm
file: earmark/suspend.py
```old
    if rec.get("tab_number") is not None and tab.get("number") is not None and tab["number"] != rec["tab_number"]:
```
```new
    if False:
```

### r6-safety: r6s09 record adopts tab names during the boot grace
file: earmark/core.py
```old
        if pid in snap["panes"] and not booting:
```
```new
        if pid in snap["panes"]:
```

### r6-safety: r6s11 restore guard ignores the pane's note
file: earmark/suspend.py
```old
    return bool(rec.get("herdr_listed")) or note.get("session_id") == rec.get("session_id")
```
```new
    return bool(rec.get("herdr_listed"))
```

### r6-safety: r6s12 one-shot scheduled tasks never pending
file: earmark/agents.py
```old
    return sum(1 for c in cache["created"].values() if c.get("recurring") or c.get("stamp", 0) > one_shot_after)
```
```new
    return sum(1 for c in cache["created"].values() if c.get("recurring"))
```

### r6-safety: r6s13 shell-snapshots command line not busy
file: earmark/procs.py
```old
                if name.lstrip("-") in SHELLS or "shell-snapshots" in cmd:
```
```new
                if name.lstrip("-") in SHELLS:
```

### r6-safety: r6s15 no Ctrl+E before Ctrl+U
file: earmark/suspend.py
```old
        herdr.run("pane", "send-keys", pane_id, "ctrl+e", "ctrl+u")  # to the line's end, then all of it
```
```new
        herdr.run("pane", "send-keys", pane_id, "ctrl+u")  # to the line's end, then all of it
```

### r6-safety: r6s17 open elsewhere at Enter: record dropped, not archived
file: earmark/suspend.py
```old
                core.archive_note(archive.setdefault("entries", {}), session, rec, time.time(), "exited")
```
```new
                pass
```

### r6-safety: r6s18 hangup resumes
file: earmark/placeholder.py
```old
    if action == "hangup":
```
```new
    if False:
```

### r6-safety: r6s19 a burst starting with y confirms
file: earmark/message.py
```old
            if typed and typed.lower() != "y":
                return ""
```
```new
            if typed.lower().startswith("y"):
                return "y"
```
### r6-safety: r6s23 subagent transcripts not looked at
file: earmark/agents.py
```old
                        if item.is_dir(follow_symlinks=False) and depth < 3:
```
```new
                        if item.is_dir(follow_symlinks=False) and depth < 0:
```

### r6-safety: r6s24 seen_at not refreshed after a restart
file: earmark/core.py
```old
        if pid in snap["panes"] and (t - rec.get("seen_at", 0) >= 600 or rec.get("seen_at", 0) < (flags or {}).get("boot", 0)):
```
```new
        if pid in snap["panes"] and (t - rec.get("seen_at", 0) >= 600):
```

### r6-safety: r6s25 Ctrl+C loses to Enter in one burst
file: earmark/placeholder.py
```old
    if CTRL_C.search(data):
```
```new
    if CTRL_C.search(data) and not ENTER.search(data):
```

### r6-safety: r6s26 the 'Try' fallback widened (any quoted draft)
file: earmark/agents.py
```old
            # could as well be typed: Earmark can't tell.
            return None
```
```new
            # could as well be typed: Earmark can't tell.
            return ""
```
### r6-safety: r6s27 arm claims a record that is still stopping
file: earmark/suspend.py
```old
        if not rec or rec.get("state") not in ("suspended", "waking"):
```
```new
        if not rec:
```

### r6-safety: r6s28 last look fails open with no pane in focus
file: earmark/suspend.py
```old
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None, p.get("tab_id"))
```
```new
    if not manual and (now.get("focused") or focused_tab_of(snap_now) == p.get("tab_id")
```

### r6-safety: r6s29 any note counts as Earmark's own stop
file: earmark/core.py
```old
                rec.get("state") == "stopping" or note.get("since", 0) <= rec.get("at", 0))
```
```new
                True)
```

### r6-safety: r6s30 record forgets the Claude folder
file: earmark/suspend.py
```old
"config_dir": found.get("config_dir"), "account"
```
```new
"config_dir": None, "account"
```

### r6-safety: r6s31 folder typed unquoted
file: earmark/suspend.py
```old
        parts.append("cd " + shlex.quote(rec["cwd"]))
```
```new
        parts.append("cd " + rec["cwd"])
```

### r6-safety: r6s33 resume runs whatever the placeholder says
file: earmark/suspend.py
```old
    return f" {placeholder} && {resume_command(rec)}"
```
```new
    return f" {placeholder} ; {resume_command(rec)}"
```

### r6-safety: r6s34 first parent change marks restarts unreliable
file: earmark/core.py
```old
        if len(recent) >= 3:
```
```new
        if len(recent) >= 1:
```

### r6-safety: r6s35 placeholder line without its state folder
file: earmark/suspend.py
```old
                              "--state", store.state_dir(), "--config", config.config_dir()])
```
```new
                              "--config", config.config_dir()])
```

<!-- Strict review 6: one per safety fix (R124-R134). -->

### R125 durable tasks keep it awake
file: earmark/suspend.py
```old
            if durable != 0:  # some, or a file Earmark can't read
```
```new
            if durable:  # some, or a file Earmark can't read
```

### R125 a durable task file is read
file: earmark/agents.py
```old
    return len(data) if isinstance(data, list) else None
```
```new
    return 0
```

### R126 the shell's folder is compared
file: earmark/suspend.py
```old
    if rec.get("shell_cwd") and pane.get("cwd") and pane["cwd"] != rec["shell_cwd"]:
```
```new
    if False:
```

### R126 the shell's folder is recorded
file: earmark/suspend.py
```old
        _set_state(session, pane_id, shell_cwd=pane.get("cwd"))
```
```new
        pass
```

### R126 a restart that brings back few panes is a new session
file: earmark/core.py
```old
        if len(known) >= 2 and len(back) * 2 < len(known) and not partial_snapshot(snap):
```
```new
        if False:
```

### R127 a shell used since it came back is left to the key
file: earmark/suspend.py
```old
    if base.get("used"):
        return False
```
```new
    if False:
        return False
```

### R128 only y then Enter answers
file: earmark/message.py
```old
            if ch in "\r\n":
                return "y" if typed.lower() == "y" else ""
```
```new
            if ch in "\r\n" or typed:
                return "y" if (typed or ch).strip().lower() == "y" else ""
```

### R129 an exit inside the grace is archived after it
file: earmark/core.py
```old
            elif pid in s.get("boot_panes", []) and t - s.get("boot", 0) >= grace(s):
```
```new
            elif False:
```

### R130 an odd snapshot reply is a HerdrError
file: earmark/herdr.py
```old
    except (TypeError, KeyError, AttributeError) as e:
        raise HerdrError(f"Herdr answered in a shape Earmark doesn't know ({e!r})")
```
```new
    except IndexError as e:
        raise HerdrError(f"Herdr answered in a shape Earmark doesn't know ({e!r})")
```

### R132 the last look sees new commands
file: earmark/suspend.py
```old
    busy = procs.Table().busy([found["pid"]])
```
```new
    busy = ""
```

### R132 the last look hears Claude
file: earmark/suspend.py
```old
        if registry.get("remote") or registry.get("status") not in (None, "idle"):
```
```new
        if False:
```

### R133 a Codex draft goes on over indented lines
file: earmark/agents.py
```old
            more.append(typed.strip())
```
```new
            pass
```

### R134 option values a shell would expand
file: earmark/agents.py
```old
            if any(UNTYPABLE.search(w) or w.startswith(("=", "%")) for w in words):
```
```new
            if any(UNTYPABLE.search(w) for w in words):
```

### R134 an unknown mode drops a bypass permission mode
file: earmark/agents.py
```old
            elif f == "--permission-mode" and flags[i + 1:i + 2] == ["bypassPermissions"]:
```
```new
            elif False:
```

<!-- Strict review 7: the re-arm rule in one place (R135-R138). -->

### R135 a placeholder seen up leaves no baseline behind
file: earmark/suspend.py
```old
        _set_state(session, pane_id, ph=[pid, token], base=None)  # a later loss starts a new baseline
```
```new
        _set_state(session, pane_id, ph=[pid, token])
```

### R135 a hook starts no pass for a shell someone used
file: earmark/suspend.py
```old
        not (rec.get("base") or {}).get("used")
```
```new
        True
```

### R136 the pass runs in every mode where no check runs
file: earmark/core.py
```old
            elif not checks_run and t - s.get("rearm_checked", 0) >= suspend.CHECK_EVERY and any(
```
```new
            elif scfg["when"] not in config.AUTO_MODES and t - s.get("rearm_checked", 0) >= suspend.CHECK_EVERY and any(
```

### R137 a finished slow stop asks for a restart re-arm
file: earmark/core.py
```old
            rec["state"], rec["at"] = "suspended", t  # the regular re-arm pass starts its placeholder
```
```new
            rec["state"], rec["at"] = "suspended", t; flags is not None and flags.update(rearm=True)
```

### R137 Ctrl+C before typing
file: earmark/suspend.py
```old
        herdr.run("pane", "send-keys", pane_id, "ctrl+c")
```
```new
        pass
```

### R138 after a restart a changing shell is watched again
file: earmark/suspend.py
```old
if not base or restart else dict(base, used=True))
```
```new
if not base else dict(base, used=True))
```

### R138 the untouched wait lasts STABLE seconds
file: earmark/suspend.py
```old
        return t - base.get("at", t) >= STABLE
```
```new
        return True
```

### R138 the revision is looked at again after the claim
file: earmark/suspend.py
```old
                (automatic and screen_print(dict(pane, pane_id=pane_id)) != (rec.get("base") or {}).get("screen")):
```
```new
                False:
```

### R138 a None field is removed, not stored
file: earmark/suspend.py
```old
                if v is None:
                    rec.pop(k, None)  # None removes the field: absent and None never mean two things
                else:
                    rec[k] = v
```
```new
                rec[k] = v
```

<!-- Strict review 7: launch-only account settings (R139). -->

### R139 look keeps the agent's account settings
file: earmark/suspend.py
```old
    out["account"] = agents.account_env(procs.environ(main["pid"]))  # None: unreadable
```
```new
    out["account"] = None
```

### R139 the record keeps them
file: earmark/suspend.py
```old
"account": found.get("account"),
```
```new
"account": None,
```

### R139 the placeholder compares before resuming
file: earmark/placeholder.py
```old
            changed = [] if warned else agents.account_changes(rec.get("account"), os.environ)
```
```new
            changed = []
```

### R139 the warning waits for a second Enter
file: earmark/placeholder.py
```old
                           "(another account or endpoint). Enter again resumes it anyway; Ctrl+C leaves it.")
                continue
```
```new
                           "(another account or endpoint). Enter again resumes it anyway; Ctrl+C leaves it.")
```

### R139 a setting only the shell has counts
file: earmark/agents.py
```old
    return sorted(k for k in set(recorded) | set(now) if recorded.get(k) != now.get(k))
```
```new
    return sorted(k for k in set(recorded) if recorded.get(k) != now.get(k))
```

### R139 prefixes count
file: earmark/agents.py
```old
            for k, v in env.items() if k in ACCOUNT_NAMES or k.startswith(ACCOUNT_PREFIXES)}
```
```new
            for k, v in env.items() if k in ACCOUNT_NAMES}
```

### R139 values are hashed, never kept
file: earmark/agents.py
```old
    return {k: hashlib.sha256(v.encode("utf-8", "surrogateescape")).hexdigest()[:16]
```
```new
    return {k: v
```

### R139 a long placeholder message wraps
file: earmark/placeholder.py
```old
            more = _text.wrap_cols(" ".join(said[1:]), cols - 2)[:3]
```
```new
            more = []
```

<!-- Strict review 7: R140-R149. -->

### R140 the last look refuses an unreadable prompt
file: earmark/suspend.py
```old
        if draft is None and UNREADABLE_PROMPT not in doubts:  # readable a moment ago, so not a doubt the user took
```
```new
        if False:
```

### R140 a doubt the user took holds at the last look
file: earmark/suspend.py
```old
        if draft is None and UNREADABLE_PROMPT not in doubts:  # readable a moment ago, so not a doubt the user took
```
```new
        if draft is None:
```

### R141 hooks write the archive first
file: earmark/core.py
```old
        if changed:
            store.save_archive(archive)
        if json.dumps(index, sort_keys=True) != before:
            store.save_index(index)
```
```new
        if json.dumps(index, sort_keys=True) != before:
            store.save_index(index)
        if changed:
            store.save_archive(archive)
```

### R141 settle_now writes the archive first
file: earmark/core.py
```old
        if changed:  # the archive first (see handle_event)
            store.save_archive(archive)
        if json.dumps(s["suspended"], sort_keys=True) != before:
            store.save_index(index)
```
```new
        if json.dumps(s["suspended"], sort_keys=True) != before:
            store.save_index(index)
        if changed:
            store.save_archive(archive)
```

### R142 a late question is said, not asked
file: earmark/suspend.py
```old
        elif pressed and time.time() - pressed > LATE:
```
```new
        elif False:
```

### R142 the question names the tab
file: earmark/suspend.py
```old
            message.show(f"Suspend {quoted(name)} anyway?" if name else "Suspend this tab anyway?",
```
```new
            message.show("Suspend this tab anyway?",
```

### R143 an unknown Claude folder is filed
file: earmark/core.py
```old
    if folder_unknown:
        # Its process's Claude folder couldn't be read, and the transcript
```
```new
    if False:
        # Its process's Claude folder couldn't be read, and the transcript
```

### R143 prune keeps it by keep_days
file: earmark/core.py
```old
        if e.get("folder_unknown"):
            facts = {"known": False}  # its Claude folder wasn't known: keep_days decides
        elif unchanged_since_last_look(e):
```
```new
        if unchanged_since_last_look(e):
```

### R144 the status clock only in automatic modes
file: earmark/core.py
```old
            if idle_clock and new.get("status") != p.get("agent_status"):
```
```new
            if new.get("status") != p.get("agent_status"):
```

### R144 the focus clock only in automatic modes
file: earmark/core.py
```old
    if idle_clock:
        focused = next((p for p in snap["panes"].values() if p.get("focused")), None)
```
```new
    if True:
        focused = next((p for p in snap["panes"].values() if p.get("focused")), None)
```

### R144 automatic modes keep the idle clock
file: earmark/core.py
```old
                        idle_clock=scfg["when"] in config.AUTO_MODES)
```
```new
                        idle_clock=False)
```

### R145 the forget question's buttons come first
file: earmark/ui.py
```old
            text = fit(text, w - 1 - buttons if w - 1 - buttons >= 16 else w - 1)  # the buttons before the words
```
```new
            text = fit(text, w - 1)
```

### R146 the message popup's height
file: herdr-plugin.toml
```old
width = "60%"
height = "50%"
```
```new
width = "60%"
height = "35%"
```

### R147 a plain message ignores the first moment's keys
file: earmark/message.py
```old
            time.sleep(KEY_DELAY)  # typing that went on after the press doesn't close it unread
            termios.tcflush(fd, termios.TCIFLUSH)
            read_key(fd, SHOW_WAIT)
```
```new
            read_key(fd, SHOW_WAIT)
```

### R148 the config folder follows XDG_CONFIG_HOME
file: earmark/config.py
```old
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
```
```new
        os.path.expanduser("~/.config"),
```

### R148 the state folder follows XDG_STATE_HOME
file: earmark/store.py
```old
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
```
```new
        os.path.expanduser("~/.local/state"),
```

### R149 a rewritten transcript forgets its mode
file: earmark/agents.py
```old
                cache.pop("mode", None)
            cache["head"] = head
```
```new
            cache["head"] = head
```

### R151 the automatic modes refuse what Earmark can't check
file: earmark/suspend.py
```old
        unsure = cant_check(found)
```
```new
        unsure = []
```

<!-- Strict review 7: the fit reviewer's own mutations (52). -->

### r7-fit: cost-index-before-empty
file: earmark/core.py
```old
before = json.dumps(index, sort_keys=True)
```
```new
before = ""
```

### r7-fit: cost-report-off-clears-every-hook
file: earmark/core.py
```old
sent = index["sessions"][session].pop("reported", None) or {}
```
```new
sent = index["sessions"][session].get("reported") or {}
```

### r7-fit: cost-config-problem-logged-every-hook
file: earmark/core.py
```old
if cfg.get("_broken") != s.get("config_problem"):
```
```new
if True:
```

### r7-fit: cost-config-dir-lookup-all-agents
file: earmark/core.py
```old
if (ref.get("agent") or p.get("agent")) != "claude" or not ref.get("value"):
```
```new
if not ref.get("value"):
```

### r7-fit: cost-prune-cache-off
file: earmark/core.py
```old
    cached = entry.get("file")
    if not cached:
        return False
```
```new
    cached = entry.get("file")
    if True:
        return False
```

### r7-fit: cost-title-glyph-kept
file: earmark/agents.py
```old
title = re.sub(r"^[^\w(\[\"'`]+", "", (title or "")).strip()
```
```new
title = (title or "").strip()
```

### r7-fit: cost-timers-keep-gone-sessions
file: earmark/suspend.py
```old
new = {k: v for k, v in timers.items() if keep is None or k in keep}
```
```new
new = dict(timers)
```

### r7-fit: cost-freed-not-counted
file: earmark/suspend.py
```old
freed += 100.0 * item[2].get("memory_kb", 0) / total_kb
```
```new
freed += 0
```

### r7-fit: rule-other-agents-activity-ignored
file: earmark/suspend.py
```old
    elif facts.get("last_active"):
        activity.append(facts["last_active"])
```
```new
    elif False:
        activity.append(facts["last_active"])
```

### r7-fit: rule-config-dir-not-read-from-process
file: earmark/suspend.py
```old
    if agent == "claude" and config_dir is None:
        config_dir = procs.environ_var
```
```new
    if False:
        config_dir = procs.environ_var
```

### r7-fit: rule-cwd-unsafe-ignored
file: earmark/suspend.py
```old
out["cwd_unsafe"] = not shell_safe(pane.get("foreground_cwd") or pane.get("cwd") or note.get("cwd") or "")
```
```new
out["cwd_unsafe"] = False
```

### r7-fit: rule-unreadable-durable-tasks-none
file: earmark/agents.py
```old
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
```
```new
    except (OSError, ValueError):
        return 0
    if isinstance(data, dict):
```

### r7-fit: rule-codex-hints-in-draft
file: earmark/agents.py
```old
if not typed.strip() or not typed.startswith("  ") or any(k in typed for k in ("⏎", "⌃")):
```
```new
if not typed.strip() or not typed.startswith("  "):
```

### r7-fit: rule-max-per-check
file: earmark/suspend.py
```old
MAX_PER_CHECK = 6 
```
```new
MAX_PER_CHECK = 60 
```

### r7-fit: resume-layout-loses-suspended-flags
file: earmark/core.py
```old
            entry["resume"] = suspended[agent_pane["pane_id"]]["resume"]  # its options and permission mode
```
```new
            pass
```

### r7-fit: notes-tab-name-lost-in-race
file: earmark/core.py
```old
if tab is None and note and note.get("tab_id") == p.get("tab_id"):
```
```new
if False:
```

### r7-fit: notes-workspace-label-fallback-lost
file: earmark/core.py
```old
"workspace_label": ws_labels.get(p.get("workspace_id"), (note or {}).get("workspace_label", "")),
```
```new
"workspace_label": ws_labels.get(p.get("workspace_id"), ""),
```

### r7-fit: notes-pane-name-lost
file: earmark/core.py
```old
"pane_label": p.get("label") or "",
```
```new
"pane_label": "",
```

### r7-fit: notes-title-fallback-lost
file: earmark/core.py
```old
"title": agents.clean_title(p.get("terminal_title"), agent) or (note or {}).get("title", ""),
```
```new
"title": agents.clean_title(p.get("terminal_title"), agent),
```

### r7-fit: notes-prune-titles-not-refreshed
file: earmark/core.py
```old
                    if facts[field] and facts[field] != e.get(field):
```
```new
                    if False:
```

### r7-fit: notes-marks-forgotten-while-booting
file: earmark/core.py
```old
if not partial and not booting and s.get("marked"):
```
```new
if s.get("marked"):
```

### r7-fit: restart-rearm-flag-dropped
file: earmark/core.py
```old
worker_args = ["--rearm"] if rearm else []
```
```new
worker_args = []
```

### r7-fit: restart-ppid-unreliable-forever
file: earmark/core.py
```old
else 0) > 6 * 3600:
```
```new
else 0) > 6 * 3600 * 10 ** 6:
```

### r7-fit: counts-sent-when-off
file: earmark/core.py
```old
    cfg = config.load()
    if not cfg["report_count"]:
        return
```
```new
    cfg = config.load()
    if False:
        return
```

### r7-fit: arm-line-safe-root-only
file: earmark/suspend.py
```old
paths = [ROOT, store.state_dir(), config.config_dir()] + ([sys.executable] if sys.executable else [])
```
```new
paths = [ROOT]
```

### r7-fit: arm-key-rearm-respects-backoff
file: earmark/suspend.py
```old
ok = arm(session, pane_id, force=True, view_ok=True)
```
```new
ok = arm(session, pane_id, force=False, view_ok=True)
```

### r7-fit: arm-rearm-pass-flag-ignored
file: earmark.py
```old
rearm_pass_only="--rearm-pass" in args)
```
```new
rearm_pass_only=False)
```

### r7-fit: msg-esc-doesnt-cancel
file: earmark/message.py
```old
if not key or b"\x1b" in key or b"\x03" in key:
```
```new
if not key:
```

### r7-fit: msg-backspace-ignored
file: earmark/message.py
```old
                typed = typed[:-1]
```
```new
                pass
```

### r7-fit: msg-confirm-inline-in-popup
file: earmark/message.py
```old
if suspend.spawn_worker(["--session", str(ask.get("session")), "--pane", str(ask.get("pane_id")),
```
```new
if False and suspend.spawn_worker(["--session", str(ask.get("session")), "--pane", str(ask.get("pane_id")),
```

### r7-fit: msg-no-fallback-toast
file: earmark/message.py
```old
    except herdr.HerdrError:
        herdr.notify(title, body)
        return False
```
```new
    except herdr.HerdrError:
        return False
```

### r7-fit: msg-show-wait-long
file: earmark/message.py
```old
SHOW_WAIT = 8 
```
```new
SHOW_WAIT = 800 
```

### r7-fit: cfg-messages-any-value
file: earmark/config.py
```old
if raw.get("messages") in ("popup", "toast"):
```
```new
if raw.get("messages"):
```

### r7-fit: herdr-notify-none-is-shown
file: earmark/herdr.py
```old
return shown if isinstance(shown, bool) else None
```
```new
return shown if isinstance(shown, bool) else True
```

### r7-fit: herdr-config-path-ignores-xdg
file: earmark/herdr.py
```old
os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
```
```new
os.path.expanduser("~/.config")
```

### r7-fit: fit-say-late-ignored
file: earmark/suspend.py
```old
late = bool(pressed) and time.time() - pressed > LATE
```
```new
late = False
```

### r7-fit: fit-confirm-window-long
file: earmark/suspend.py
```old
asks[pane_id] = {"why": why, "asked": t, "until": t + CONFIRM_WINDOW}
```
```new
asks[pane_id] = {"why": why, "asked": t, "until": t + 3600}
```

### r7-fit: ui-a-toggle-in-workspaces
file: earmark/ui.py
```old
elif key == "a" and self.view == "sessions":
```
```new
elif key == "a":
```

### r7-fit: ui-detail-squeezes-names
file: earmark/ui.py
```old
if w - FORGET_COL - cols(candidate) - 6 >= 16:
```
```new
if w - FORGET_COL - cols(candidate) - 6 >= 0:
```

### r7-fit: ui-filter-backspace-ignored
file: earmark/ui.py
```old
                self.filter = self.filter[:-1]
```
```new
                pass
```

### r7-fit: ui-keep-button-forgets
file: earmark/ui.py
```old
                        if name == "forget":
                            self.do_forget(key)
```
```new
                        if True:
                            self.do_forget(key)
```

### r7-fit: ph-tabs-not-expanded
file: earmark/placeholder.py
```old
for ch in CONTROL.sub("", text.replace("\t", "    ")):
```
```new
for ch in CONTROL.sub("", text):
```

### r7-fit: cfg-multiline-array-on-39
file: earmark/config.py
```old
while value.startswith("[") and "]" not in value and n < len(lines):
```
```new
while False:
```

### r7-fit: counts-gone-workspaces-kept
file: earmark/core.py
```old
    for wid in [wid for wid in sent if wid not in snap["workspaces"]]:
        del sent[wid]
```
```new
    for wid in [wid for wid in sent if wid not in snap["workspaces"]]:
        pass
```

### r7-fit: title-grok-suffix-kept
file: earmark/agents.py
```old
    if agent and title.lower().endswith(f" - {agent.lower()}"):
```
```new
    if False:
```

### r7-fit: facts-codex-deleted-rollout-exists
file: earmark/agents.py
```old
exists = not rollout or os.path.exists(rollout)
```
```new
exists = True
```

### r7-fit: ui-q-doesnt-close
file: earmark/ui.py
```old
        if key in ("q", "\x1b"):
```
```new
        if key in ("\x1b",):
```

### r7-fit: ui-mouse-off
file: earmark/ui.py
```old
curses.mousemask(curses.ALL_MOUSE_EVENTS)
```
```new
curses.mousemask(0)
```

### r7-fit: herdr-screen-crlf-kept
file: earmark/herdr.py
```old
return out.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
```
```new
return out.stdout.decode("utf-8", "replace")
```

### r7-fit: cfg-bad-resume-entries-used
file: earmark/config.py
```old
cfg["resume"] = {k: v for k, v in resume.items() if _resume_ok(v)}
```
```new
cfg["resume"] = dict(resume)
```

### r7-fit: msg-long-word-cut-once
file: earmark/text.py
```old
        while cols(word) > width:
```
```new
        if cols(word) > width:
```

<!-- Strict review 7: the safety reviewer's own mutations (146). -->

### r7-safety: last look: focused flag of the pane itself ignored
file: earmark/suspend.py
```old
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None, p.get("tab_id"))
```
```new
    if not manual and (False or focused_tab_of(snap_now) in (None, p.get("tab_id"))
```

### r7-safety: last look: no-focus (None) no longer stops
file: earmark/suspend.py
```old
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None, p.get("tab_id"))
```
```new
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (p.get("tab_id"),)
```

### r7-safety: last look: tab in view no longer stops (only no-focus does)
file: earmark/suspend.py
```old
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None, p.get("tab_id"))
```
```new
    if not manual and (now.get("focused") or focused_tab_of(snap_now) in (None,)
```

### r7-safety: last look: blocked no longer stops
file: earmark/suspend.py
```old
    if now.get("agent_status") in ("working", "blocked"):
```
```new
    if now.get("agent_status") in ("working",):
```

### r7-safety: last look: remote control re-check dropped
file: earmark/suspend.py
```old
        if registry.get("remote") or registry.get("status") not in (None, "idle"):
```
```new
        if registry.get("status") not in (None, "idle"):
```

### r7-safety: last look: registry busy re-check dropped
file: earmark/suspend.py
```old
        if registry.get("remote") or registry.get("status") not in (None, "idle"):
```
```new
        if registry.get("remote"):
```

### r7-safety: record identity: state no longer compared
file: earmark/suspend.py
```old
    if not current or current.get("state") != "stopping" or current.get("at") != t:
```
```new
    if not current or current.get("at") != t:
```

### r7-safety: arm: first bare shell check dropped
file: earmark/suspend.py
```old
    if not bare_shell(info):
        return False  # something else runs there: no claim, no write
```
```new
    if False:
        return False  # something else runs there: no claim, no write
```

### r7-safety: arm: force skips waiting for release
file: earmark/suspend.py
```old
        if not force or not wait_released(pane_id, rec.get("session_id")):
```
```new
        if not force:
```

### r7-safety: arm: restart once-only ignored
file: earmark/suspend.py
```old
        if restart and rec.get("armed_by_rearm"):
            return False
```
```new
        if False:
            return False
```

### r7-safety: is_placeholder: options not checked
file: earmark/suspend.py
```old
            if len(rest) % 2 or any(opt not in ("--state", "--config") for opt in rest[::2]):
                return False
```
```new
            if False:
                return False
```

### r7-safety: is_placeholder: pane not compared
file: earmark/suspend.py
```old
            return session is None or argv[i + 2:i + 4] == [session, pane_id]
```
```new
            return session is None or argv[i + 2:i + 3] == [session]
```

### r7-safety: rearm_pass: waking grace ignored
file: earmark/suspend.py
```old
        if rec.get("state") == "waking" and time.time() - (rec.get("waking_at") or 0) < RESUME_GRACE:
```
```new
        if False:
```

### r7-safety: mark_waking: elsewhere record not archived
file: earmark/suspend.py
```old
                core.archive_note(archive.setdefault("entries", {}), session, rec, time.time(), "exited")
                store.save_archive(archive)
                store.save_index(index)
                drop_screen(rec)
            return "this session is open somewhere else already, so it isn't resumed here"
```
```new
                store.save_index(index)
                drop_screen(rec)
            return "this session is open somewhere else already, so it isn't resumed here"
```

### r7-safety: refusal: auto doesn't refuse unknown status
file: earmark/suspend.py
```old
        if status not in ("idle", "done"):
            return f"it's {status or 'not idle'}"
```
```new
        if status not in ("idle", "done", "unknown", None):
            return f"it's {status or 'not idle'}"
```

### r7-safety: refusal: registry 'shell' status allowed
file: earmark/suspend.py
```old
    if registry.get("status") not in (None, "idle"):
        return "it's working" if registry["status"] == "busy" else f"Claude says it's {registry['status']}"
```
```new
    if registry.get("status") == "busy":
        return "it's working" if registry["status"] == "busy" else f"Claude says it's {registry['status']}"
```

### r7-safety: choose: count mode keeps none
file: earmark/suspend.py
```old
        keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"]]}
```
```new
        keep = set()
```

### r7-safety: choose: memory margin ignored
file: earmark/suspend.py
```old
            if len(chosen) >= MAX_PER_CHECK or available + freed >= scfg["memory_below"] + MEMORY_MARGIN:
```
```new
            if len(chosen) >= MAX_PER_CHECK:
```

### r7-safety: auto: clock jump mid-check ignored
file: earmark/suspend.py
```old
        if time.time() - last > AWAY_GAP:  # the machine slept mid-check: coming back isn't idleness
```
```new
        if False:  # the machine slept mid-check: coming back isn't idleness
```

### r7-safety: auto: memory mode doesn't stop when recovered
file: earmark/suspend.py
```old
            if now is not None and now >= cfg["suspend"]["memory_below"] + MEMORY_MARGIN:
                break
```
```new
            if False:
                break
```

### r7-safety: give_up: signalled agent's record dropped
file: earmark/suspend.py
```old
        if signalled:
            _set_state(session, pane_id, state="stopping", at=time.time())
```
```new
        if False:
            _set_state(session, pane_id, state="stopping", at=time.time())
```

### r7-safety: give_up: exited agent dropped not archived
file: earmark/suspend.py
```old
            if not signalled:  # gone before Earmark stopped it: the user quit it (an exit, not a suspend)
                to_archive(session, pane_id, "exited")
```
```new
            if not signalled:  # gone before Earmark stopped it: the user quit it (an exit, not a suspend)
                drop_record(session, pane_id, "x")
```

### r7-safety: confirmed: ask kept for reuse
file: earmark/suspend.py
```old
        ask = asks.pop(pane_id, None)
```
```new
        ask = asks.get(pane_id, None)
```

### r7-safety: settle: stop_failed without the registry
file: earmark/core.py
```old
            stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE \
                and runs_elsewhere()
```
```new
            stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE
```

### r7-safety: settle: open elsewhere without the registry
file: earmark/core.py
```old
        if panes - {pid} and runs_elsewhere():
```
```new
        if panes - {pid}:
```

### r7-safety: settle: booting closes suspended tabs
file: earmark/core.py
```old
            if flags is not None and t - flags.get("boot", 0) < grace(flags) \
                    and rec.get("seen_at", 0) < flags.get("boot", 0):
                continue  # right after a restart Herdr may still be bringing it back
```
```new
            if False:
                continue  # right after a restart Herdr may still be bringing it back
```

### r7-safety: settle: herdr_listed kept while booting dropped
file: earmark/core.py
```old
        elif pid in snap["panes"] and not other and not booting and state == "suspended":
            rec.pop("herdr_listed", None)
```
```new
        elif pid in snap["panes"] and not other:
            rec.pop("herdr_listed", None)
```

### r7-safety: apply: own stop by since dropped
file: earmark/core.py
```old
                rec.get("state") == "stopping" or note.get("since", 0) <= rec.get("at", 0))
```
```new
                rec.get("state") == "stopping")
```

### r7-safety: apply: said_closed ignored for boot panes
file: earmark/core.py
```old
        if partial or (booting and pid in s.get("boot_panes", [])
                       and not said_closed(pid, note.get("tab_id"), note.get("workspace_id"))):
```
```new
        if partial or (booting and pid in s.get("boot_panes", [])):
```

### r7-safety: apply: restart new-session check ignores partial
file: earmark/core.py
```old
        if len(known) >= 2 and len(back) * 2 < len(known) and not partial_snapshot(snap):
```
```new
        if len(known) >= 2 and len(back) * 2 < len(known):
```

### r7-safety: apply: away gap not recorded
file: earmark/core.py
```old
                    s["quiet_until"] = t + suspend.RETURN_GRACE
```
```new
                    pass
```

### r7-safety: hook: rearm-pass worker never scheduled
file: earmark/core.py
```old
                s["rearm_checked"] = t
                worker_args = ["--rearm-pass"]
```
```new
                s["rearm_checked"] = t
```

### r7-safety: placeholder: input not discarded before exit 0
file: earmark/placeholder.py
```old
    discard_input(fd)  # an Enter queued since (the key, resume on view) mustn't reach the agent starting
```
```new
    pass
```

### r7-safety: message: y without Enter
file: earmark/message.py
```old
            if ch in "\r\n":
                return "y" if typed.lower() == "y" else ""
```
```new
            if ch in "\r\ny":
                return "y" if ch == "y" else ""
```

### r7-safety: message: second flush dropped
file: earmark/message.py
```old
        time.sleep(KEY_DELAY)  # a word being typed as the popup opened isn't an answer
        termios.tcflush(fd, termios.TCIFLUSH)
```
```new
        time.sleep(KEY_DELAY)  # a word being typed as the popup opened isn't an answer
```

### r7-safety: agents: draft hint styles kept (faint counted as typed)
file: earmark/agents.py
```old
        elif n in (2, 3):
            hint = True
```
```new
        elif n in (3,):
            hint = True
```

### r7-safety: agents: env prefix for any agent
file: earmark/agents.py
```old
    if agent != "claude" or not config_dir or not os.path.isabs(config_dir) or UNTYPABLE.search(config_dir):
```
```new
    if not config_dir or not os.path.isabs(config_dir) or UNTYPABLE.search(config_dir):
```

### r7-safety: agents: zsh = and fish % prefixes allowed in kept flags
file: earmark/agents.py
```old
            if any(UNTYPABLE.search(w) or w.startswith(("=", "%")) for w in words):  # zsh =cmd, fish %self
```
```new
            if any(UNTYPABLE.search(w) for w in words):  # zsh =cmd, fish %self
```

### r7-safety: agents: bypass not downgraded when mode unknown
file: earmark/agents.py
```old
            if f == "--dangerously-skip-permissions":
                out.append("--allow-dangerously-skip-permissions")
```
```new
            if False:
                out.append("--allow-dangerously-skip-permissions")
```

### r7-safety: r7b chain_to: stops at first parent
file: earmark/suspend.py
```old
        if parent not in group or parent in chain:
            return chain
```
```new
        if True:
            return chain
```

### r7-safety: r7b look: claude config dir from env not read
file: earmark/suspend.py
```old
        config_dir = procs.environ_var(main["pid"], "CLAUDE_CONFIG_DIR")  # None: unreadable, so unknown
```
```new
        config_dir = None  # None: unreadable, so unknown
```

### r7-safety: r7b look: scheduled tasks ignored
file: earmark/suspend.py
```old
        elif tasks:
            out["timers"] = "it has scheduled tasks"
```
```new
        elif False:
            out["timers"] = "it has scheduled tasks"
```

### r7-safety: r7b refusal: unsafe session id allowed
file: earmark/suspend.py
```old
    if not agents.safe_session_id(sid):
        return "its session id isn't safe to type into a shell"
```
```new
    if False:
        return "its session id isn't safe to type into a shell"
```

### r7-safety: r7b suspend_pane: line_safe ignored
file: earmark/suspend.py
```old
    if not line_safe(session, pane_id):
```
```new
    if False:
```

### r7-safety: r7b suspend_pane: status doubt dropped
file: earmark/suspend.py
```old
    if p.get("agent_status") not in ("idle", "done"):
        doubts.append(f"Herdr can't tell what it's doing (it's {p.get('agent_status') or 'unknown'})")
```
```new
    if False:
        doubts.append(f"Herdr can't tell what it's doing (it's {p.get('agent_status') or 'unknown'})")
```

### r7-safety: r7b suspend_pane: record race (already suspended under lock) ignored
file: earmark/suspend.py
```old
        if pane_id in s.setdefault("suspended", {}):
            return "it's already suspended"
        s["suspended"][pane_id] = rec
```
```new
        s.setdefault("suspended", {})
        s["suspended"][pane_id] = rec
```

### r7-safety: r7b suspend_pane: NOT_YET path no herdr_listed
file: earmark/suspend.py
```old
            _set_state(session, pane_id, herdr_listed=True)  # its restore may relaunch it after a restart
```
```new
            pass  # its restore may relaunch it after a restart
```

### r7-safety: r7b suspend_pane: permission error not given up
file: earmark/suspend.py
```old
    except PermissionError as e:
        return give_up(f"Earmark may not stop it ({e})")
```
```new
    except PermissionError as e:
        return f"Earmark may not stop it ({e})"
```

### r7-safety: r7b give_up: backoff not set after signal
file: earmark/suspend.py
```old
                    if n:
                        n["backoff_until"] = time.time() + BACKOFF
```
```new
                    if False:
                        n["backoff_until"] = time.time() + BACKOFF
```

### r7-safety: r7b line_safe: session name not checked
file: earmark/suspend.py
```old
    return all(shell_safe(p) for p in paths) and not any(agents.UNTYPABLE.search(w or "") for w in (session, pane_id))
```
```new
    return all(shell_safe(p) for p in paths)
```

### r7-safety: r7b mark_tab: marked recorded after rename
file: earmark/suspend.py
```old
            with store.locked():  # listed first: only tabs Earmark marked are ever unmarked, and
                index = store.load_index()  # a hook between the two never records the mark
                session_state(index, session).setdefault("marked", {})[tab_id] = mark
                store.save_index(index)
            try:
                herdr.run("tab", "rename", tab_id, f"{mark} {label}")
```
```new
            try:
                herdr.run("tab", "rename", tab_id, f"{mark} {label}")
                with store.locked():
                    index = store.load_index()
                    session_state(index, session).setdefault("marked", {})[tab_id] = mark
                    store.save_index(index)
```

### r7-safety: r7b arm: waking records not re-armable
file: earmark/suspend.py
```old
        if not rec or rec.get("state") not in ("suspended", "waking"):
            return False
        if rec.get("arming", 0) > t - ARM_CLAIM:
```
```new
        if not rec or rec.get("state") not in ("suspended",):
            return False
        if rec.get("arming", 0) > t - ARM_CLAIM:
```

### r7-safety: r7b arm: relaunch guard dropped
file: earmark/suspend.py
```old
    if herdr_may_relaunch(session, pane_id, rec):
        return False  # every path: the key, a check's re-arm pass, the restart re-arm
```
```new
    if False:
        return False  # every path: the key, a check's re-arm pass, the restart re-arm
```

### r7-safety: r7b same_tab: label not compared
file: earmark/suspend.py
```old
            core._unmarked(tab.get("label"), pane.get("tab_id"), marked) != rec["tab_label"]:
        return False
```
```new
            False:
        return False
```

### r7-safety: r7b rearm_all: deadline grace ignored
file: earmark/suspend.py
```old
    deadline = max(time.time() + REARM_WAIT, s.get("boot", 0) + core.grace(s) + 15)
```
```new
    deadline = time.time() + REARM_WAIT
```

### r7-safety: r7b worker: auto without lock
file: earmark/suspend.py
```old
        if mine:
            auto(session, cfg)
```
```new
        auto(session, cfg)
```

### r7-safety: r7b manual: other session not archived on key
file: earmark/suspend.py
```old
        if state == "other":
            to_archive(session, pane_id, "replaced")
        elif state:
```
```new
        if state == "other":
            drop_record(session, pane_id, "x")
        elif state:
```

### r7-safety: r7b settle: replaced not archived
file: earmark/core.py
```old
        elif other:  # something else runs in its pane now: the suspended session was left
            changed |= archive_note(entries, session, current(dict(rec)), t, "replaced")
```
```new
        elif other:  # something else runs in its pane now: the suspended session was left
            pass
```

### r7-safety: r7b settle: tab identity not kept current
file: earmark/core.py
```old
                for k, v in current_ids.items():
                    if rec.get(k) != v:
                        rec[k] = v
```
```new
                for k, v in current_ids.items():
                    pass
```

### r7-safety: r7b apply: own stop pops nothing (archives as exit)
file: earmark/core.py
```old
            if own_stop:
                s["panes"].pop(pid)  # the agent Earmark is suspending
```
```new
            if False:
                s["panes"].pop(pid)  # the agent Earmark is suspending
```

### r7-safety: r7b apply: boot_protected ignored
file: earmark/core.py
```old
            elif released and not boot_protected(s, pid, t):
```
```new
            elif released:
```

### r7-safety: r7b apply: forgotten session's suspended not archived
file: earmark/core.py
```old
        for rec in (sessions[other].get("suspended") or {}).values():
            changed |= archive_note(entries, other, dict(rec), t, "closed")
```
```new
        for rec in ():
            changed |= archive_note(entries, other, dict(rec), t, "closed")
```

### r7-safety: r7b apply: rearm not requested on restart
file: earmark/core.py
```old
            s["rearm"], s["rearm_pid"] = True, server_pid
```
```new
            s["rearm_pid"] = server_pid
```

### r7-safety: r7b apply: armed_by_rearm not reset on restart
file: earmark/core.py
```old
            for rec in suspended.values():
                rec.pop("armed_by_rearm", None)
```
```new
            for rec in ():
                rec.pop("armed_by_rearm", None)
```

### r7-safety: r7b archive_note: unsafe ids archived
file: earmark/core.py
```old
    if not agents.safe_session_id(note.get("session_id")):
        return False
    facts = agents.session_facts(note["agent"], note["session_id"], config_dir=note.get("config_dir"))
```
```new
    facts = agents.session_facts(note["agent"], note["session_id"], config_dir=note.get("config_dir"))
```

### r7-safety: r7b tab_layouts: suspended resume not kept
file: earmark/core.py
```old
            entry["resume"] = suspended[agent_pane["pane_id"]]["resume"]  # its options and permission mode
```
```new
            pass  # its options and permission mode
```

### r7-safety: r7b restore: elsewhere check dropped
file: earmark/core.py
```old
                elsewhere = tab["agent"] == "claude" and agents.claude_running(tab["session_id"], tab.get("config_dir"))
```
```new
                elsewhere = False
```

### r7-safety: r7b placeholder: hangup archives
file: earmark/placeholder.py
```old
    if action == "hangup":
        return 1
```
```new
    if action == "hangup":
        suspend.to_archive(session, pane_id, "exited")
        return 1
```

### r7-safety: r7b message: ask timeout infinite-ish
file: earmark/message.py
```old
        if not key or b"\x1b" in key or b"\x03" in key:
            return ""
```
```new
        if not key or b"\x03" in key:
            return ""
```

### r7-safety: r7b agents: draft codex hint lines kept
file: earmark/agents.py
```old
            if not typed.strip() or not typed.startswith("  ") or any(k in typed for k in ("⏎", "⌃")):
```
```new
            if not typed.strip() or not typed.startswith("  "):
```

### r7-safety: r7b agents: Try hint fallback returns empty
file: earmark/agents.py
```old
        if text.startswith('Try "') and text.endswith('"'):
            # Claude's hint is drawn faint (and left out above); unstyled, it
            # could as well be typed: Earmark can't tell.
            return None
```
```new
        if text.startswith('Try "') and text.endswith('"'):
            return ""
```

### r7-safety: r7b agents: unknown option arity 1 swallows nothing
file: earmark/agents.py
```old
            if arity == 1:
                words += args[i:i + 1]
                i += 1
```
```new
            if arity == 1:
                pass
```

### r7-safety: r7b agents: claude_running PermissionError treated as gone
file: earmark/agents.py
```old
        except PermissionError:
            pass
        # A file left by a crash can name a pid now used by something else:
```
```new
        except PermissionError:
            continue
        # A file left by a crash can name a pid now used by something else:
```

### r7-safety: r7b agents: CronDelete matches anything
file: earmark/agents.py
```old
                              if any(w in c.get("result", "") or w == cid for w in wanted)), None)
```
```new
                              ), None)
```

### r7-safety: r7b store: save without fsync rename (non-atomic write)
file: earmark/store.py
```old
        os.replace(tmp, os.path.join(directory, name))
```
```new
        import shutil; shutil.copyfile(tmp, os.path.join(directory, name)); os.unlink(tmp)
```

### r7-safety: last look: draft re-read dropped
file: earmark/suspend.py
```old
        if draft:
            return give_up("there's unsent text in its prompt", backoff=False)
```
```new
        if False:
            return give_up("there's unsent text in its prompt", backoff=False)
```

### r7-safety: r7b rearm_pass: revision baseline ignored
file: earmark/suspend.py
```old
    if base.get("screen") == shot:
```
```new
    if base:
```

### r7-safety: r7b key: press time not passed
file: earmark/suspend.py
```old
    spawn_worker(["--pane", pane_id, "--pressed", repr(time.time())])
```
```new
    spawn_worker(["--pane", pane_id])
```

<!-- Strict review 7, found live: the screen decides, and screens are read from the bottom (R150). -->
### R150 screens are read from the bottom, not the scrolled-to part
file: earmark/herdr.py
```old
    source = ["--source", "recent", "--lines", str(int(rows))] if rows else ["--source", "visible"]
```
```new
    source = ["--source", "visible"]
```

### R150 screen_of passes the pane's height
file: earmark/suspend.py
```old
    return herdr.read_screen(pane["pane_id"], rows=(pane.get("scroll") or {}).get("viewport_rows"))
```
```new
    return herdr.read_screen(pane["pane_id"])
```

### R150 the first look reads from the bottom
file: earmark/suspend.py
```old
        screen = screen_of(p)
```
```new
        screen = herdr.read_screen(pane_id)
```

### R150 the last look reads from the bottom
file: earmark/suspend.py
```old
        draft = agents.draft_text(screen_of(now), found["agent"])
```
```new
        draft = agents.draft_text(herdr.read_screen(pane_id), found["agent"])
```

### R138 the fingerprint is of what's shown
file: earmark/suspend.py
```old
    shown = "\n".join(line.rstrip() for line in text.rstrip().splitlines())
```
```new
    shown = ""
```

### R138 a used shell is marked as such
file: earmark/suspend.py
```old
    _set_state(session, pane_id, base={"screen": shot, "at": t} if not base or restart else dict(base, used=True))
```
```new
    _set_state(session, pane_id, base={"screen": shot, "at": t})
```

<!-- Strict review 8: both reviewers' own mutations (82 not already listed). -->

### r8-fit: m02 status clock kept with suspend off (R144 back)
file: earmark/core.py
```old
if idle_clock and new.get("status") != p.get("agent_status"):
```
```new
if new.get("status") != p.get("agent_status"):
```

### r8-fit: m03 idle clock always on (R144 back, second door)
file: earmark/core.py
```old
idle_clock=scfg["when"] in config.AUTO_MODES)
```
```new
idle_clock=True)
```

### r8-fit: m04 last_event rewritten every hook
file: earmark/core.py
```old
if t - s.get("last_event", 0) > 60:
```
```new
if t - s.get("last_event", 0) > 0:
```

### r8-fit: m05 away tracking written in off mode
file: earmark/core.py
```old
if scfg["when"] in config.AUTO_MODES:  # nothing else reads it
```
```new
if True:  # nothing else reads it
```

### r8-fit: m06 index.json written on every hook
file: earmark/core.py
```old
        if json.dumps(index, sort_keys=True) != before:
            store.save_index(index)
    send_reports(reports)
```
```new
        if True:
            store.save_index(index)
    send_reports(reports)
```

### r8-fit: m08 restart re-sends clears for empty workspaces
file: earmark/core.py
```old
s["reported"] = {wid: "" for wid in snap["workspaces"]}
```
```new
s["reported"] = {}
```

### r8-fit: m09 a cut-off snapshot closes tabs
file: earmark/core.py
```old
return not snap["workspaces"] or any(tid not in tabs_with_panes for tid in snap["tabs"])
```
```new
return not snap["workspaces"]
```

### r8-fit: m12 restore leaves focus on the last tab
file: earmark/core.py
```old
tab_id, pane_id = herdr.new_tab(target, tab.get("cwd"), label, focus=(i == 0))
```
```new
tab_id, pane_id = herdr.new_tab(target, tab.get("cwd"), label, focus=True)
```

### r8-fit: m13 '0 archived' token
file: earmark/core.py
```old
return f"{n} archived" if n else ""
```
```new
return f"{n} archived"
```

### r8-fit: m14 closed workspaces never pruned
file: earmark/core.py
```old
        days = cfg["keep_days"] if cfg["keep_days"] is not None else config.FALLBACK_DAYS
        if days and t - closed[key]
```
```new
        days = cfg["keep_days"] if cfg["keep_days"] is not None else 0
        if days and t - closed[key]
```

### r8-fit: m15 process-info on every hook for unresolved Claude panes
file: earmark/core.py
```old
CONFIG_DIR_RETRY = 600
```
```new
CONFIG_DIR_RETRY = 0
```

### r8-fit: m17 resume on view without dwell (wake storm)
file: earmark/suspend.py
```old
WAKE_DWELL = 0.8 
```
```new
WAKE_DWELL = 0.0 
```

### r8-fit: m18 resume on view presses Enter repeatedly
file: earmark/suspend.py
```old
if not rec or rec.get("state") != "suspended" or time.time() - rec.get("enter_sent", 0) < 5:
```
```new
if not rec or rec.get("state") != "suspended":
```

### r8-fit: m19 memory mode acts with memory fine
file: earmark/suspend.py
```old
if available is None or available >= scfg["memory_below"] or not total_kb:
```
```new
if available is None or not total_kb:
```

### r8-fit: m20 memory hysteresis dropped
file: earmark/suspend.py
```old
available + freed >= scfg["memory_below"] + MEMORY_MARGIN
```
```new
available + freed >= scfg["memory_below"]
```

### r8-fit: m21 count mode keeps one fewer (the most recent) awake
file: earmark/suspend.py
```old
keep = {item[0]["pane_id"] for item in recent[:scfg["keep_awake"]]}
```
```new
keep = {item[0]["pane_id"] for item in recent[1:scfg["keep_awake"]]}
```

### r8-fit: m22 memory mode suspends the most recently active first
file: earmark/suspend.py
```old
ok.sort(key=lambda item: item[2]["activity"])
```
```new
ok.sort(key=lambda item: -item[2]["activity"])
```

### r8-fit: m23 parking rule loses 'in view'
file: earmark/suspend.py
```old
        if focused_tab and pane.get("tab_id") == focused_tab:
            return "it's in view"
```
```new
        if focused_tab and pane.get("pane_id") == focused_tab:
            return "it's in view"
```

### r8-fit: m25 question by desktop/terminal toast
file: earmark/suspend.py
```old
shown = toast_mode(cfg) and herdr.setting("ui.toast", "delivery") == "herdr" and herdr.notify(
```
```new
shown = toast_mode(cfg) and herdr.notify(
```

### r8-fit: m26 double tap confirms
file: earmark/suspend.py
```old
return bool(ask) and ask.get("until", 0) >= t >= ask.get("asked", 0) + CONFIRM_MIN and ask.get("why") == why
```
```new
return bool(ask) and ask.get("until", 0) >= t and ask.get("why") == why
```

### r8-fit: m33 check goes on after a sleep mid-check
file: earmark/suspend.py
```old
if time.time() - last > AWAY_GAP:  # the machine slept mid-check
```
```new
if False:  # the machine slept mid-check
```

### r8-fit: m34 suspends right after coming back
file: earmark/suspend.py
```old
    if t < s.get("quiet_until", 0):
        return  # Herdr just came back
```
```new
    if False:
        return  # Herdr just came back
```

### r8-fit: m35 placeholder wakes twice a second
file: earmark/placeholder.py
```old
ready, _, _ = select.select([fd, wake_r], [], [], 60.5 - time.time() % 60)
```
```new
ready, _, _ = select.select([fd, wake_r], [], [], 0.5)
```

### r8-fit: m40 a typed key closes a message unread
file: earmark/message.py
```old
KEY_DELAY = 0.4
```
```new
KEY_DELAY = 0.0
```

### r8-fit: m42 late question can't be answered
file: earmark/message.py
```old
"--focus" if (focus or ask) else "--no-focus"
```
```new
"--focus" if focus else "--no-focus"
```

### r8-fit: m43 Enter confirms forget
file: earmark/ui.py
```old
            if key in ("y", "Y"):
                self.do_forget(key_to_forget)
```
```new
            if key in ("y", "Y", "\n"):
                self.do_forget(key_to_forget)
```

### r8-fit: m45 workspace filter needs a tab match too
file: earmark/ui.py
```old
                rows = [r for r in rows if needle in r["label"].lower()
                        or any(
```
```new
                rows = [r for r in rows if needle in r["label"].lower()
                        and any(
```

### r8-fit: m47 zsh =cmd / fish %self values typed back
file: earmark/agents.py
```old
if any(UNTYPABLE.search(w) or w.startswith(("=", "%")) for w in words):
```
```new
if any(UNTYPABLE.search(w) for w in words):
```

### r8-fit: m48 unknown durable-tasks shape reads as none
file: earmark/agents.py
```old
    return len(data) if isinstance(data, list) else None
```
```new
    return len(data) if isinstance(data, list) else 0
```

### r8-fit: m50 unknown toast answer counted as shown
file: earmark/herdr.py
```old
    return shown if isinstance(shown, bool) else None
```
```new
    return shown if isinstance(shown, bool) else True
```

### r8-fit: m52 tab mark starting with '-'
file: earmark/config.py
```old
    if isinstance(mark, str) and len(mark) <= 8 and not mark.startswith("-") and mark.isprintable() \
            and " " not in mark:
```
```new
    if isinstance(mark, str) and len(mark) <= 8 and mark.isprintable() \
            and " " not in mark:
```

### r8-fit: m53 agent given 2 s to exit
file: earmark/suspend.py
```old
STOP_WAIT = 15 
```
```new
STOP_WAIT = 2 
```

### r8-fit: m54 worker.log grows to 256 MB
file: earmark/suspend.py
```old
        if os.path.getsize(path) > 256 * 1024:
```
```new
        if os.path.getsize(path) > 256 * 1024 * 1024:
```

### r8-fit: m55 live sessions never leave the archive
file: earmark/core.py
```old
    for key in [k for k, e in entries.items() if f"{e['agent']}:{e['session_id']}" in live]:
```
```new
    for key in [k for k, e in entries.items() if e['session_id'] in live]:
```

### r8-fit: m56 queued Enter reaches the agent
file: earmark/placeholder.py
```old
    discard_input(fd)  # an Enter queued
```
```new
    pass  # an Enter queued
```

### r8-fit: m57 placeholder typed into a shell in another folder after restart
file: earmark/suspend.py
```old
    if rec.get("shell_cwd") and pane.get("cwd") and pane["cwd"] != rec["shell_cwd"]:
        return False
```
```new
    if False:
        return False
```

### r8-fit: m58 turning report_count off leaves the tokens shown
file: earmark/core.py
```old
            reports = [(wid, "", time.time_ns()) for wid, text in sent.items() if text]
```
```new
            reports = []
```

### r8-fit: n02 restart detection given up after two parent changes
file: earmark/core.py
```old
        if len(recent) >= 3:
```
```new
        if len(recent) >= 2:
```

### r8-fit: n03 one pane missing after a restart = a new session
file: earmark/core.py
```old
if len(known) >= 2 and len(back) * 2 < len(known) and not partial_snapshot(snap):
```
```new
if len(known) >= 2 and len(back) < len(known) and not partial_snapshot(snap):
```

### r8-fit: n04 a used shell stays used across a restart
file: earmark/core.py
```old
                rec.pop("base", None)  # a new server's shells: watched afresh
```
```new
                pass  # a new server's shells: watched afresh
```

### r8-fit: n06 archived folder is the shell's, not the agent's
file: earmark/core.py
```old
                "cwd": p.get("foreground_cwd") or p.get("cwd"),
```
```new
                "cwd": p.get("cwd") or p.get("foreground_cwd"),
```

### r8-fit: n08 leaving a tab doesn't stamp it (attention clock on arrival)
file: earmark/core.py
```old
            if (left and note.get("tab_id") == left) or (event == "pane.focused" and data.get("pane_id") == pid):
```
```new
            if event == "pane.focused" and data.get("pane_id") == pid:
```

### r8-fit: n09 seen-since-restart not stamped
file: earmark/core.py
```old
if pid in snap["panes"] and (t - rec.get("seen_at", 0) >= 600 or rec.get("seen_at", 0) < (flags or {}).get("boot", 0)):
```
```new
if pid in snap["panes"] and t - rec.get("seen_at", 0) >= 600:
```

### r8-fit: n11 a stop in progress read as failed
file: earmark/core.py
```old
            stop_failed = state == "stopping" and here.get("agent") and t - since > suspend.STOP_STALE \
```
```new
            stop_failed = state == "stopping" and here.get("agent") and t - since > 0 \
```

### r8-fit: n20 restore resumes a deleted session
file: earmark/core.py
```old
                if facts["exists"] and facts["has_content"] and not elsewhere:
```
```new
                if not elsewhere:
```

### r8-fit: n21 counts sent after reopen with report_count off
file: earmark/core.py
```old
    cfg = config.load()
    if not cfg["report_count"]:
        return
```
```new
    cfg = config.load()
```

### r8-fit: n23 wrapper (aws-vault exec) not a doubt
file: earmark/suspend.py
```old
    unknown += [f"(started through {name})" for name in wrappers if name not in LAUNCHERS]
```
```new
    unknown += []
```

### r8-fit: n24 durable tasks looked up in the shell's folder
file: earmark/suspend.py
```old
            durable = agents.durable_tasks(pane.get("foreground_cwd") or pane.get("cwd"))
```
```new
            durable = agents.durable_tasks(pane.get("cwd"))
```

### r8-fit: n30 settings changed mid-check ignored
file: earmark/suspend.py
```old
        if _mtime(config.config_path()) != settings_seen:  # changed meanwhile
```
```new
        if False:  # changed meanwhile
```

### r8-fit: n43 the key on a live placeholder spawns a worker
file: earmark/suspend.py
```old
    if press_enter(session, pane_id):
        return
    spawn_worker
```
```new
    if False:
        return
    spawn_worker
```

### r8-fit: n47 'suspended N ago' counts from last activity
file: earmark/placeholder.py
```old
    when = ago(rec.get("at"), now)
```
```new
    when = ago(rec.get("last_active"), now)
```

### r8-fit: n49 bold-off un-dims the frozen view
file: earmark/placeholder.py
```old
        .replace("\x1b[22m", "\x1b[22m" + DIM)
```
```new
        .replace("\x1b[22m", "\x1b[22m")
```

### r8-fit: n51 account warning can never be passed
file: earmark/placeholder.py
```old
            changed = [] if warned else agents.account_changes(rec.get("account"), os.environ)
```
```new
            changed = agents.account_changes(rec.get("account"), os.environ)
```

### r8-fit: n53 cut body has no ellipsis
file: earmark/message.py
```old
        body_rows = body_rows[:room - 1] + [text.fit(body_rows[room - 1] + " …", width)]
```
```new
        body_rows = body_rows[:room]
```

### r8-fit: n60 combining marks take a column
file: earmark/text.py
```old
    if unicodedata.combining(ch):
        return 0
```
```new
    if False:
        return 0
```

### r8-fit: n61 any agent's ' | ' title cut
file: earmark/agents.py
```old
    if agent == "codex" and " | " in title:
```
```new
    if " | " in title:
```

### r8-fit: n64 same-size rewritten transcript not re-read
file: earmark/agents.py
```old
if size < cache["offset"] or (cache.get("head") and head != cache["head"] and cache["offset"]):
```
```new
if size < cache["offset"]:
```

### r8-fit: n79 no return grace after a long silence
file: earmark/core.py
```old
                    s["quiet_until"] = t + suspend.RETURN_GRACE
```
```new
                    s["quiet_until"] = t
```

### r8-fit: n83 worker shares the hook's session
file: earmark/suspend.py
```old
stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, start_new_session=True,
```
```new
stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, start_new_session=False,
```

### r8-fit: n90 failed-stop backoff forgotten by the next hook
file: earmark/core.py
```old
CARRY = ("since", "focused_at", "status", "status_at", "config_dir", "config_dir_tried", "backoff_until")
```
```new
CARRY = ("since", "focused_at", "status", "status_at", "config_dir", "config_dir_tried")
```

### r8-fit: n91 failed Claude-folder lookup retried every hook
file: earmark/core.py
```old
            if p.get("_config_dir_tried"):
                new["config_dir_tried"] = p["_config_dir_tried"]
```
```new
            if False:
                new["config_dir_tried"] = p["_config_dir_tried"]
```

### r8-fit: n92 placeholder looked at as an agent
file: earmark/suspend.py
```old
    if any(is_placeholder(x) for x in running):
        return dict(out, why="it's suspended already")
```
```new
    if False:
        return dict(out, why="it's suspended already")
```

### r8-safety: A8 last look: registry remote not re-checked
file: earmark/suspend.py
```old
        if registry.get("remote") or registry.get("status") not in (None, "idle"):
            return give_up("Claude says it's busy now", backoff=False)
```
```new
        if registry.get("status") not in (None, "idle"):
            return give_up("Claude says it's busy now", backoff=False)
```

### r8-safety: A9 rearm_pass: waking within grace not skipped
file: earmark/suspend.py
```old
            continue  # being resumed right now
```
```new
            pass  # being resumed right now
```

### r8-safety: A10 mark_waking: fallback ignored for open-elsewhere
file: earmark/suspend.py
```old
        if _open_elsewhere(rec or fallback, pane_id, snap):
```
```new
        if rec and _open_elsewhere(rec, pane_id, snap):
```

### r8-safety: A17 resumed_by_herdr: registry ignored
file: earmark/suspend.py
```old
        if registry.get("session_id"):
            return True if registry["session_id"] == rec.get("session_id") else "other"
```
```new
        if False:
            return True if registry["session_id"] == rec.get("session_id") else "other"
```

### r8-safety: A23 draft: italic counted as hint dropped (only faint)
file: earmark/agents.py
```old
        elif n in (2, 3):
            hint = True
```
```new
        elif n in (2,):
            hint = True
```

### r8-safety: A25 give_up: process gone and unsignalled now dropped instead of archived
file: earmark/suspend.py
```old
                to_archive(session, pane_id, "exited")
                return "it exited on its own"
```
```new
                drop_record(session, pane_id, "x")
                return "it exited on its own"
```

### r8-safety: A26 last look: draft None not re-checked
file: earmark/suspend.py
```old
        if draft is None and UNREADABLE_PROMPT not in doubts:  # readable a moment ago, so not a doubt the user took
```
```new
        if False:  # readable a moment ago, so not a doubt the user took
```

### r8-safety: A27 key: confirm in popup path loses lateness (always focus)
file: earmark/suspend.py
```old
    late = bool(pressed) and time.time() - pressed > LATE
```
```new
    late = False
```

### r8-safety: A28 boot grace: pane notes of boot panes closed
file: earmark/core.py
```old
        if partial or (booting and pid in s.get("boot_panes", [])
```
```new
        if partial or (False and pid in s.get("boot_panes", [])
```

### r8-safety: B3 mark_waking: no Herdr answer goes ahead
file: earmark/suspend.py
```old
    if snap is None:
        return NO_ANSWER
```
```new
    if snap is None:
        snap = {"panes": {}, "workspaces": {}, "tabs": {}}
```

### r8-safety: B5 settle: replaced not archived
file: earmark/core.py
```old
            changed |= archive_note(entries, session, current(dict(rec)), t, "replaced")
```
```new
            pass
```

### r8-safety: B6 settle: failed resume not archived
file: earmark/core.py
```old
            changed |= archive_note(entries, session, current(dict(rec)), t, "exited")
```
```new
            pass
```

### r8-safety: B8 press_enter: no placeholder check
file: earmark/suspend.py
```old
        if not placeholder_pid(session, pane_id):
            return False
        herdr.send_enter(pane_id)
```
```new
        herdr.send_enter(pane_id)
```

### r8-safety: B17 settle: missing suspended pane during boot grace archived
file: earmark/core.py
```old
            if flags is not None and t - flags.get("boot", 0) < grace(flags) \
```
```new
            if False and t - flags.get("boot", 0) < grace(flags) \
```

### r8-fit: m01 note seen refreshed every minute (index rewrites)
file: earmark/core.py
```old
    if t - s.get("seen", 0) > 600:
```
```new
    if t - s.get("seen", 0) > 60:
```

### R155 the mode is read again after the stop
file: earmark/suspend.py
```old
        after = agents.claude_mode_since(transcript, size_before) if size_before is not None else None
```
```new
        after = None
```

### R155 settle_mode runs after a normal stop
file: earmark/suspend.py
```old
        settle_mode()
        # Herdr notices an agent is gone when the shell's prompt is back; a
```
```new
        # Herdr notices an agent is gone when the shell's prompt is back; a
```

### R155 a wide mode needs the footer without an exit record
file: earmark/agents.py
```old
        if WIDE_MODES[mode] not in shown:
            return "default"
```
```new
        if False:
            return "default"
```

### R155 the exit record wins
file: earmark/agents.py
```old
    if after_exit is not None:
        return after_exit
```
```new
    if False:
        return after_exit
```

### R155 only what came after the offset
file: earmark/agents.py
```old
            f.seek(offset)
            chunk = f.read().decode("utf-8", "replace")
```
```new
            chunk = f.read().decode("utf-8", "replace")
```

### R156 a stopping record remembers Herdr listed it
file: earmark/core.py
```old
        if pid in panes and state in ("suspended", "stopping", "waking"):
```
```new
        if pid in panes and state == "suspended":
```

### R156 Enter marks the resume as listed
file: earmark/suspend.py
```old
            rec["herdr_listed"] = True  # the resumed agent: a restart now has Herdr relaunch it
```
```new
            pass
```

### R157 the confirm path answers through tell
file: earmark/suspend.py
```old
            tell(session, pane_id, why, cfg, pressed)  # "suspended" or "kept running", as it really went
```
```new
            say(cfg, "Earmark kept it running", why[0].upper() + why[1:] + ".")
```

### R157 the popup passes the press time
file: earmark/message.py
```old
                                 "--accept", str(ask.get("why")), "--pressed", repr(time.time())]):
```
```new
                                 "--accept", str(ask.get("why"))]):
```

### R158 pasted text is set aside
file: earmark/placeholder.py
```old
            keys, pasting = outside_paste(data, pasting)
```
```new
            keys, pasting = data, False
```

### R158 bracketed paste is on in the placeholder
file: earmark/placeholder.py
```old
ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[?1007l\x1b[?2004h"
```
```new
ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[?1007l"
```

### R159 the suite's HOME is its own
file: tests/_isolate.py
```old
os.environ["HOME"] = os.path.join(ROOT, "home")
```
```new
pass
```

### R160 a failed screen copy stops nothing
file: earmark/suspend.py
```old
    except OSError as e:  # nothing stopped yet: the record goes, the agent runs on
```
```new
    except ZeroDivisionError as e:
```

### R162 any other key closes the question
file: earmark/message.py
```old
            if typed and typed.lower() != "y":
                return ""
```
```new
            if False:
                return ""
```

### R162 a typed y is shown
file: earmark/message.py
```old
            if echo:
                echo(typed)
```
```new
            pass
```

### R163 a double-click on the x never reopens
file: earmark/ui.py
```old
        if b & curses.BUTTON1_DOUBLE_CLICKED and not on_forget:
```
```new
        if b & curses.BUTTON1_DOUBLE_CLICKED:
```

### R164 an unknown tasks file shape is a doubt
file: earmark/agents.py
```old
        data = data.get("tasks", data.get("jobs"))  # another shape: not known, so counted as some
```
```new
        data = data.get("tasks", data.get("jobs", []))
```

### R165 count mode is prefiltered too
file: earmark/suspend.py
```old
                or note.get("backoff_until", 0) > t or t - recent < soonest:
```
```new
                or note.get("backoff_until", 0) > t or (mode != "count" and t - recent < soonest):
```

<!-- Equivalent mutants left out after review 8 (they change nothing a user
could see): r8-fit m36 (the kitty Ctrl+C form can't arrive: the placeholder
pops the kitty modes first), n54 (the first input flush; the one after the
first moment covers it), n69 (node option parsing at the end of argv), n80
(CLAUDE_CONFIG_DIR from the first foreground process: a launcher shares its
child's environment), R64 (read_answer only ever returns "y" or ""; R128
and r4-fit plant the confirm rule itself), r7-fit rule-bare-shell-looked-at
(another refusal fires). r5-fit "bracketed paste left on" is gone with
the code it planted in: the placeholder turns bracketed paste on itself
(review 8 R158). -->
