"""The note popup (PLAN L3, L4): this workspace's note in a read view;
e edits it in your editor (inside the popup), u asks a Claude session in
the workspace to update it (the /herdr-note skill), q or Esc closes.

`u` submits "/herdr-note" through Herdr's own `agent prompt`, and only to a
Claude that's idle or done (Herdr refuses a blocked one itself) with an
empty prompt box (the suspend code's reader: nothing typed is ever mixed in
or lost) and the skill installed where that Claude looks for skills.
"""
import curses
import os
import shlex
import shutil
import subprocess
import tempfile
import time

from . import agents, core, herdr, notes, store, text

BUTTON5_PRESSED = getattr(curses, "BUTTON5_PRESSED", 0x200000)
SKILL = "herdr-note"
cols, fit, clean = text.cols, text.fit, text.clean


# ------------------------------------------------------------------- view

def render(note, width):
    """The note as (line, style) pairs wrapped to width: headings bold,
    bullets and checkboxes drawn, code dim; anything else as written."""
    out = []
    code = False
    for raw in note.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            code = not code
            continue
        style = "dim" if code else "plain"
        if not code:
            stripped = line.lstrip()
            indent = line[:len(line) - len(stripped)]
            if stripped.startswith("#"):
                line, style = stripped.lstrip("#").strip(), "bold"
            elif stripped[:6].lower() in ("- [ ] ", "* [ ] "):
                line = indent + "☐ " + stripped[6:]
            elif stripped[:6].lower() in ("- [x] ", "* [x] "):
                line = indent + "☑ " + stripped[6:]
            elif stripped[:2] in ("- ", "* ", "+ "):
                line = indent + "• " + stripped[2:]
        out += [(part, style) for part in wrap(clean(line), width)] or [("", style)]
    return out


def wrap(line, width):
    """A line cut into pieces of at most width columns, at spaces when it can."""
    if width < 1:
        return [line]
    pieces = []
    while cols(line) > width:
        cut, used = 0, 0
        for i, ch in enumerate(line):
            used += text.char_cols(ch)
            if used > width:
                break
            cut = i + 1
        cut = max(cut, 1)  # a character wider than the line still moves it on
        space = line.rfind(" ", 0, cut + 1)
        at = space if space > width // 3 else cut
        pieces.append(line[:at].rstrip())
        line = line[at:].lstrip()
    if line or not pieces:
        pieces.append(line)
    return pieces


# ------------------------------------------------------------- ask Claude

def skill_installed(config_dir):
    base = config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.exists(os.path.join(base, "skills", SKILL, "SKILL.md"))


def candidates(session, workspace_id):
    """(ready, why-not) for `u`: the Claude panes in this workspace that can
    take the request now (idle, the skill installed, an empty prompt box on
    the pane's bottom screen, whatever it's scrolled to), and for the others
    a reason each."""
    snap = herdr.snapshot()
    with store.locked():
        notes_of = (store.load_index().get("sessions", {}).get(session) or {}).get("panes") or {}
    ready, why = [], []
    for pid, p in snap["panes"].items():
        if p.get("workspace_id") != workspace_id or p.get("agent") != "claude":
            continue
        tab = (snap["tabs"].get(p.get("tab_id")) or {}).get("label") or pid
        status = p.get("agent_status")
        if status not in ("idle", "done"):
            why.append(f"{tab}: {'waiting on you' if status == 'blocked' else 'busy'}")
            continue
        if not skill_installed((notes_of.get(pid) or {}).get("config_dir")):
            why.append(f"{tab}: the {SKILL} skill isn't installed")
            continue
        try:
            draft = agents.draft_text(herdr.read_screen(pid, rows=(p.get("scroll") or {}).get("viewport_rows")),
                                      "claude")
        except herdr.HerdrError:
            draft = None
        if draft is None:
            why.append(f"{tab}: can't read its prompt")
        elif draft:
            why.append(f"{tab}: has unsent text")
        else:
            ready.append((pid, tab))
    return ready, why


def ask(pane_id):
    """Submit /herdr-note to that Claude (Herdr refuses a blocked agent)."""
    herdr.run("agent", "prompt", pane_id, "/" + SKILL)


# ------------------------------------------------------------------ popup

def editor_argv():
    for name in ("VISUAL", "EDITOR"):
        value = os.environ.get(name)
        if value:
            try:
                argv = shlex.split(value)
            except ValueError:
                continue
            if argv and shutil.which(argv[0]):
                return argv
    for name in ("nvim", "vim", "vi", "nano"):
        if shutil.which(name):
            return [name]
    return None


class NotePopup:
    def __init__(self, session, workspace_id, label=""):
        self.session, self.wid, self.label = session, workspace_id, label
        self.path = notes.note_path(session, workspace_id)
        self.note, self.stamp = "", None
        self.top = 0
        self.message = ""
        self.picking = None  # [(pane, tab)] while choosing which Claude to ask
        self.buttons = {}
        self.load()

    def load(self):
        try:
            st = os.stat(self.path)
            stamp = (st.st_size, st.st_mtime_ns)
        except OSError:
            stamp = None
        if stamp != self.stamp:
            self.note, self.stamp = notes.read(self.session, self.wid), stamp
            return True
        return False

    def lines(self, w):
        if not self.note.strip():
            return [("No note for this workspace yet.", "dim"), ("", "plain"),
                    ("e  write one in your editor", "dim"), ("u  ask a Claude session here to write it", "dim")]
        return render(self.note, w - 2)

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()
        title = f" Note · {self.label} " if self.label else " Note "
        put(scr, 0, 0, fit(title, w - 1), curses.A_BOLD)
        body = self.lines(w)
        room = max(1, h - 3)
        self.top = max(0, min(self.top, len(body) - room))
        for i, (line, style) in enumerate(body[self.top:self.top + room]):
            attr = curses.A_BOLD if style == "bold" else curses.A_DIM if style == "dim" else 0
            put(scr, 2 + i, 1, fit(line, w - 2), attr)
        self.draw_footer(scr, h, w)
        scr.refresh()

    def draw_footer(self, scr, h, w):
        self.buttons = {}
        if self.picking:
            parts = [(str(n), f"[{n}] {tab}") for n, (_, tab) in enumerate(self.picking, 1)][:9] + [("esc", "Esc")]
        else:
            parts = [("e", "[e] Edit"), ("u", "[u] Ask Claude"), ("q", "[q] Close")]
        x = 1
        if self.message:
            put(scr, h - 2, 1, fit(self.message, w - 2), curses.A_BOLD)
        if self.picking:
            put(scr, h - 2, 1, fit("Ask which Claude?", w - 2), curses.A_BOLD)
        for key, label in parts:
            if x + cols(label) >= w:
                break
            put(scr, h - 1, x, label, curses.A_REVERSE if key in ("e", "u") else curses.A_DIM)
            self.buttons[key] = (x, x + cols(label))
            x += cols(label) + 2

    def edit(self, scr):
        """The user's editor on a copy of the note (hidden, in the notes
        folder), saved back in one write that names the version it started
        from: a note a Claude wrote meanwhile (`u`) is kept, the edit below it."""
        argv = editor_argv()
        if not argv:
            self.message = "No editor found (set EDITOR)."
            return
        before = notes.read(self.session, self.wid)
        fd, copy = tempfile.mkstemp(prefix=".edit-", suffix=".md", dir=os.path.dirname(self.path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(before)
            curses.endwin()
            try:
                subprocess.call(argv + [copy])
            except OSError as e:
                self.message = f"{argv[0]}: {e}"
                return
            finally:
                scr.refresh()
            with open(copy, encoding="utf-8", errors="replace") as f:
                edited = f.read(notes.LIMIT)
        finally:
            try:
                os.unlink(copy)
            except OSError:
                pass
        self.message = ""
        if edited != before:
            self.save_edit(before, edited)
        self.load()

    def save_edit(self, before, edited):
        try:  # an emptied note is no note
            notes.write(self.session, self.wid, edited, expect=notes.version(before), clear=True)
        except notes.Conflict:
            now = notes.read(self.session, self.wid)
            if edited.strip():
                notes.write(self.session, self.wid, now.rstrip("\n") + "\n\n---\n\n" + edited, clear=True)
                self.message = "The note changed while you edited it (a Claude wrote it?): your edit is below it."
            else:
                self.message = "The note changed while you edited it, so it wasn't cleared."
    def ask_claude(self):
        try:
            ready, why = candidates(self.session, self.wid)
        except herdr.HerdrError as e:
            self.message = f"Herdr didn't answer ({e})."
            return
        if not ready:
            self.message = "No Claude here can take it now: " + ("; ".join(why) if why else "none is running")
            if any("skill" in y for y in why):
                self.message += " (see Earmark's README: Notes)"
            return
        if len(ready) > 1:
            self.picking = ready
            return
        self.send(*ready[0])

    def send(self, pane_id, tab):
        """Asks that Claude, checked once more first: one picked from the list
        may have started working, or been typed into, since it was listed."""
        self.picking = None
        try:
            ready, why = candidates(self.session, self.wid)
        except herdr.HerdrError as e:
            self.message = f"Herdr didn't answer ({e})."
            return
        if pane_id not in [pid for pid, _ in ready]:
            reason = next((y for y in why if y.startswith(f"{tab}:")), f"{tab}: not here any more")
            self.message = f"Didn't ask: {reason}."
            return
        try:
            ask(pane_id)
            self.message = f"Asked Claude in “{tab}”; the note shows here when it's done."
        except herdr.HerdrError as e:
            self.message = f"Couldn't ask Claude in “{tab}” ({e})."

    def on_key(self, scr, key):
        """True to close."""
        if self.picking:
            if key in ("\x1b", "q"):
                self.picking = None
            elif isinstance(key, str) and key.isdigit() and 1 <= int(key) <= len(self.picking):
                self.send(*self.picking[int(key) - 1])
            return False
        if key in ("q", "\x1b"):
            return True
        if key in ("e", "\n", curses.KEY_ENTER):
            self.edit(scr)
        elif key == "u":
            self.ask_claude()
        elif key in (curses.KEY_DOWN, "j"):
            self.top += 1
        elif key in (curses.KEY_UP, "k"):
            self.top = max(0, self.top - 1)
        elif key == curses.KEY_NPAGE:
            self.top += max(1, scr.getmaxyx()[0] - 4)
        elif key == curses.KEY_PPAGE:
            self.top = max(0, self.top - max(1, scr.getmaxyx()[0] - 4))
        elif key == curses.KEY_HOME:
            self.top = 0
        elif key == curses.KEY_END:
            self.top = 10 ** 9
        return False

    def on_mouse(self, scr):
        try:
            _, x, y, _, b = curses.getmouse()
        except curses.error:
            return False
        if b & curses.BUTTON4_PRESSED:
            self.top = max(0, self.top - 3)
            return False
        if b & BUTTON5_PRESSED:
            self.top += 3
            return False
        if b & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED) and y == scr.getmaxyx()[0] - 1:
            for key, (x0, x1) in self.buttons.items():
                if x0 <= x < x1:
                    return self.on_key(scr, "\x1b" if key == "esc" else key)
        return False

    def run(self, scr):
        curses.set_escdelay(25)
        curses.curs_set(0)
        curses.use_default_colors()
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        scr.timeout(1000)  # the note changes (an edit elsewhere, Claude writing it): shown within a second
        while True:
            self.draw(scr)
            try:
                key = scr.get_wch()
            except curses.error:
                self.load()
                continue
            except KeyboardInterrupt:
                return
            if key == curses.KEY_RESIZE:
                continue
            if key == curses.KEY_MOUSE:
                if self.on_mouse(scr):
                    return
            elif self.on_key(scr, key):
                return


def put(scr, y, x, s, attr=0):
    try:
        scr.addstr(y, x, s, attr)
    except curses.error:
        pass


def main(session, workspace_id, label=""):
    curses.wrapper(NotePopup(session, workspace_id, label).run)
