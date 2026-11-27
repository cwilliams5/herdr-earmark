"""The placeholder in a suspended tab: `earmark.py suspended <session> <pane>`.

It shows the agent's last screen (dimmed) or a short notice, with "Press
Enter to resume". It's typed into the pane's shell as `placeholder &&
resume command`: on Enter it exits 0 and the shell starts the agent as a new
job, the way a person would (an agent exec'd in its place kept its process
group, and Herdr lost track of it). Ctrl+C, a hangup or any refusal exits 1,
so the shell starts nothing; Ctrl+C also files the session in Earmark's
archive.

No curses: the frozen view replays the captured ANSI screen as it was, on
the alternate screen, and puts the shell's screen back on the way out.
"""
import os
import re
import select
import signal
import sys
import termios
import time
import tty

from . import agents, config, core, store, suspend, text as _text

# Terminal modes an agent may have left on (it was stopped, not quit):
# mouse reporting, focus events, the kitty keyboard protocol,
# modifyOtherKeys, application cursor keys. (Bracketed paste the placeholder
# turns on itself, to set pastes aside, and off as it leaves.)
RESET_MODES = ("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l\x1b[?1004l"
               "\x1b[<99u\x1b[>4;0m\x1b[?1l\x1b>")
ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[?1007l\x1b[?2004h"  # alternate screen, no cursor, wheel isn't arrows, pastes marked
LEAVE_SCREEN = "\x1b[?2004l\x1b[0m\x1b[?25h\x1b[?1049l"
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"

ENTER = re.compile(rb"[\r\n]|\x1b\[13(;1(:1)?)?u")
CTRL_C = re.compile(rb"\x03|\x1b\[99;5(:1)?u")
SGR_ONLY = re.compile(r"(\x1b\[[0-9;:]*m)|\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1a\x1c-\x1f\x7f]")

DIM, BOLD, REVERSE, RESET = "\x1b[2m", "\x1b[1m", "\x1b[7m", "\x1b[0m"


width = _text.char_cols


def crop(line, cols):
    """An ANSI line cut to cols terminal columns; colours are kept, any
    other escape sequence and control character is dropped."""
    out, used = [], 0
    pos = 0
    for m in SGR_ONLY.finditer(line):
        used = _take(line[pos:m.start()], cols, used, out)
        if m.group(1):
            out.append(m.group(1))
        pos = m.end()
    _take(line[pos:], cols, used, out)
    return "".join(out) + RESET


def _take(text, cols, used, out):
    for ch in CONTROL.sub("", text.replace("\t", "    ")):
        w = width(ch)
        if used + w > cols:
            break
        out.append(ch)
        used += w
    return used


fit = _text.fit
ago = _text.ago


def pad(value, cols):
    return value + " " * max(0, cols - _text.cols(value))


def frozen_lines(screen, agent):
    """The captured screen without the agent's own prompt box (and what's
    below it), and without blank lines at the bottom."""
    lines = agents.cut_input_box((screen or "").split("\n"), agent)
    while lines and not agents.plain(lines[-1]).strip():
        lines.pop()
    return lines


def dimmed(line):
    """A frozen line drawn faint, colours kept: the screen reads as asleep."""
    return DIM + line.replace("\x1b[0m", "\x1b[0m" + DIM).replace("\x1b[m", "\x1b[m" + DIM) \
        .replace("\x1b[22m", "\x1b[22m" + DIM)


def compose(rec, cfg, screen, rows, cols, now, message=""):
    """The whole placeholder screen as a list of rows (strings with ANSI).
    `message`, when there's one, takes the bar's place beside the key."""
    name, other = core.names(rec, cfg["title_first"])
    when = ago(rec.get("at"), now)
    state = (f"Finished while you were away, not read yet · suspended {when}" if rec.get("unseen")
             else f"Suspended {when} to free memory")
    hint = "Ctrl+C: keep the tab as a plain shell, file the session in Earmark's archive"
    lines = frozen_lines(screen, rec.get("agent")) if cfg["suspend"]["show"] == "frozen" else []
    if lines and rows >= 6 and cols >= 30:
        key = "  Press Enter to resume  "
        if message:  # beside the key, then in place of the hint, over as many rows as it needs (up to 4)
            beside = cols - len(key) - 2
            said = (_text.wrap_cols(_text.clean(message), beside) if beside >= 30 else ["", message]) or [""]
            more = _text.wrap_cols(" ".join(said[1:]), cols - 2)[:3]
            rest = " " + said[0]
            below = [f"{BOLD}{fit('  ' + m, cols)}{RESET}" for m in more] or [f"{DIM}{fit('  ' + hint, cols)}{RESET}"]
        else:
            rest = fit(f" {state} · {name}", cols - len(key))
            below = [f"{DIM}{fit('  ' + hint, cols)}{RESET}"]
        room = max(0, rows - 2 - len(below))
        body = [dimmed(crop(line, cols)) for line in lines][-room:] if room else []
        body = [""] * (room - len(body)) + body
        bar = f"{REVERSE}{BOLD}{key}{RESET}{REVERSE}{pad(rest, cols - len(key))}{RESET}"
        return body + [f"{DIM}{'─' * cols}{RESET}", bar] + below
    # The notice: a few centred lines.
    key = "   Press Enter to resume   "
    block = [
        (BOLD, fit(name, cols - 2)),
        (DIM, fit(f"{rec.get('agent') or 'agent'} · {state[0].lower() + state[1:]}", cols - 2)),
        ("", ""),
        (REVERSE + BOLD, key if len(key) <= cols else fit("Enter to resume", cols)),
        ("", ""),
    ] + ([(BOLD, line) for line in (_text.wrap_cols(_text.clean(message), cols - 2) or [""])[:4]] if message
         else [(DIM, fit(hint, cols - 2))])
    if other:
        block.insert(1, (DIM, fit(other, cols - 2)))
    top = max(0, (rows - len(block)) // 2)
    out = [""] * top
    for attr, line in block[:max(0, rows - top)]:
        out.append(" " * max(0, (cols - _text.cols(line)) // 2) + (f"{attr}{line}{RESET}" if attr and line else line))
    return out + [""] * max(0, rows - len(out))


class Terminal:
    """Raw input, the alternate screen, and everything put back on exit."""

    def __init__(self, fd):
        self.fd = fd
        self.saved = termios.tcgetattr(fd)

    def __enter__(self):
        # TCSANOW, not the default flush: an Enter pressed (or sent by the
        # key or "resume on view") while Python was starting must count.
        tty.setraw(self.fd, termios.TCSANOW)
        sys.stdout.write(RESET_MODES + ENTER_SCREEN)
        sys.stdout.flush()
        return self

    def __exit__(self, *exc):
        sys.stdout.write(LEAVE_SCREEN)
        sys.stdout.flush()
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)


class Hangup(Exception):
    pass


def outside_paste(data, pasting):
    """The keys in `data` that aren't part of a (bracketed) paste, and
    whether a paste is still going on at its end: pasting a prompt into
    what looks like the agent's own screen is a natural mistake, and its
    newlines aren't Enter."""
    out = b""
    while data:
        if pasting:
            end = data.find(PASTE_END)
            if end < 0:
                return out, True
            data, pasting = data[end + len(PASTE_END):], False
        else:
            start = data.find(PASTE_START)
            if start < 0:
                return out + data, False
            out, data, pasting = out + data[:start], data[start + len(PASTE_START):], True
    return out, pasting


def key_action(data):
    """What a burst of input means: "leave" (Ctrl+C), "resume" (Enter), or
    None (anything else: arrows, focus reports, other keys)."""
    if CTRL_C.search(data):
        return "leave"
    if ENTER.search(data):
        return "resume"
    return None


def wait_for_key(rec, cfg, screen, fd, message=""):
    """Draw and wait: "resume", "leave", or "hangup" (the pane went away).
    It wakes for a key, a resize, or the minute turning (to redraw the
    "suspended 5 min ago" line when its text changes)."""
    resized = [True]
    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_r, False)
    os.set_blocking(wake_w, False)
    old_wakeup = signal.set_wakeup_fd(wake_w)
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))

    def hangup(*_):
        raise Hangup()

    signal.signal(signal.SIGHUP, hangup)
    signal.signal(signal.SIGTERM, hangup)
    name = core.names(rec, cfg["title_first"])[0]
    sys.stdout.write(f"\x1b]2;{fit('Suspended: ' + name, 80)}\x07")
    drawn_minute, drawn, pasting = None, None, False
    try:
        while True:
            minute = int(time.time() // 60)
            if resized[0] or minute != drawn_minute:
                size = os.get_terminal_size(fd)
                rows = compose(rec, cfg, screen, size.lines, size.columns, time.time(), message)[:size.lines]
                if resized[0] or rows != drawn:  # "5 min ago" turns "6 min ago": redrawn; "2 hours ago" stays
                    sys.stdout.write("\x1b[H\x1b[2J" + "\r\n".join(rows))
                    sys.stdout.flush()
                resized[0], drawn, drawn_minute = False, rows, minute
            ready, _, _ = select.select([fd, wake_r], [], [], 60.5 - time.time() % 60)
            if wake_r in ready:
                try:
                    os.read(wake_r, 512)
                except OSError:
                    pass
            if fd not in ready:
                continue
            data = os.read(fd, 1024)
            if not data:
                return "hangup"
            keys, pasting = outside_paste(data, pasting)
            action = key_action(keys)
            if action:
                return action
    except Hangup:
        return "hangup"
    finally:
        signal.set_wakeup_fd(old_wakeup)
        os.close(wake_r)
        os.close(wake_w)


def main(session, pane_id):
    """Exit status 0 means "resume" (the shell runs the resume command after
    it); anything else means the shell starts nothing."""
    rec = suspend.record(session, pane_id)
    if not rec or rec.get("state") not in ("stopping", "suspended", "waking"):
        print("Earmark: nothing is suspended in this pane.")
        return 1
    cfg = config.load()
    screen = ""
    if cfg["suspend"]["show"] == "frozen" and rec.get("screen"):
        try:
            with open(rec["screen"], encoding="utf-8", errors="replace") as f:
                screen = f.read()
        except OSError:
            pass
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        print("Earmark: the placeholder needs a terminal.")
        return 1
    facts = agents.session_facts(rec.get("agent"), rec.get("session_id"), config_dir=rec.get("config_dir"), title=False)
    if rec.get("config_dir") is not None and facts.get("known") and not facts.get("exists"):
        # The agent deleted the conversation while it was suspended (Claude
        # Code's cleanupPeriodDays): there's nothing to resume.
        with Terminal(fd):
            wait_for_key(rec, cfg, "", fd, "This conversation no longer exists (the agent cleaned it up); "
                                           "press Enter to close this placeholder")
        unmark(session, pane_id)
        suspend.drop_record(session, pane_id, "its conversation is gone")
        print("Earmark: that session's conversation no longer exists.")
        return 1
    message, why, warned = "", "", False
    with Terminal(fd):
        while True:
            action = wait_for_key(rec, cfg, screen, fd, message)
            if action != "resume":
                break
            # This process runs in the shell the resume will run in: its
            # environment is what the agent would get.
            changed = [] if warned else agents.account_changes(rec.get("account"), os.environ)
            if changed:
                warned = True
                message = (f"This shell's {', '.join(changed[:3])}{' and more' if len(changed) > 3 else ''} "
                           "isn't what the agent was started with: it would come back with the shell's "
                           "(another account or endpoint). Enter again resumes it anyway; Ctrl+C leaves it.")
                continue
            why = suspend.mark_waking(session, pane_id, fallback=rec)
            if why != suspend.NO_ANSWER:
                break
            message = why  # Herdr didn't answer: stay, and say so; Enter tries again
    sys.stdout.write("\x1b]2;\x07")
    if action == "hangup":
        return 1
    unmark(session, pane_id)
    if action == "leave":
        if suspend.to_archive(session, pane_id, "exited"):
            print("Earmark: this tab is a plain shell now; its session is in Earmark's archive.")
        return 1
    if why:
        print(f"Earmark: {why}.")
        return 1
    sys.stdout.write("\x1b[H\x1b[2J")
    sys.stdout.flush()
    discard_input(fd)  # an Enter queued since (the key, resume on view) mustn't reach the agent starting
    return 0


def discard_input(fd):
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
    except (termios.error, OSError):
        pass


def unmark(session, pane_id):
    """Take the sleep mark off this tab's name on the way out (unless
    another pane in the tab is still suspended; the hooks tidy that case).
    Only this Herdr session's records count: tab ids repeat across
    sessions."""
    from . import herdr
    try:
        tab_id = herdr.pane(pane_id).get("tab_id")
        label = (herdr.run("tab", "get", tab_id) or {}).get("tab", {}).get("label") or ""
        mine = store.load_index().get("sessions", {}).get(session) or {}
        mark = (mine.get("marked") or {}).get(tab_id)
        others = [pid for pid, r in (mine.get("suspended") or {}).items() if pid != pane_id and r.get("tab_id") == tab_id]
        if mark and not others:
            suspend.unmark_tab(tab_id, label, mark, session=session)
    except Exception:
        pass
