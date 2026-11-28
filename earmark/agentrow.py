"""Agent rows (PLAN M4, M5): model · effort · context on each agent's second
line in Herdr's sidebar, e.g. "Opus 5.5 · xhigh · 9%".

Claude Code tells only its status line these three (the status-line JSON:
model.display_name, effort.level, context_window.used_percentage; its hooks
don't carry effort), so `earmark statusline -- <command...>` stands in
front of the user's own status line (earmark/statusline.py: that command's
output goes back first, Earmark's part runs apart), and from_statusline()
here takes the values. No agent hooks, no daemon.

Codex and Grok write theirs to their session files, which the hooks read
(Codex: the rollout's turn_context and token_count; Grok: summary.json and
signals.json), so their rows change per turn, not live.

Each agent pane has a small cache, rows/<session>/<pane>.json: the values
(agent, session id, model, effort, percent) and the tokens last sent. The
hooks refit them (the sidebar's width changed, a Herdr restart lost the
tokens) and clear a pane's tokens once its agent has gone. A cache, so no
fsync: lost, everything is sent again.
"""
import contextlib
import json
import os
import sys
import time

from . import agents, config, herdr, sidebar, store

# ------------------------------------------------------------------ cache

def rows_dir(session):
    path = os.path.join(store.state_dir(), "rows", store.segment(session))
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


LOCK_WAIT = 2  # seconds: each use takes milliseconds; one stuck that long is given up on


def locked(session):
    """One lock per Herdr session's rows. TimeoutError after LOCK_WAIT, so
    a stuck holder can't pile up status line runs behind it."""
    return store.flock(os.path.join(rows_dir(session), ".lock"), timeout=LOCK_WAIT)


def _file(session, pane):
    return os.path.join(rows_dir(session), store.segment(pane) + ".json")


def load(session, pane):
    try:
        with open(_file(session, pane), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(session, pane, data):
    store.write_atomic(_file(session, pane), json.dumps(data, ensure_ascii=False, sort_keys=True), sync=False)


def drop(session, pane):
    with contextlib.suppress(OSError):
        os.unlink(_file(session, pane))


def cached_panes(session):
    """Pane ids with a cache file (read back from each file: names may be hashes)."""
    out = {}
    try:
        names = os.listdir(rows_dir(session))
    except OSError:
        return out
    for name in names:
        if name.endswith(".json") and not name.startswith("."):
            try:
                with open(os.path.join(rows_dir(session), name), encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and isinstance(data.get("pane"), str):
                out[data["pane"]] = data
    return out


# ----------------------------------------------------------------- values

def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def claude_values(payload):
    """What Claude's status-line JSON says, or None if it isn't that."""
    if not isinstance(payload, dict):
        return None
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    effort = payload.get("effort") if isinstance(payload.get("effort"), dict) else {}
    window = payload.get("context_window") if isinstance(payload.get("context_window"), dict) else {}
    used = _number(window.get("used_percentage"))
    percent = int(round(used)) if used is not None and used >= 0 else \
        sidebar.percent_of(window.get("total_input_tokens"), window.get("context_window_size"))
    name = model.get("display_name") or model.get("id")
    return {"agent": "claude", "session_id": payload.get("session_id") if isinstance(payload.get("session_id"), str)
            else None, "model": name if isinstance(name, str) else None,
            "effort": effort.get("level") if isinstance(effort.get("level"), str) else None, "percent": percent}


def _codex_catalog():
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    try:
        with open(os.path.join(home, "models_cache.json"), encoding="utf-8") as f:
            models = json.load(f).get("models")
    except (OSError, ValueError, AttributeError):
        return {}
    return {m["slug"]: m for m in models or [] if isinstance(m, dict) and isinstance(m.get("slug"), str)}


def codex_values(rollout):
    """From a Codex rollout: the last turn's model and effort (no effort: the
    model's default), and the last token count against its window."""
    model = effort = None
    used = window = None
    have_turn = have_tokens = False
    for record in agents.tail_records(rollout):
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if not have_turn and record.get("type") == "turn_context":
            model, effort, have_turn = payload.get("model"), payload.get("effort"), True
        elif not have_tokens and record.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
            used, window, have_tokens = last.get("total_tokens"), info.get("model_context_window"), True
        if have_turn and have_tokens:
            break
    if not isinstance(model, str):
        return None
    entry = _codex_catalog().get(model) or {}
    if not isinstance(effort, str):
        effort = entry.get("default_reasoning_level") if isinstance(entry.get("default_reasoning_level"), str) else None
    name = entry.get("display_name") if isinstance(entry.get("display_name"), str) else model
    return {"agent": "codex", "model": name, "effort": effort, "percent": sidebar.percent_of(used, window)}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def grok_values(summary_path):
    """From a Grok session folder: summary.json's model and effort, the
    prompt's label for the model ("Grok 4.7"), signals.json's context."""
    folder = os.path.dirname(summary_path)
    summary = _read_json(summary_path)
    model = summary.get("current_model_id")
    if not isinstance(model, str):
        return None
    label = _read_json(os.path.join(folder, "prompt_context.json")).get("system_prompt_label")
    signals = _read_json(os.path.join(folder, "signals.json"))
    effort = summary.get("reasoning_effort")
    return {"agent": "grok", "model": label if isinstance(label, str) and label else model,
            "effort": effort if isinstance(effort, str) else None,
            "percent": sidebar.percent_of(signals.get("contextTokensUsed"), signals.get("contextWindowTokens"))}


def file_values(agent, session_id, cached):
    """Codex or Grok values for a session, read again only when its file
    changed (the cache keeps the file, its size and time)."""
    same = cached.get("session_id") == session_id and cached.get("agent") == agent
    source = cached.get("source") if same and os.path.isfile(cached.get("source") or "") else \
        agents.session_facts(agent, session_id, title=False).get("source")
    if not source:
        return None
    paths = [source] if agent == "codex" else \
        [source] + [os.path.join(os.path.dirname(source), n) for n in ("signals.json", "prompt_context.json")]
    stamp = []
    for p in paths:
        try:
            st = os.stat(p)
            stamp.append([p, st.st_size, st.st_mtime_ns])
        except OSError:
            stamp.append([p, None, None])
    if same and cached.get("stamp") == stamp:
        return dict({k: cached.get(k) for k in ("agent", "model", "effort", "percent")}, stamp=stamp, source=source)
    values = codex_values(source) if agent == "codex" else grok_values(source)
    return dict(values, stamp=stamp, source=source) if values else None


# ---------------------------------------------------------------- sending

def update(session, pane, values, cfg, width, fresh=False):
    """Fit `values` to the row, send the tokens if they changed, remember
    both. `values` None refits what's cached, read under the lock (a status
    line run may have just saved newer values). `fresh`: what was sent
    before is gone (a Herdr restart)."""
    with locked(session):
        cached = load(session, pane)
        if values is None:
            if not cached:
                return {}
            values = cached
        tokens = sidebar.agent_tokens(values.get("model"), values.get("effort"), values.get("percent"),
                                      cfg["sidebar"], width)
        before = None if fresh else cached.get("sent")
        # What the pane shows is what was last sent to it, whatever ran there
        # before; nothing known (new, or after a restart): nothing to clear.
        delta = sidebar.changed(tokens, before)
        record = dict(values, pane=pane, sent=tokens)
        if record != cached:
            save(session, pane, record)
        seq = time.time_ns()
    if delta:
        try:
            sidebar.report("pane", pane, delta, seq)
        except herdr.HerdrError:
            with locked(session):  # not sent: the next run compares with what's really shown
                again = load(session, pane)
                if again.get("sent") == tokens:
                    again["sent"] = before
                    save(session, pane, again)
            raise
    return delta


def clear(session, pane, cached, alive=True):
    """A pane whose agent left: its tokens cleared (if the pane is still
    there) and its cache dropped."""
    shown = {k: None for k, v in (cached.get("sent") or {}).items() if v}
    with locked(session):
        drop(session, pane)
    if alive and shown:
        sidebar.report("pane", pane, shown, time.time_ns())


def refresh(session, snap, cfg, boot):
    """For the hooks: refit every agent row (the width may have changed),
    send them all again after a restart, read Codex's and Grok's files, and
    clear rows whose agent has gone. Errors are printed, never raised."""
    if not cfg["sidebar"]["agent_row"]:  # turned off: what's shown goes
        for pane_id, rec in cached_panes(session).items():
            try:
                clear(session, pane_id, rec, alive=pane_id in snap["panes"])
            except (herdr.HerdrError, OSError) as e:
                print(f"earmark: agent row of {pane_id}: {e}", file=sys.stderr)
        return
    width = sidebar.sidebar_width(session)
    marker = os.path.join(rows_dir(session), ".boot")
    try:
        with open(marker, encoding="utf-8") as f:
            fresh = f.read().strip() != str(boot)
    except OSError:
        fresh = True
    cached = cached_panes(session)
    for pane_id, rec in cached.items():
        p = snap["panes"].get(pane_id)
        live = (p.get("agent_session") or {}).get("value") if p else None
        if not p or p.get("agent") != rec.get("agent") or (live and rec.get("session_id") and live != rec["session_id"]):
            try:
                clear(session, pane_id, rec, alive=bool(p))
            except (herdr.HerdrError, OSError) as e:
                print(f"earmark: agent row of {pane_id}: {e}", file=sys.stderr)
            continue
        if rec.get("agent") == "claude":
            try:
                update(session, pane_id, None, cfg, width, fresh=fresh)
            except (herdr.HerdrError, OSError) as e:
                print(f"earmark: agent row of {pane_id}: {e}", file=sys.stderr)
    for pane_id, p in snap["panes"].items():
        agent = p.get("agent")
        sid = (p.get("agent_session") or {}).get("value")
        if agent not in ("codex", "grok") or not isinstance(sid, str) or not sid:
            continue
        try:
            values = file_values(agent, sid, cached.get(pane_id) or {})
            if values:
                update(session, pane_id, dict(values, session_id=sid), cfg, width, fresh=fresh)
        except (herdr.HerdrError, OSError, ValueError) as e:
            print(f"earmark: agent row of {pane_id}: {e}", file=sys.stderr)
    if fresh:
        with contextlib.suppress(OSError):
            store.write_atomic(marker, str(boot), sync=False)


# ------------------------------------------------------------ status line

def from_statusline(data, env):
    """Earmark's part of Claude Code's status line (earmark/statusline.py
    runs the user's own command first): this pane's agent line from the
    status line's input."""
    pane = env.get("HERDR_PANE_ID")
    if not pane:
        return
    values = claude_values(json.loads(data.decode("utf-8")))
    if values and (values.get("model") or values.get("percent") is not None):
        session = env.get("HERDR_SESSION") or "default"
        cfg = config.load()
        if cfg["sidebar"]["agent_row"] and pane_is_ours(session, pane, values.get("session_id")):
            update(session, pane, values, cfg, sidebar.sidebar_width(session))


def pane_is_ours(session, pane, session_id):
    """Whether this Claude is the agent Herdr shows in `pane`: a Claude in
    VS Code, tmux or a window started from a Herdr pane inherits its
    HERDR_PANE_ID, and must not write that pane's line. Asked of Herdr once
    per session id (the pane's cache then holds it)."""
    if not session_id:
        return False
    if load(session, pane).get("session_id") == session_id:
        return True
    try:
        live = (herdr.pane(pane).get("agent_session") or {}).get("value")
    except herdr.HerdrError:
        return False
    return live == session_id
