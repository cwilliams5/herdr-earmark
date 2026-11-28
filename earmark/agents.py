"""What Earmark knows about each coding agent.

RESUME is Herdr's own table of resume commands ("Native session restore",
herdr.dev/docs/session-state, Herdr 0.9.5), keyed by the agent names Herdr
reports (`herdr integration status`). Users can override or add entries in
config.toml's [resume] table.

Some agents also get a deeper look at their own files, which tells whether a
session still exists, whether it has anything to resume, its title and its
last activity (`session_facts`): Claude Code (transcripts), Codex (its
state database) and Grok (session summaries). Formats were read from Claude
Code 2.1.330, Codex 0.171 and Grok 1.0.92; anything unexpected makes the
facts "unknown", and an unknown session is kept until keep_days, never
dropped on a guess. Other agents rely on keep_days alone.
"""
import calendar
import glob
import hashlib
import json
import os
import pathlib
import re
import time

RESUME = {
    "pi": ["pi", "--session", "{id}"],
    # Herdr reports Antigravity CLI sessions as agent "agy" (source
    # herdr:antigravity_cli); its integration is named antigravity-cli.
    "agy": ["agy", "--conversation", "{id}"],
    "antigravity-cli": ["agy", "--conversation", "{id}"],
    "omp": ["omp", "--resume={id}"],
    # `command` skips a user's `claude` alias or function, which could add a
    # flag (bypassing permissions, say) the session wasn't in. These lines
    # are typed into the tab's shell, so the shell builtin works there.
    "claude": ["command", "claude", "--resume", "{id}"],
    # Herdr's table says `codex resume <id>`. --no-daemon keeps the reopened
    # Codex out of its shared app-server daemon, which reports sessions to
    # whichever pane started the daemon (herdrdev/herdr#4649, open as of
    # Herdr 0.9.5 / Codex 0.171). `command` skips a user's codex alias or
    # function, which may add --no-daemon already (Codex rejects it twice).
    # The command is typed into the tab's shell, so `command` works there.
    # Drop both once that issue is fixed.
    "codex": ["command", "codex", "--no-daemon", "resume", "{id}"],
    "cursor": ["cursor-agent", "--resume", "{id}"],
    "grok": ["grok", "--resume", "{id}"],
    "copilot": ["copilot", "--resume={id}"],
    "devin": ["devin", "--resume", "{id}"],
    "droid": ["droid", "--resume", "{id}"],
    "kimi": ["kimi", "--session", "{id}"],
    "qodercli": ["qodercli", "--resume", "{id}"],
    "qwen": ["qwen", "--resume", "{id}"],
    "letta": ["letta", "--conversation", "{id}"],
    "opencode": ["opencode", "--session", "{id}"],
    "kilo": ["kilo", "--session", "{id}"],
    "hermes": ["hermes", "--resume", "{id}"],
    "mastracode": ["mastracode", "--thread", "{id}"],
}

# Titles an agent shows before it has a real one: not worth keeping.
GENERIC_TITLES = {"", "claude", "claude code", "codex", "pi", "grok", "copilot", "shell",
                  # status lines some agents show as the title while they work
                  "waiting for response…", "waiting for response...", "thinking…", "thinking..."}


# A session id Earmark will type into a shell. Herdr accepts any id up to 512
# bytes without control characters, from any process in a pane, so ids are
# checked before use: no leading "-" (it would be read as an option), no
# quote or backslash (fish reads \' inside single quotes as an escaped quote,
# which breaks the POSIX quoting shlex produces), no control characters.
# Paths are fine (pi and omp report a session file path).
_SAFE_ID = re.compile(r"[^\s'\\-][^'\\\x00-\x1f\x7f]{0,511}")


def safe_session_id(session_id):
    return isinstance(session_id, str) and bool(_SAFE_ID.fullmatch(session_id))


def resume_argv(agent, session_id, overrides=None):
    """The command that reopens a session, or None if Earmark doesn't know one
    or the session id isn't safe to type into a shell. In a [resume]
    template, "{id}" must be a whole argument, never inside `sh -c "..."`."""
    if not safe_session_id(session_id):
        return None
    if agent == "letta" and session_id.startswith("default:"):
        return ["letta", "--conversation", "default", "--agent", session_id.split(":", 1)[1]]
    template = (overrides or {}).get(agent) or RESUME.get(agent)
    if not template:
        return None
    return [part.replace("{id}", session_id) for part in template]


def clean_title(title, agent=None):
    """A terminal title without the agent's decorations: Claude Code's status
    glyph ("✳ Fix tests"), Grok's " - grok" and Codex's " | <folder>"
    suffixes. Returns "" for titles that only name the agent."""
    title = re.sub(r"^[^\w(\[\"'`]+", "", (title or "")).strip()
    if agent == "codex" and " | " in title:
        title = title.rsplit(" | ", 1)[0].strip()
    if agent and title.lower().endswith(f" - {agent.lower()}"):
        title = title[: -len(agent) - 3].strip()
    if title.lower() in GENERIC_TITLES or (agent and title.lower() == agent.lower()):
        return ""
    return title


# ------------------------------------------------------------- Claude Code

def _claude_dir(config_dir=None):
    """Claude Code's folder: the one the session's own process used (read
    from its environment when Earmark first saw it), else this process's
    CLAUDE_CONFIG_DIR, else ~/.claude. Herdr's server, which runs Earmark's
    hooks, may not have the CLAUDE_CONFIG_DIR the user's shell has.
    config_dir "" means the process had none: Claude's default folder."""
    if config_dir:
        return config_dir
    if config_dir == "":
        return os.path.expanduser("~/.claude")
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def claude_transcript(session_id, config_dir=None):
    if not re.fullmatch(r"[0-9A-Za-z-]+", session_id or ""):
        return None
    # The folder is escaped: a "[" in it would otherwise turn the search into
    # a pattern that matches nothing, and every session would look deleted.
    hits = glob.glob(os.path.join(glob.escape(_claude_dir(config_dir)), "projects", "*", f"{session_id}.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


# User records Claude Code writes that the user didn't type: slash-command
# echoes, background-task and subagent results, `!` shell input and output.
_COMMAND_NOISE = ("<local-command", "<command-name>", "<command-message>", "<command-args>", "<task-notification",
                  "<bash-input", "<bash-stdout", "<bash-stderr", "<system-reminder", "<user-prompt-submit-hook")


def _real_prompt(record):
    """The text of a user record that is a real prompt, else None."""
    if record.get("type") != "user" or record.get("isMeta"):
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        content = " ".join(texts)
    if not isinstance(content, str):
        return None
    content = content.strip()
    if not content or content.startswith(_COMMAND_NOISE):
        return None
    return content


def tail_records(path, tail_bytes=1048576):
    """JSON-line records at the end of a file, last first."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            data = f.read()
    except OSError:
        return
    lines = data.split(b"\n")
    if size > tail_bytes:
        lines = lines[1:]  # the first line was cut
    for raw in reversed(lines):
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if isinstance(record, dict):
            yield record


REQUESTS, REPLIES = 3, 3  # the last few of each, for a note's line on a tab
REQUEST_CHARS, REPLY_CHARS = 600, 1500
SCAN_LIMIT = 64 << 20  # bytes read back for them at most (a user's message can sit megabytes back)


def _lines_back(path, chunk=4 << 20):
    """A file's lines, last first, read backwards a chunk at a time, up to
    SCAN_LIMIT bytes."""
    try:
        f = open(path, "rb")
    except OSError:
        return
    with f:
        f.seek(0, os.SEEK_END)
        pos, rest, read = f.tell(), b"", 0
        while pos > 0 and read < SCAN_LIMIT:
            step = min(chunk, pos)
            pos -= step
            read += step
            f.seek(pos)
            lines = (f.read(step) + rest).split(b"\n")
            rest = lines[0]  # may be the end of a line that starts in the chunk before
            yield from reversed(lines[1:])
        if pos == 0 and rest:
            yield rest


def _start(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _reply(text, n=REPLY_CHARS):
    """A reply in words, without a closing list of sources, its start and
    its end kept (where an agent says what it did and where things stand)."""
    text = str(text)
    cut = text.rfind("Sources:")
    if cut > len(text) * 0.4:
        text = text[:cut]
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    head = n * 4 // 15
    return text[:head].rstrip() + " … " + text[-(n - head - 3):].lstrip()


def _claude_record(line):
    """A transcript line worth parsing for recent_exchange (cheap test first:
    tool results are most of a transcript's bytes)."""
    if b'"type":"assistant"' in line or b'"type": "assistant"' in line:
        return True
    return (b'"type":"user"' in line or b'"type": "user"' in line) and b'"tool_result"' not in line


def recent_exchange(agent, path):
    """What catching up on a session needs, from its conversation: the
    user's last few requests (their start), the agent's last few replies in
    words (start and end), and the names of the tools it used since the last
    request ("Bash", "Edit"), never what a tool read or returned (web pages,
    files and command output are where planted instructions would come
    from), nor the records Claude writes as the user's that the user didn't
    type (task results, `!` shell output: _COMMAND_NOISE). Oldest first. Claude's transcript and Codex's rollout; other
    agents give nothing."""
    requests, replies, tools = [], [], {}
    for line in _lines_back(path) if agent in ("claude", "codex") and path else ():
        if agent == "claude" and not _claude_record(line) or agent == "codex" and b'"response_item"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        said = asked = None
        used = []
        if agent == "claude":
            asked = _real_prompt(record)
            content = (record.get("message") or {}).get("content") if record.get("type") == "assistant" else None
            for c in content if isinstance(content, list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and isinstance(c.get("name"), str):
                    used.append(c["name"])
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"] \
                if isinstance(content, list) else []
            said = " ".join(t for t in texts if t.strip()) or None
        else:
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            if payload.get("type") == "message":
                texts = [c.get("text", "") for c in payload.get("content") or [] if isinstance(c, dict)
                         and c.get("type") in ("input_text", "output_text")]
                words = " ".join(t for t in texts if t.strip() and not t.lstrip().startswith("<")) or None
                asked, said = (words, None) if payload.get("role") == "user" else \
                    (None, words) if payload.get("role") == "assistant" else (None, None)
            elif payload.get("type") in ("function_call", "custom_tool_call") and isinstance(payload.get("name"), str):
                used.append(payload["name"])
        if not requests:  # since the last request
            for name in used:
                tools[name[:40]] = tools.get(name[:40], 0) + 1
        if asked and len(requests) < REQUESTS and (not requests or requests[-1] != _start(asked, REQUEST_CHARS)):
            requests.append(_start(asked, REQUEST_CHARS))  # a message sent twice takes one place
        if said and len(replies) < REPLIES:
            replies.append(_reply(said))
        if len(requests) >= REQUESTS and len(replies) >= REPLIES:
            break
    return {"requests": requests[::-1], "replies": replies[::-1],
            "tools": [f"{name} ×{n}" if n > 1 else name for name, n in sorted(tools.items(), key=lambda kv: -kv[1])]}


def claude_has_content(path, max_lines=5000):
    """True if the transcript has something to resume: a real prompt, or any
    answer from Claude (a session started with a slash command such as
    /goal has answers but no typed prompt). A session that only ran /exit
    or /model has neither."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n >= max_lines:
                    return True  # long transcripts are real conversations
                if '"user"' not in line and '"assistant"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") == "assistant" or _real_prompt(record):
                    return True
    except OSError:
        return False
    return False


def claude_title(path, tail_bytes=262144):
    """The session's name: the last custom title, else the last AI title, else
    the last prompt. Reads only the end of the file."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            chunk = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    custom = ai = prompt = ""
    for line in chunk.splitlines():
        if '"custom-title"' in line or '"ai-title"' in line or '"last-prompt"' in line:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") == "custom-title":
                custom = r.get("customTitle") or r.get("title") or custom
            elif r.get("type") == "ai-title":
                ai = r.get("aiTitle") or ai
            elif r.get("type") == "last-prompt":
                prompt = r.get("lastPrompt") or prompt
    title = custom or ai or prompt
    return " ".join(title.split())[:120]


UNKNOWN = {"known": False, "exists": True, "has_content": True, "title": "", "last_active": None}


def session_facts(agent, session_id, config_dir=None, title=True):
    """What Earmark can learn about a session from the agent's own files:
    {"known": bool, "exists": bool, "has_content": bool, "title": str,
    "last_active": float or None, "source": the file read, when there is
    one}. "known" is False for agents (or setups)
    Earmark can't look into; then the rest is a placeholder and the caller
    relies on keep_days."""
    reader = {"claude": _claude_facts, "codex": _codex_facts, "grok": _grok_facts}.get(agent)
    if not reader or not session_id:
        return dict(UNKNOWN)
    try:
        return reader(session_id, config_dir, title) if agent == "claude" else reader(session_id)
    except (OSError, ValueError):
        return dict(UNKNOWN)


def _claude_facts(session_id, config_dir=None, title=True):
    if not os.path.isdir(os.path.join(_claude_dir(config_dir), "projects")):
        return dict(UNKNOWN)
    path = claude_transcript(session_id, config_dir)
    if not path:
        return {"known": True, "exists": False, "has_content": False, "title": "", "last_active": None}
    return {"known": True, "exists": True, "has_content": claude_has_content(path),
            "title": claude_title(path) if title else "", "last_active": os.path.getmtime(path), "source": path}


# ------------------------------------------------------------------- Codex

def _codex_db():
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    dbs = glob.glob(os.path.join(glob.escape(home), "state_*.sqlite"))
    number = lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0)
    return max(dbs, key=number) if dbs else None


def _codex_facts(session_id):
    """Codex keeps a `threads` table: a generated name, the first message, the
    last update, and the path of the session's log (its "rollout")."""
    db = _codex_db()
    if not db:
        return dict(UNKNOWN)
    import sqlite3  # here only: the placeholder (Claude, mostly) never loads it
    try:
        # A file URI built by pathlib, so "?", "#" or "%" in the path can't break it.
        con = sqlite3.connect(pathlib.Path(db).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            # Only whether there was a first message is read, not the message.
            row = con.execute("select rollout_path, name, title, "
                              "coalesce(first_user_message, '') != '', updated_at "
                              "from threads where id = ?", (session_id,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return dict(UNKNOWN)
    if not row:
        return {"known": True, "exists": False, "has_content": False, "title": "", "last_active": None}
    rollout, name, title, had_first, updated = row
    exists = not rollout or os.path.exists(rollout)
    return {"known": True, "exists": exists, "has_content": bool(had_first or title),
            "title": " ".join((name or title or "").split())[:120],
            "last_active": float(updated) if updated else None, "source": rollout or None}


# -------------------------------------------------------------------- Grok

def _iso_to_epoch(text):
    """2026-11-21T19:19:03.852787919Z -> seconds (Python 3.9 can't parse it)."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d+))?Z?$", text or "")
    if not m:
        return None
    y, mo, d, h, mi, sec, frac = m.groups()
    return calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(sec))) + float(f"0.{frac or 0}")


def _grok_facts(session_id):
    """Grok keeps sessions/<folder>/<id>/summary.json: a generated summary
    (its title), the last activity and a message count."""
    home = os.environ.get("GROK_HOME") or os.path.expanduser("~/.grok")
    if not os.path.isdir(os.path.join(home, "sessions")) or not re.fullmatch(r"[0-9A-Za-z-]+", session_id):
        return dict(UNKNOWN)
    hits = glob.glob(os.path.join(glob.escape(home), "sessions", "*", session_id, "summary.json"))
    if not hits:
        return {"known": True, "exists": False, "has_content": False, "title": "", "last_active": None}
    with open(hits[0], encoding="utf-8") as f:
        summary = json.load(f)
    title = " ".join((summary.get("session_summary") or "").split())[:120]
    messages = int(summary.get("num_messages") or 0)
    last = _iso_to_epoch(summary.get("last_active_at") or summary.get("updated_at")) or os.path.getmtime(hits[0])
    return {"known": True, "exists": True, "has_content": bool(title) or messages >= 2,
            "title": title, "last_active": last, "source": hits[0]}


# ------------------------------------------------- suspending a live session
#
# What Earmark reads before suspending an agent in place (CLAUDE.md,
# "Suspend"), and how it brings it back the way it was started.

def claude_activity(path):
    """The last time Claude wrote anything for this session: its transcript,
    or the folder beside it where subagents keep theirs (a Claude running
    background subagents can look idle to Herdr while they work)."""
    newest = 0.0
    try:
        newest = os.path.getmtime(path)
    except OSError:
        return None
    folder = path[:-len(".jsonl")]
    stack = [(folder, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            with os.scandir(directory) as it:
                for item in it:
                    try:
                        if item.is_dir(follow_symlinks=False) and depth < 3:
                            stack.append((item.path, depth + 1))
                        elif item.is_file(follow_symlinks=False):
                            newest = max(newest, item.stat().st_mtime)
                    except OSError:
                        continue
        except OSError:
            continue
    return newest


_TIMER_TOOLS = ('"ScheduleWakeup"', '"CronCreate"', '"CronDelete"')


ONE_SHOT_HOURS = 24  # a one-shot scheduled task counts as pending this long
TIMER_READ = 8 * 1024 * 1024  # bytes of transcript read per check at most


def _open_tasks(cache, now):
    one_shot_after = now - ONE_SHOT_HOURS * 3600
    return sum(1 for c in cache["created"].values() if c.get("recurring") or c.get("stamp", 0) > one_shot_after)


def _result_text(item):
    content = item.get("content")
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content or "")[:2000]


def claude_timers(path, since, cache, now=None):
    """Claude's own timers still to fire, counted only from calls made after
    `since` (when the running process started; they die with it; 0 counts
    them all): a /loop or ScheduleWakeup wake-up still to come, and
    scheduled tasks (CronCreate) created and not deleted (a one-shot task,
    recurring false, for ONE_SHOT_HOURS). A CronDelete removes the task it
    names (matched against what the create said: its result and input); one
    Earmark can't match removes nothing, so the agent stays awake. Returns
    (wake_until, open_tasks). `cache` (a dict kept between calls) remembers
    how far the transcript was read, so each call reads only what's new."""
    now = time.time() if now is None else now
    if since and not os.path.isdir("/proc/self"):
        since -= since % 60  # macOS start times (from `ps etime`) wobble by the second
    if cache.get("path") != path or cache.get("since") != since or cache.get("v") != 2:
        cache.clear()
        cache.update({"v": 2, "path": path, "since": since, "offset": 0, "wake_until": 0, "created": {}})
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(256).hex()
            if size < cache["offset"] or (cache.get("head") and head != cache["head"] and cache["offset"]):
                # rewritten (shorter, or a different start): read it again
                cache.update({"offset": 0, "wake_until": 0, "created": {}})
                cache.pop("mode", None)
            cache["head"] = head
            f.seek(cache["offset"])
            chunk = f.read(TIMER_READ)  # a long transcript is read on over later checks
    except OSError:
        return cache["wake_until"], _open_tasks(cache, now)
    if cache.get("skipping"):  # the rest of a line longer than the read window
        nl = chunk.find(b"\n")
        if nl < 0:
            cache["offset"] += len(chunk)
            cache["behind"] = cache["offset"] < size
            return cache["wake_until"], _open_tasks(cache, now)
        cache["offset"] += nl + 1
        chunk = chunk[nl + 1:]
        cache["skipping"] = False
    elif len(chunk) == TIMER_READ and b"\n" not in chunk:
        # One line longer than the whole window (a huge tool result; no timer
        # call is that long): skipped, or the reader would stall on it.
        cache["offset"] += len(chunk)
        cache["skipping"], cache["behind"] = True, True
        return cache["wake_until"], _open_tasks(cache, now)
    end = chunk.rfind(b"\n") + 1  # whole lines only; a line being written waits
    cache["offset"] += end
    cache["behind"] = cache["offset"] < size
    created = cache["created"]
    for raw in chunk[:end].split(b"\n"):
        line = raw.decode("utf-8", "replace")
        if '"permissionMode"' in line:  # the mode it's in, read over the whole transcript (claude_mode)
            try:
                value = json.loads(line).get("permissionMode")
            except (ValueError, AttributeError):
                value = None
            if isinstance(value, str):
                cache["mode"] = value
        waiting = [cid for cid, c in created.items() if not c.get("result")]
        if not any(tool in line for tool in _TIMER_TOOLS) and not any(cid in line for cid in waiting):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        items = [x for x in (record.get("message") or {}).get("content") or [] if isinstance(x, dict)]
        if record.get("type") == "user":  # what a CronCreate answered (the task's id is in it)
            for item in items:
                if item.get("type") == "tool_result" and item.get("tool_use_id") in created:
                    created[item["tool_use_id"]]["result"] = _result_text(item)
            continue
        stamp = _iso_to_epoch(record.get("timestamp"))
        if record.get("type") != "assistant" or stamp is None or stamp < since:
            continue
        for item in items:
            if item.get("type") != "tool_use":
                continue
            args = item.get("input") if isinstance(item.get("input"), dict) else {}
            if item.get("name") == "ScheduleWakeup":
                delay = args.get("delaySeconds")
                stopped = args.get("stop") is True or not isinstance(delay, (int, float))
                cache["wake_until"] = 0 if stopped else stamp + float(delay)
                # When it was set, and how long the machine had slept by the
                # time Earmark read it (look() adds any sleep since).
                from . import procs
                cache["wake_from"], cache["wake_slept"] = stamp, procs.suspended_seconds()
            elif item.get("name") == "CronCreate":
                created[str(item.get("id") or f"anon-{len(created)}")] = {
                    "stamp": stamp, "recurring": args.get("recurring") is not False,
                    "names": " ".join(str(v) for v in args.values() if isinstance(v, str))[:500]}
            elif item.get("name") == "CronDelete":
                wanted = [v for v in args.values() if isinstance(v, str) and len(v) >= 4]
                match = next((cid for cid, c in created.items()
                              if any(w in c.get("result", "") or w == cid for w in wanted)), None)
                if match:
                    del created[match]
    return cache["wake_until"], _open_tasks(cache, now)


# Permission modes passed back on resume. Bypassing permissions comes back
# only through the launch flags that allowed it in the first place.
RESUMABLE_MODES = {"acceptEdits", "plan", "auto", "dontAsk"}


def durable_tasks(cwd):
    """Scheduled tasks Claude keeps for a project across restarts
    (CronCreate with its persist option writes them to
    <project>/.claude/scheduled_tasks.json): how many, or None when the file
    is there but can't be read (counted as some)."""
    if not cwd:
        return 0
    path = os.path.join(cwd, ".claude", "scheduled_tasks.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        if not data:
            return 0
        data = data.get("tasks", data.get("jobs"))  # another shape: not known, so counted as some
    return len(data) if isinstance(data, list) else None


def claude_running(session_id, config_dir=None):
    """Whether any running Claude Code process has this session open, by
    Claude's own registry (<config>/sessions/<pid>.json, live pids only).
    Covers terminals and other Herdr sessions Earmark can't see."""
    for path in glob.glob(os.path.join(glob.escape(_claude_dir(config_dir)), "sessions", "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            pid = int(data.get("pid"))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if data.get("sessionId") != session_id:
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
        # A file left by a crash can name a pid now used by something else:
        # the process must have started when the file says Claude did.
        from . import procs
        started, recorded = procs.started_at(pid), data.get("startedAt")
        if isinstance(recorded, (int, float)) and started is not None and abs(started - recorded / 1000) > 30:
            continue
        return True
    return False


def claude_registry(pid, config_dir=None):
    """Claude Code's own record of a running process
    (<config>/sessions/<pid>.json): its status ("idle", "busy", ...) and
    whether Remote Control is on. {} when there's none."""
    try:
        with open(os.path.join(_claude_dir(config_dir), "sessions", f"{int(pid)}.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {"status": data.get("status") if isinstance(data.get("status"), str) else None,
            "remote": bool(data.get("bridgeSessionId")),
            "session_id": data.get("sessionId")}


# Launch options, per agent, read from `claude --help` (2.1.332) and `codex
# --help` (0.171): how many values each takes (0, 1, "+" one or more, "?"
# an optional one), and whether it comes back on resume. Options that start
# or pick a session, print and exit, or only matter at the first launch
# don't come back; neither does a prompt given on the command line. An
# option not listed here is "unknown": Earmark can't tell what it would
# drop, so automatic suspends leave that agent alone (the key asks first).
_KEEP, _DROP = True, False
_OPTIONS = {
    "claude": {
        "--add-dir": ("+", _KEEP), "--agent": (1, _KEEP), "--agents": (1, _KEEP),
        "--allow-dangerously-skip-permissions": (0, _KEEP), "--allowedTools": ("+", _KEEP),
        "--allowed-tools": ("+", _KEEP), "--append-system-prompt": (1, _KEEP),
        "--append-system-prompt-file": (1, _KEEP), "--autocompact": (1, _KEEP),
        "--ax-screen-reader": (0, _KEEP), "--bare": (0, _KEEP), "--betas": ("+", _KEEP),
        "--brief": (0, _KEEP), "--chrome": (0, _KEEP), "--no-chrome": (0, _KEEP),
        "--dangerously-skip-permissions": (0, _KEEP), "--debug-file": (1, _KEEP),
        "--disable-slash-commands": (0, _KEEP), "--disallowedTools": ("+", _KEEP),
        "--disallowed-tools": ("+", _KEEP), "--effort": (1, _KEEP),
        "--exclude-dynamic-system-prompt-sections": (0, _KEEP), "--fallback-model": (1, _KEEP),
        "--ide": (0, _KEEP), "--mcp-config": ("+", _KEEP), "--model": (1, _KEEP),
        "--permission-mode": (1, _KEEP), "--permission-prompts": (1, _KEEP), "--plugin-dir": (1, _KEEP),
        "--plugin-url": (1, _KEEP), "--remote-control-session-name-prefix": (1, _KEEP),
        "--restricted": (0, _KEEP), "--safe-mode": (0, _KEEP), "--setting-sources": (1, _KEEP),
        "--settings": (1, _KEEP), "--strict-mcp-config": (0, _KEEP), "--system-prompt": (1, _KEEP),
        "--system-prompt-file": (1, _KEEP), "--system-prompt-snapshot": (1, _KEEP), "--tools": ("+", _KEEP),
        "--verbose": (0, _KEEP), "--max-budget-usd": (1, _KEEP),
        "-c": (0, _DROP), "--continue": (0, _DROP), "-r": ("?", _DROP), "--resume": ("?", _DROP),
        "--session-id": (1, _DROP), "--fork-session": (0, _DROP), "-p": (0, _DROP), "--print": (0, _DROP),
        "--output-format": (1, _DROP), "--input-format": (1, _DROP), "--json-schema": (1, _DROP),
        "--include-hook-events": (0, _DROP), "--include-partial-messages": (0, _DROP),
        "--replay-user-messages": (0, _DROP), "--forward-subagent-text": (0, _DROP),
        "-n": (1, _DROP), "--name": (1, _DROP), "--file": ("+", _DROP), "--bg": (0, _DROP),
        "--background": (0, _DROP), "--desktop": (0, _DROP), "--environment": (1, _DROP),
        "--tmux": (0, _DROP), "--no-session-persistence": (0, _DROP),
    },
    "codex": {
        "-c": (1, _KEEP), "--config": (1, _KEEP), "--enable": (1, _KEEP), "--disable": (1, _KEEP),
        "--remote": (1, _KEEP), "--remote-auth-token-env": (1, _KEEP), "--strict-config": (0, _KEEP),
        "-m": (1, _KEEP), "--model": (1, _KEEP), "--oss": (0, _KEEP), "--local-provider": (1, _KEEP),
        "-p": (1, _KEEP), "--profile": (1, _KEEP), "-s": (1, _KEEP), "--sandbox": (1, _KEEP),
        "--approve-for-me": (0, _KEEP), "--dangerously-bypass-approvals-and-sandbox": (0, _KEEP),
        "--dangerously-bypass-hook-trust": (0, _KEEP), "-C": (1, _KEEP), "--cd": (1, _KEEP),
        "--worktree": (0, _KEEP), "--add-dir": (1, _KEEP), "-a": (1, _KEEP), "--ask-for-approval": (1, _KEEP),
        "--search": (0, _KEEP), "--no-alt-screen": (0, _KEEP),
        "--no-daemon": (0, _DROP), "-i": ("+", _DROP), "--image": ("+", _DROP), "--last": (0, _DROP),
        "--all": (0, _DROP), "--include-non-interactive": (0, _DROP),
    },
}
_UUIDISH = re.compile(r"[0-9A-Za-z][0-9A-Za-z-]{7,}")
# What can't be typed into every shell inside '...' (fish reads \ and '
# there differently), and control characters. One definition for all.
UNTYPABLE = re.compile(r"['\\\x00-\x1f\x7f]")


def launch_flags(agent, argv):
    """(options to keep on resume, options Earmark doesn't know) from an
    agent process's command line. Positional words (a first prompt, Codex's
    `resume <id>`) are dropped. For an agent without a table, every option
    is unknown."""
    args = list(argv or [])
    if args and os.path.basename(args[0]) in ("node", "bun", "deno"):
        # node [its own options] /path/cli.js ...: the script stands for the
        # program, and the launcher's options aren't the agent's.
        i = 1
        while i < len(args) - 1 and args[i].startswith("-"):
            i += 1
        args = args[i:]
    args = args[1:]
    table = _OPTIONS.get(agent)
    if table is None:
        return [], [a for a in args if a.startswith("-")]
    kept, unknown, i = [], [], 0
    while i < len(args):
        arg = args[i]
        name, eq, _ = arg.partition("=")
        if arg == "--":
            break  # everything after is the prompt
        if not arg.startswith("-") or arg == "-":
            i += 1  # a prompt, a subcommand or its session id
            continue
        if name not in table:
            unknown.append(arg)
            i += 1
            continue
        arity, keep = table[name]
        words = [arg]
        i += 1
        if not eq:
            if arity == 1:
                words += args[i:i + 1]
                i += 1
            elif arity == "+":
                while i < len(args) and not args[i].startswith("-"):
                    words.append(args[i])
                    i += 1
            elif arity == "?" and i < len(args) and _UUIDISH.fullmatch(args[i]):
                words.append(args[i])  # --resume <id>
                i += 1
        if keep:
            if any(UNTYPABLE.search(w) or w.startswith(("=", "%")) for w in words):  # zsh =cmd, fish %self
                # A value Earmark can't type safely into every shell (a
                # newline, an escape, a quote or a backslash): left behind,
                # so the agent counts as having options Earmark can't bring back.
                unknown.append(f"{name}=…")
            else:
                kept += words
    return kept, unknown


# Environment settings that decide which account, endpoint or model an agent
# talks to: Claude Code's ANTHROPIC_* and cloud switches, Codex's OPENAI_*,
# Grok's XAI_*, cloud profiles and proxies. A resume typed into the pane's
# shell gets the shell's values, not the ones the agent was started with
# (`ANTHROPIC_BASE_URL=... claude`, a function that sets a work profile), so
# the placeholder compares them before it resumes.
ACCOUNT_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "OPENAI_", "XAI_", "GROK_")
ACCOUNT_NAMES = {"AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID", "AWS_BEARER_TOKEN_BEDROCK",
                 "CLOUD_ML_REGION", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT", "CODEX_HOME",
                 "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"}


def account_env(env):
    """Fingerprints of the account settings in an environment, {name: hash}:
    hashed, so no key ever reaches Earmark's files. None (unreadable) stays
    None."""
    if env is None:
        return None
    return {k: hashlib.sha256(v.encode("utf-8", "surrogateescape")).hexdigest()[:16]
            for k, v in env.items() if k in ACCOUNT_NAMES or k.startswith(ACCOUNT_PREFIXES)}


def account_changes(recorded, env):
    """The account settings whose value in `env` (the placeholder's, so the
    shell's) isn't the one the agent was started with; [] when the agent's
    weren't known."""
    if recorded is None:
        return []
    now = account_env(env) or {}
    return sorted(k for k in set(recorded) | set(now) if recorded.get(k) != now.get(k))


def env_prefix(agent, config_dir):
    """`CLAUDE_CONFIG_DIR=<dir> ` for a Claude session from a folder of its
    own (shell syntax; only for a path safe to type), else ""."""
    if agent != "claude" or not config_dir or not os.path.isabs(config_dir) or UNTYPABLE.search(config_dir):
        return ""
    import shlex
    return "CLAUDE_CONFIG_DIR=" + shlex.quote(config_dir) + " "


def live_resume_argv(agent, session_id, overrides=None, flags=None, permission_mode=""):
    """The command that brings a suspended session back in its own pane: the
    resume command with the launch options kept (`flags`, from
    launch_flags), Claude's adjusted to the permission mode it was last in.
    The options go before the session id. None if Earmark can't resume it."""
    argv = resume_argv(agent, session_id, overrides)
    if not argv:
        return None
    flags = list(flags or [])
    if agent == "claude":
        flags = claude_resume_flags(flags, permission_mode)
    if not flags:
        return argv
    at = argv.index(session_id) if session_id in argv else len(argv)
    return argv[:at] + flags + argv[at:] if agent == "codex" else argv + flags


def claude_mode_since(path, offset):
    """The last permission mode Claude wrote to its transcript after
    `offset` bytes, or None if it wrote none. Claude records a Shift+Tab to
    plan or manual mode only when it exits (it re-stamps the mode in force
    then; checked with Claude Code 2.1.33x), so this read, after the stop,
    is the mode it was really in."""
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    mode = None
    for line in chunk.splitlines():
        if '"permissionMode"' in line:
            try:
                value = json.loads(line).get("permissionMode")
            except ValueError:
                continue
            if isinstance(value, str):
                mode = value
    return mode


# The modes that let Claude act without asking, and the words its footer
# shows for each while it's on.
WIDE_MODES = {"bypassPermissions": "bypass permissions on", "auto": "auto mode on"}


def launch_mode(flags):
    """The permission mode the launch options asked for, or ""."""
    mode = ""
    for i, f in enumerate(flags or []):
        if f == "--dangerously-skip-permissions":
            mode = "bypassPermissions"
        elif f == "--permission-mode" and i + 1 < len(flags):
            mode = flags[i + 1]
        elif f.startswith("--permission-mode="):
            mode = f.split("=", 1)[1]
    return mode


def mode_to_resume(after_exit, before, flags, screen):
    """The permission mode a suspended Claude comes back in: the one it
    wrote as it exited; failing that, the one read before the stop, but
    never a mode that acts without asking (auto, bypass) unless its footer
    showed it on the screen kept at the stop: Claude may have left it
    without writing so."""
    if after_exit is not None:
        return after_exit
    mode = before or launch_mode(flags)
    if mode in WIDE_MODES:
        shown = "\n".join(plain(line) for line in (screen or "").splitlines()[-8:]).lower()
        if WIDE_MODES[mode] not in shown:
            return "default"
    return before


def claude_resume_flags(flags, mode):
    """Launch flags adjusted to the permission mode the transcript says the
    session was last in (Shift+Tab changes it): the mode in force comes back,
    and no more. Bypassing permissions returns only where the launch flags
    allowed it; a session switched out of it comes back able to switch in
    again (--allow-dangerously-skip-permissions), not bypassing."""
    bypass_allowed = any(f in ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions")
                         for f in flags)
    if not (mode in RESUMABLE_MODES or mode == "default" or (mode == "bypassPermissions" and bypass_allowed)):
        # Nothing recorded (or nothing usable): as launched, but never
        # bypassing on a guess (the session may have switched out of it):
        # it comes back able to switch in again.
        out, i = [], 0
        while i < len(flags):
            f = flags[i]
            if f == "--dangerously-skip-permissions":
                out.append("--allow-dangerously-skip-permissions")
            elif f == "--permission-mode" and flags[i + 1:i + 2] == ["bypassPermissions"]:
                out.append("--allow-dangerously-skip-permissions")
                i += 1
            elif f == "--permission-mode=bypassPermissions":
                out.append("--allow-dangerously-skip-permissions")
            else:
                out.append(f)
            i += 1
        return out
    out, i = [], 0
    while i < len(flags):
        if flags[i] == "--permission-mode":
            i += 2
            continue
        if flags[i].startswith("--permission-mode=") or flags[i] in (
                "--dangerously-skip-permissions", "--allow-dangerously-skip-permissions"):
            i += 1
            continue
        out.append(flags[i])
        i += 1
    if bypass_allowed:
        out.append("--allow-dangerously-skip-permissions")
    if mode != "default":
        out += ["--permission-mode", mode]
    return out


# ------------------------------------------------------------ the screen

SGR = re.compile(r"\x1b\[([0-9;:]*)m")
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")


def plain(line):
    return ANSI.sub("", line)


def _is_rule(text):
    t = text.strip()
    run = len(t) - len(t.lstrip("─"))
    return run > 0 and (run >= 3 or not t[run:].strip())


def _hint_after(codes, hint):
    """Whether text drawn after an SGR sequence with these parameters is
    faint or italic (a hint), given that it was before. Parameters are split
    on ";"; an empty one means 0; a parameter with ":" is one attribute with
    its own operands (38:2::r:g:b, 4:3); 38/48/58 with ";" take the next 2
    (5;n) or 4 (2;r;g;b) parameters as their colour, never as styles."""
    params = codes.split(";") if codes else [""]
    i = 0
    while i < len(params):
        p = params[i]
        if ":" in p:
            i += 1
            continue
        n = int(p) if p.isdigit() else 0
        if n in (38, 48, 58):
            mode = params[i + 1] if i + 1 < len(params) else ""
            i += 3 if mode == "5" else 5 if mode == "2" else 1
            continue
        if n in (0, 22, 23):
            hint = False
        elif n in (2, 3):
            hint = True
        i += 1
    return hint


def _typed(line):
    """The text of an ANSI line without faint or italic runs: an empty prompt
    shows its placeholder hint that way, and a hint isn't a draft."""
    parts = SGR.split(line)
    kept, hint = [parts[0]], False
    for codes, text in zip(parts[1::2], parts[2::2]):
        hint = _hint_after(codes, hint)
        if not hint:
            kept.append(text)
    return plain("".join(kept))


def _claude_box(lines):
    """(top, bottom) line numbers of Claude Code's prompt box: the last pair
    of horizontal rules on screen with the ❯ prompt between them. None if
    there's no such pair."""
    rules = [i for i, line in enumerate(lines) if _is_rule(plain(line))]
    for top, bottom in reversed(list(zip(rules, rules[1:]))):
        if any(plain(line).lstrip().startswith(("❯", ">")) for line in lines[top + 1:bottom]):
            return top, bottom
    return None


def draft_text(screen, agent):
    """Text typed into the agent's prompt but not sent, from an ANSI screen
    capture: "" when the prompt is empty, the text when there is some, None
    when Earmark can't tell (an agent whose prompt it doesn't know, or a
    screen without one)."""
    lines = (screen or "").split("\n")
    if agent == "claude":
        box = _claude_box(lines)
        if not box:
            return None
        text = " ".join(_typed(line) for line in lines[box[0] + 1:box[1]]).strip()
        text = text.lstrip("❯>").strip()
        if text.startswith('Try "') and text.endswith('"'):
            # Claude's hint is drawn faint (and left out above); unstyled, it
            # could as well be typed: Earmark can't tell.
            return None
        return text
    if agent == "codex":
        prompts = [i for i, line in enumerate(lines) if plain(line).lstrip().startswith("›")]
        if not prompts:
            return None
        first = prompts[-1]
        line = _typed(lines[first]).strip()
        text = line[1:].strip() if line.startswith("›") else line
        # A draft can go on over indented lines (and start on one, after a
        # newline): read them up to the first blank line.
        more = []
        for following in lines[first + 1:]:
            typed = _typed(following)
            if not typed.strip() or not typed.startswith("  ") or any(k in typed for k in ("⏎", "⌃")):
                break  # a blank line, the box's end, or Codex's key hints below it
            more.append(typed.strip())
        return " ".join([text] + more).strip()
    return None


def cut_input_box(lines, agent):
    """A screen capture without the agent's own prompt and what's below it
    (the frozen view draws "Enter to resume" there instead)."""
    if agent == "claude":
        box = _claude_box(lines)
        if box:
            return lines[:box[0]]
    elif agent == "codex":
        prompts = [i for i, line in enumerate(lines) if plain(line).lstrip().startswith("›")]
        if prompts:
            return lines[:prompts[-1]]
    return lines
