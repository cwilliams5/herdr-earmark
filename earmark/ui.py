"""The archive popup: a terminal UI in a Herdr popup pane.

Keyboard: Up/Down (or j/k), PgUp/PgDn, Home/End, Enter reopens, Delete (or d)
forgets after a y to confirm, / filters, a toggles every workspace, Esc or q
closes. Mouse: click selects, double-click reopens, the wheel scrolls, and a
click on a row's × asks to forget it.

Colors come from the terminal (and so from the Herdr theme): reverse video
for the selection, bold titles, dim details. No palette of its own.
"""
import curses
import time

from . import config, core, herdr, store

BUTTON5_PRESSED = getattr(curses, "BUTTON5_PRESSED", 0x200000)  # wheel down
HELP = "Enter reopen · Del forget · / filter · a all workspaces · Esc close"
FORGET_COL = 3  # the × and its margin at the right edge of each row


def ago(t, now=None):
    seconds = max(0, (now or time.time()) - (t or 0))
    if seconds < 90:
        return "just now"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} hour{'s' if int(hours) != 1 else ''} ago"
    days = hours / 24
    if days < 2:
        return "yesterday"
    return f"{int(days)} days ago"


class Popup:
    def __init__(self, ctx):
        self.ctx = ctx
        self.session = herdr.session_name()
        self.workspace = ctx.get("workspace_label") or ""
        self.cfg = config.load()
        self.all = False
        self.filter = ""
        self.filtering = False
        self.confirm = None  # key of the entry waiting for "y" to forget
        self.message = ""
        self.sel = 0
        self.top = 0
        self.rows = []
        self.buttons = {}
        self.load()

    # ---------------------------------------------------------------- data

    def load(self):
        with store.locked():
            archive = store.load_archive()
            if core.prune(archive, self.cfg, time.time()):
                store.save_archive(archive)
        rows = core.listing(archive, self.session, None if self.all else self.workspace)
        if self.filter:
            needle = self.filter.lower()
            rows = [r for r in rows if needle in (r.get("title") or "").lower()
                    or needle in (r.get("workspace_label") or "").lower()]
        self.rows = rows
        self.sel = min(self.sel, max(0, len(rows) - 1))

    # ------------------------------------------------------------- drawing

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 5 or w < 30:
            scr.addnstr(0, 0, "Earmark: make this popup bigger", max(1, w - 1))
            scr.refresh()
            return
        head = " Earmark · " + ("every workspace" if self.all else (self.workspace or "this workspace"))
        count = f"{len(self.rows)} archived " if self.rows else ""
        scr.addnstr(0, 0, head, w - 1, curses.A_BOLD)
        if len(head) + len(count) < w - 1:
            scr.addnstr(0, w - 1 - len(count), count, len(count), curses.A_DIM)
        scr.hline(1, 0, curses.ACS_HLINE, w)
        scr.hline(h - 2, 0, curses.ACS_HLINE, w)

        body = h - 4
        if self.sel < self.top:
            self.top = self.sel
        if self.sel >= self.top + body:
            self.top = self.sel - body + 1
        if not self.rows:
            if self.filter:
                lines = [f"Nothing matches \"{self.filter}\"."]
            else:
                where = "any workspace" if self.all else (self.workspace or "this workspace")
                lines = [f"Nothing archived in {where} yet.",
                         "Close a tab running a coding agent and its session is kept here."]
            for i, line in enumerate(lines[:body]):
                scr.addnstr(2 + i, 2, line, w - 3, curses.A_DIM)
        now = time.time()
        for i, r in enumerate(self.rows[self.top:self.top + body]):
            n = self.top + i
            y = 2 + i
            selected = n == self.sel
            attr = curses.A_REVERSE if selected else curses.A_NORMAL
            detail = f"{r['agent']}  {ago(r.get('last_active'), now):>13}"
            if self.all:
                detail = f"{r.get('workspace_label') or '?'}  ·  " + detail
            title = r.get("title") or r.get("tab_label") or "(untitled session)"
            room = w - len(detail) - FORGET_COL - 4
            if room < 10:  # narrow: drop the detail
                detail, room = "", w - FORGET_COL - 3
            scr.addnstr(y, 0, " " * (w - 1), w - 1, attr)
            scr.addnstr(y, 1, ("› " if selected else "  ") + title[:room], room + 2, attr | curses.A_BOLD)
            if detail:
                scr.addnstr(y, w - FORGET_COL - len(detail) - 1, detail, len(detail), attr | curses.A_DIM)
            scr.addnstr(y, w - FORGET_COL, " ×", 2, attr)

        self.buttons = {}
        if self.confirm:
            text = " Forget this session?  "
            scr.addnstr(h - 1, 0, text, w - 1, curses.A_BOLD)
            x = len(text)
            for name, label in (("forget", "[ Forget ]"), ("keep", "[ Keep ]")):
                if x + len(label) < w:
                    scr.addnstr(h - 1, x, label, len(label), curses.A_REVERSE if name == "forget" else curses.A_BOLD)
                    self.buttons[name] = (x, x + len(label))
                x += len(label) + 2
            if x + 20 < w:
                scr.addnstr(h - 1, x, "(y / Esc)", w - 1 - x, curses.A_DIM)
            scr.refresh()
            return
        if self.filtering:
            foot = f" Filter: {self.filter}_   (Enter keeps it, Esc clears)"
        elif self.message:
            foot = " " + self.message
        else:
            foot = " " + HELP
        scr.addnstr(h - 1, 0, foot, w - 1, curses.A_BOLD if self.message else curses.A_DIM)
        scr.refresh()

    # ------------------------------------------------------------ actions

    def selected(self):
        return self.rows[self.sel] if 0 <= self.sel < len(self.rows) else None

    def do_reopen(self):
        r = self.selected()
        if not r:
            return False
        error = core.reopen(r, self.ctx, self.cfg)
        if error:
            self.message = error
            return False
        core.update_counts(self.session)
        return True  # close the popup; the new tab has focus

    def do_forget(self, key):
        core.forget(key)
        core.update_counts(self.session)
        self.message = "Forgotten."
        self.load()

    def row_at(self, y):
        n = self.top + (y - 2)
        return n if 2 <= y < 2 + len(self.rows) - self.top and 0 <= n < len(self.rows) else None

    def on_mouse(self, scr):
        try:
            _, x, y, _, b = curses.getmouse()
        except curses.error:
            return False
        h, w = scr.getmaxyx()
        clicked = b & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED)
        if self.confirm:
            # Only the footer's buttons act while asking; anything else keeps it.
            if clicked and y == h - 1:
                for name, (x0, x1) in self.buttons.items():
                    if x0 <= x < x1:
                        key, self.confirm = self.confirm, None
                        if name == "forget":
                            self.do_forget(key)
            return False
        if b & curses.BUTTON4_PRESSED:
            self.sel = max(0, self.sel - 1)
            return False
        if b & BUTTON5_PRESSED:
            self.sel = min(len(self.rows) - 1, self.sel + 1)
            return False
        n = self.row_at(y)
        if n is None:
            return False
        if b & curses.BUTTON1_DOUBLE_CLICKED:
            self.sel = n
            return self.do_reopen()
        if clicked:
            self.sel = n
            if x >= w - FORGET_COL - 1:
                self.confirm = self.rows[n]["key"]
        return False

    def on_key(self, key):
        """Returns True to close the popup."""
        if self.confirm:
            key_to_forget, self.confirm = self.confirm, None
            if key in ("y", "Y"):
                self.do_forget(key_to_forget)
            return False
        if self.filtering:
            if key in ("\n", "\r", curses.KEY_ENTER):
                self.filtering = False
            elif key == "\x1b":
                self.filtering, self.filter = False, ""
            elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                self.filter = self.filter[:-1]
            elif isinstance(key, str) and key.isprintable():
                self.filter += key
            self.load()
            return False
        self.message = ""
        if key in ("q", "\x1b"):
            if self.filter and key == "\x1b":
                self.filter = ""
                self.load()
                return False
            return True
        if key in (curses.KEY_UP, "k"):
            self.sel = max(0, self.sel - 1)
        elif key in (curses.KEY_DOWN, "j"):
            self.sel = min(len(self.rows) - 1, self.sel + 1)
        elif key == curses.KEY_PPAGE:
            self.sel = max(0, self.sel - 10)
        elif key == curses.KEY_NPAGE:
            self.sel = min(len(self.rows) - 1, self.sel + 10)
        elif key == curses.KEY_HOME:
            self.sel = 0
        elif key == curses.KEY_END:
            self.sel = len(self.rows) - 1
        elif key in ("\n", "\r", curses.KEY_ENTER):
            return self.do_reopen()
        elif key in (curses.KEY_DC, "d"):
            if self.selected():
                self.confirm = self.selected()["key"]
        elif key == "/":
            self.filtering = True
        elif key == "a":
            self.all = not self.all
            self.sel = self.top = 0
            self.load()
        self.sel = max(0, self.sel)
        return False

    # --------------------------------------------------------------- loop

    def run(self, scr):
        curses.set_escdelay(25)
        curses.curs_set(0)
        curses.use_default_colors()
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        while True:
            self.draw(scr)
            try:
                key = scr.get_wch()
            except KeyboardInterrupt:
                return
            if key == curses.KEY_RESIZE:
                continue
            if key == curses.KEY_MOUSE:
                if self.on_mouse(scr):
                    return
            elif self.on_key(key):
                return


def main(ctx):
    curses.wrapper(Popup(ctx).run)
