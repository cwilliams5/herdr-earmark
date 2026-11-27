"""The small popup the suspend key speaks through.

Herdr's own notifications (`herdr notification show`) follow its
`[ui.toast] delivery` setting, which is off by default: a refusal shown only
there looks like the key did nothing, and a "press again to confirm" nobody
saw could be confirmed by a second press meant as "did it register?". So
the key opens this popup instead: a message closes on any key (or by
itself after SHOW_WAIT), and a doubt is confirmed only by `y` in it.

Raw termios like the placeholder; no curses."""
import json
import os
import select
import sys
import termios
import time
import tty

from . import PLUGIN_ID, herdr, text

ENV = "EARMARK_MESSAGE"
SHOW_WAIT = 8    # seconds a message stays up without a key
ASK_WAIT = 60    # seconds a question waits for y; then the agent is kept
KEY_DELAY = 0.4  # keys in the first moment after the question appears don't answer it


def show(title, body="", ask=None, focus=True):
    """Open the popup (from the key's action). `ask`: {"session",
    "pane_id", "why"} makes it a question that `y` confirms (always
    focused). focus=False shows a message without taking the keyboard
    (an answer that comes long after the press). Falls back to a Herdr
    notification if the popup can't be opened."""
    payload = {"title": title, "body": body}
    if ask:
        payload["ask"] = ask
    try:
        herdr.run("plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", "message",
                  "--focus" if (focus or ask) else "--no-focus", "--env", f"{ENV}={json.dumps(payload)}")
        return True
    except herdr.HerdrError:
        herdr.notify(title, body)
        return False


wrap_cols = text.wrap_cols  # shared with the placeholder


def lines(title, body, hint, width, height=24):
    """What the popup draws, from its second row: the title, the hint (what
    a key does: always on screen, even in a small popup), then the body
    wrapped to the width and cut to the rows left (ending in … if cut)."""
    width = max(10, width - 4)
    out = [text.fit(title, width)] + ([text.fit(hint, width)] if hint else []) + [""]
    body_rows = []
    for para in (body or "").split("\n"):
        body_rows += wrap_cols(text.clean(para), width) or [""]
    room = max(1, height - 2 - len(out))
    if len(body_rows) > room:
        body_rows = body_rows[:room - 1] + [text.fit(body_rows[room - 1] + " …", width)]
    return out + body_rows


def draw(title, body, hint):
    try:
        size = os.get_terminal_size()
        cols, rows_ = size.columns, size.lines
    except OSError:
        cols, rows_ = 60, 12
    rows = lines(title, body, hint, cols, rows_)
    out = ["\x1b[2J\x1b[H\x1b[?25l"]
    for i, line in enumerate(rows):
        style = "\x1b[1m" if i == 0 else "\x1b[2m" if (i == 1 and hint) else ""
        out.append(f"\x1b[{i + 2};3H{style}{line}\x1b[0m")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def read_key(fd, timeout):
    """One key press, or b"" when the time runs out (or input ends)."""
    deadline = time.time() + timeout
    while True:
        left = deadline - time.time()
        if left <= 0:
            return b""
        ready, _, _ = select.select([fd], [], [], left)
        if ready:
            try:
                return os.read(fd, 32) or b""
            except OSError:
                return b""


def read_answer(fd, timeout, echo=None):
    """"y" when `y` then Enter is typed, else "" (any other key, Esc,
    Ctrl+C, the time running out or input ending), so a word being typed
    elsewhere ("my yard") never confirms and `n` closes at once. `echo` is
    told what's typed so far (shown, so a `y` doesn't look ignored)."""
    deadline = time.time() + timeout
    typed = ""
    while True:
        key = read_key(fd, max(0.0, deadline - time.time()))
        if not key or b"\x1b" in key or b"\x03" in key:
            return ""
        for ch in key.decode("utf-8", "replace"):
            if ch in "\r\n":
                return "y" if typed.lower() == "y" else ""
            if ch in "\x7f\b":
                typed = typed[:-1]
            elif ch.isprintable() and not ch.isspace():
                typed += ch
            if typed and typed.lower() != "y":
                return ""
            if echo:
                echo(typed)


def main():
    try:
        data = json.loads(os.environ.get(ENV) or "{}")
    except ValueError:
        data = {}
    title, body, ask = data.get("title") or "Earmark", data.get("body") or "", data.get("ask")
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return 1
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd, termios.TCSANOW)
        termios.tcflush(fd, termios.TCIFLUSH)  # keys typed before the question was shown don't answer it
        if not ask:
            draw(title, body, "Any key closes this.")
            time.sleep(KEY_DELAY)  # typing that went on after the press doesn't close it unread
            termios.tcflush(fd, termios.TCIFLUSH)
            read_key(fd, SHOW_WAIT)
            return 0
        hint = "y then Enter: suspend it anyway    any other key: keep it running"
        draw(title, body, hint)
        time.sleep(KEY_DELAY)  # a word being typed as the popup opened isn't an answer
        termios.tcflush(fd, termios.TCIFLUSH)
        echoed = lambda typed: draw(title, body, "y  now Enter to suspend it anyway    Backspace: undo" if typed else hint)
        if read_answer(fd, ASK_WAIT, echo=echoed) != "y":
            return 0
        from . import suspend
        # The suspend can take half a minute (the agent's exit, Herdr letting
        # go, the placeholder): a worker does it, so this modal popup closes
        # now and Herdr stays usable. The worker reports only if it didn't.
        if suspend.spawn_worker(["--session", str(ask.get("session")), "--pane", str(ask.get("pane_id")),
                                 "--accept", str(ask.get("why")), "--pressed", repr(time.time())]):
            return 0
        draw("Suspending…", "", "")
        why = suspend.confirm(ask.get("session"), ask.get("pane_id"), ask.get("why"))
        if why:
            draw("Earmark kept it running", why[0].upper() + why[1:] + ".", "Any key closes this.")
            read_key(fd, SHOW_WAIT)
        return 0
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[2J\x1b[H")
        sys.stdout.flush()
