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
import json
import os
import re
import sqlite3

RESUME = {
    "pi": ["pi", "--session", "{id}"],
    "antigravity-cli": ["agy", "--conversation", "{id}"],
    "omp": ["omp", "--resume={id}"],
    "claude": ["claude", "--resume", "{id}"],
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


def resume_argv(agent, session_id, overrides=None):
    """The command that reopens a session, or None if Earmark doesn't know one."""
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

def _claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def claude_transcript(session_id):
    if not re.fullmatch(r"[0-9A-Za-z-]+", session_id or ""):
        return None
    hits = glob.glob(os.path.join(_claude_dir(), "projects", "*", f"{session_id}.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


_COMMAND_NOISE = ("<local-command", "<command-name>", "<command-message>", "<command-args>")


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


def claude_has_content(path, max_lines=5000):
    """True if the transcript holds at least one real prompt (not just /exit)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n >= max_lines:
                    return True  # long transcripts are real conversations
                if '"user"' not in line:
                    continue
                try:
                    if _real_prompt(json.loads(line)):
                        return True
                except ValueError:
                    continue
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


def session_facts(agent, session_id):
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
        return reader(session_id)
    except (OSError, ValueError, sqlite3.Error):
        return dict(UNKNOWN)


def _claude_facts(session_id):
    if not os.path.isdir(os.path.join(_claude_dir(), "projects")):
        return dict(UNKNOWN)
    path = claude_transcript(session_id)
    if not path:
        return {"known": True, "exists": False, "has_content": False, "title": "", "last_active": None}
    return {"known": True, "exists": True, "has_content": claude_has_content(path),
            "title": claude_title(path), "last_active": os.path.getmtime(path), "source": path}


# ------------------------------------------------------------------- Codex

def _codex_db():
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    dbs = glob.glob(os.path.join(home, "state_*.sqlite"))
    number = lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0)
    return max(dbs, key=number) if dbs else None


def _codex_facts(session_id):
    """Codex keeps a `threads` table: a generated name, the first message, the
    last update, and the path of the session's log (its "rollout")."""
    db = _codex_db()
    if not db:
        return dict(UNKNOWN)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
    try:
        row = con.execute("select rollout_path, name, title, first_user_message, updated_at "
                          "from threads where id = ?", (session_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {"known": True, "exists": False, "has_content": False, "title": "", "last_active": None}
    rollout, name, title, first, updated = row
    exists = not rollout or os.path.exists(rollout)
    return {"known": True, "exists": exists, "has_content": bool(first or title),
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
