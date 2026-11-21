"""What Earmark knows about each coding agent.

RESUME is Herdr's own table of resume commands ("Native session restore",
herdr.dev/docs/session-state, Herdr 0.9.5), keyed by the agent names Herdr
reports (`herdr integration status`). Users can override or add entries in
config.toml's [resume] table.

Claude Code also gets a deeper look: its transcript tells whether a session
exists, whether it has anything to resume, its title and its last activity.
Other agents rely on keep_days alone.
"""
import glob
import json
import os
import re

RESUME = {
    "pi": ["pi", "--session", "{id}"],
    "antigravity-cli": ["agy", "--conversation", "{id}"],
    "omp": ["omp", "--resume={id}"],
    "claude": ["claude", "--resume", "{id}"],
    "codex": ["codex", "resume", "{id}"],
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
GENERIC_TITLES = {"", "claude", "claude code", "codex", "pi", "grok", "copilot", "shell"}


def resume_argv(agent, session_id, overrides=None):
    """The command that reopens a session, or None if Earmark doesn't know one."""
    if agent == "letta" and session_id.startswith("default:"):
        return ["letta", "--conversation", "default", "--agent", session_id.split(":", 1)[1]]
    template = (overrides or {}).get(agent) or RESUME.get(agent)
    if not template:
        return None
    return [part.replace("{id}", session_id) for part in template]


def clean_title(title, agent=None):
    """A terminal title without the agent's status glyph ("✳ Fix tests" -> "Fix tests").
    Returns "" for titles that only name the agent."""
    title = re.sub(r"^[^\w(\[\"'`]+", "", (title or "")).strip()
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


def session_facts(agent, session_id):
    """What Earmark can learn about a session from the agent's own files:
    {"known": bool, "exists": bool, "has_content": bool, "title": str,
    "last_active": float or None}. "known" is False for agents Earmark can't
    look into; then the rest is unknown and the caller relies on keep_days."""
    if agent != "claude":
        return {"known": False, "exists": True, "has_content": True, "title": "", "last_active": None}
    path = claude_transcript(session_id)
    if not path:
        return {"known": True, "exists": False, "has_content": False, "title": "", "last_active": None}
    return {"known": True, "exists": True, "has_content": claude_has_content(path),
            "title": claude_title(path), "last_active": os.path.getmtime(path)}
