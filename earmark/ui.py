"""The archive popup: a terminal UI in a Herdr popup pane.

Two views, switched with Tab or by clicking their names at the top:

- Sessions: this workspace's archived sessions (a: every workspace's).
  Enter reopens one in a new tab.
- Workspaces: closed workspaces, newest first. Enter restores one: its tabs
  come back in order with their names, agent tabs resuming their sessions.

Keyboard: Up/Down (or j/k), PgUp/PgDn, Home/End, Enter, Delete (or d)
forgets after a confirm, / filters, Esc or q closes. Mouse: click selects,
double-click opens, the wheel scrolls, and a click on a row's × asks to
forget it, with clickable Forget and Keep buttons.

Colors come from the terminal (and so from the Herdr theme): reverse video
for the selection and the current view, bold names, dim details.
"""
import curses
import time

from . import config, core, herdr, store

BUTTON5_PRESSED = getattr(curses, "BUTTON5_PRESSED", 0x200000)  # wheel down
FORGET_COL = 3  # the × and its margin at the right edge of each row
VIEWS = (("sessions", "Sessions"), ("workspaces", "Workspaces"))
HELP = {
    "sessions": "Enter reopen · Del forget · / filter · a all workspaces · Tab workspaces · Esc close",
    "workspaces": "Enter restore · Del forget · / filter · Tab sessions · Esc close",
}


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


def tab_count(record):
    n = len(record.get("tabs") or [])
    agents_n = sum(1 for tb in record.get("tabs") or [] if tb.get("session_id"))
    text = f"{n} tab{'s' if n != 1 else ''}"
    return text + (f", {agents_n} with agents" if agents_n else "")


class Popup:
    def __init__(self, ctx, view="sessions"):
        self.ctx = ctx
        self.session = herdr.session_name()
        self.workspace = ctx.get("workspace_label") or ""
        self.cfg = config.load()
        self.view = view if view in dict(VIEWS) else "sessions"
        self.all = False
        self.filter = ""
        self.filtering = False
        self.confirm = None  # key of the row waiting for a confirm to forget
        self.message = ""
        self.sel = 0
        self.top = 0
        self.rows = []
        self.buttons = {}  # footer buttons while confirming: name -> (x0, x1)
        self.view_tabs = {}  # header view names: view -> (x0, x1)
        self.load()

    # ---------------------------------------------------------------- data

    def load(self):
        with store.locked():
            archive = store.load_archive()
            if core.prune(archive, self.cfg, time.time()):
                store.save_archive(archive)
        needle = self.filter.lower()
        if self.view == "workspaces":
            rows = core.closed_workspaces(archive, self.session)
            if needle:
                rows = [r for r in rows if needle in r["label"].lower()
                        or any(needle in (tb.get("label") or "").lower() for tb in r.get("tabs") or [])]
        else:
            rows = core.listing(archive, self.session, None if self.all else self.workspace)
            if needle:
                rows = [r for r in rows if any(needle in (text or "").lower() for text in
                        (r.get("title"), core.custom_name(r), r.get("workspace_label")))]
        self.rows = rows
        self.sel = min(self.sel, max(0, len(rows) - 1))

    def switch(self, view):
        if view != self.view:
            self.view, self.sel, self.top, self.filter, self.message = view, 0, 0, "", ""
            self.load()

    # ------------------------------------------------------------- drawing

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 5 or w < 40:
            scr.addnstr(0, 0, "Earmark: make this popup bigger", max(1, w - 1))
            scr.refresh()
            return
        self.draw_header(scr, w)
        scr.hline(1, 0, curses.ACS_HLINE, w)
        scr.hline(h - 2, 0, curses.ACS_HLINE, w)

        body = h - 4
        if self.sel < self.top:
            self.top = self.sel
        if self.sel >= self.top + body:
            self.top = self.sel - body + 1
        if not self.rows:
            for i, line in enumerate(self.empty_lines()[:body]):
                scr.addnstr(2 + i, 2, line, w - 3, curses.A_DIM)
        now = time.time()
        for i, r in enumerate(self.rows[self.top:self.top + body]):
            n = self.top + i
            selected = n == self.sel
            attr = curses.A_REVERSE if selected else curses.A_NORMAL
            if self.view == "workspaces":
                primary = r["label"] or "(unnamed workspace)"
                secondary = ""
                detail = f"{tab_count(r)}  ·  closed {ago(r.get('closed_at'), now)}"
            else:
                primary, secondary = core.names(r, self.cfg["title_first"])
                detail = f"{r['agent']}  {ago(r.get('last_active'), now):>13}"
                if self.all:
                    detail = f"{r.get('workspace_label') or '?'}  ·  " + detail
            self.draw_row(scr, 2 + i, w, attr, selected, primary, secondary, detail)
        self.draw_footer(scr, h, w)
        scr.refresh()

    def draw_header(self, scr, w):
        scr.addnstr(0, 0, " Earmark ", w - 1, curses.A_BOLD)
        x = 10
        self.view_tabs = {}
        for view, name in VIEWS:
            label = f" {name} "
            if x + len(label) >= w:
                break
            scr.addnstr(0, x, label, len(label), curses.A_REVERSE if view == self.view else curses.A_DIM)
            self.view_tabs[view] = (x, x + len(label))
            x += len(label) + 1
        if self.view == "workspaces":
            right = f"{len(self.rows)} closed " if self.rows else ""
        else:
            where = "every workspace" if self.all else (self.workspace or "this workspace")
            right = f"{where}{f' · {len(self.rows)} archived' if self.rows else ''} "
        if x + len(right) + 2 < w:
            scr.addnstr(0, w - 1 - len(right), right, len(right), curses.A_DIM)

    def draw_row(self, scr, y, w, attr, selected, primary, secondary, detail):
        room = w - len(detail) - FORGET_COL - 4
        if room < 10:  # narrow: drop the detail
            detail, room = "", w - FORGET_COL - 3
        scr.addnstr(y, 0, " " * (w - 1), w - 1, attr)
        scr.addnstr(y, 1, ("› " if selected else "  ") + primary[:room], room + 2, attr | curses.A_BOLD)
        rest = room - len(primary) - 2  # the other name, dimmed, in whatever room is left
        if secondary and rest > 3:
            scr.addnstr(y, 3 + len(primary) + 2, secondary[:rest], rest, attr | curses.A_DIM)
        if detail:
            scr.addnstr(y, w - FORGET_COL - len(detail) - 1, detail, len(detail), attr | curses.A_DIM)
        scr.addnstr(y, w - FORGET_COL, " ×", 2, attr)

    def empty_lines(self):
        if self.filter:
            return [f"Nothing matches \"{self.filter}\"."]
        if self.view == "workspaces":
            return ["No closed workspaces yet.",
                    "Close a workspace and it waits here, to come back with all its tabs."]
        where = "any workspace" if self.all else (self.workspace or "this workspace")
        return [f"Nothing archived in {where} yet.",
                "Close a tab running a coding agent and its session is kept here."]

    def draw_footer(self, scr, h, w):
        self.buttons = {}
        if self.confirm:
            text = (" Forget this closed workspace? Its sessions stay archived.  " if self.view == "workspaces"
                    else " Forget this session?  ")
            scr.addnstr(h - 1, 0, text, w - 1, curses.A_BOLD)
            x = len(text)
            for name, label in (("forget", "[ Forget ]"), ("keep", "[ Keep ]")):
                if x + len(label) < w:
                    scr.addnstr(h - 1, x, label, len(label), curses.A_REVERSE if name == "forget" else curses.A_BOLD)
                    self.buttons[name] = (x, x + len(label))
                x += len(label) + 2
            if x + 12 < w:
                scr.addnstr(h - 1, x, "(y / Esc)", w - 1 - x, curses.A_DIM)
            return
        if self.filtering:
            foot = f" Filter: {self.filter}_   (Enter keeps it, Esc clears)"
        elif self.message:
            foot = " " + self.message
        else:
            foot = " " + HELP[self.view]
        scr.addnstr(h - 1, 0, foot, w - 1, curses.A_BOLD if self.message else curses.A_DIM)

    # ------------------------------------------------------------ actions

    def selected(self):
        return self.rows[self.sel] if 0 <= self.sel < len(self.rows) else None

    def do_open(self):
        """Reopen the session or restore the workspace; True closes the popup."""
        r = self.selected()
        if not r:
            return False
        if self.view == "workspaces":
            self.message = f"Restoring {r['label'] or 'the workspace'}..."
            error = core.restore_workspace(r, self.cfg)
        else:
            error = core.reopen(r, self.ctx, self.cfg)
        if error:
            self.message = error
            return False
        core.update_counts(self.session)
        return True  # the restored tabs have focus

    def do_forget(self, key):
        if self.view == "workspaces":
            core.forget_workspace(key)
        else:
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
        if clicked and y == 0:
            for view, (x0, x1) in self.view_tabs.items():
                if x0 <= x < x1:
                    self.switch(view)
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
            return self.do_open()
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
        if key in ("\t", curses.KEY_BTAB):
            self.switch("workspaces" if self.view == "sessions" else "sessions")
        elif key in (curses.KEY_UP, "k"):
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
            return self.do_open()
        elif key in (curses.KEY_DC, "d"):
            if self.selected():
                self.confirm = self.selected()["key"]
        elif key == "/":
            self.filtering = True
        elif key == "a" and self.view == "sessions":
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


def main(ctx, view="sessions"):
    curses.wrapper(Popup(ctx, view).run)
