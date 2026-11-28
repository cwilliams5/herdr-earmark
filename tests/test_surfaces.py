"""Behaviour tests for the surfaces strict review 7's reviewers got one-line
breaks through: the archive popup driven by a script of keys and clicks,
the message popup's keys on a real pseudo-terminal, the command line into
the worker, a closed workspace's round trip, the inputs to the parking
rule, and what happens to a record on each path."""

import importlib.util
import json
import os
import pty
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, herdr, message, placeholder, procs, store, suspend, ui  # noqa: E402
from test_suspend import CFG, T0, pane, shell_info, snap, typed  # noqa: E402
from test_review1 import CFG_TIME, StateDir  # noqa: E402

FACTS = {"known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def record(**kw):
    rec = {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "workspace_label": "Work",
           "agent": "claude", "session_id": "s1", "state": "suspended", "at": T0 - 100, "cwd": "/proj",
           "resume": ["command", "claude", "--resume", "s1"], "base": {"screen": "shell", "at": 0}}
    rec.update(kw)
    return rec


# ------------------------------------------------------------- the popup

class Screen:
    """A curses window for Popup.run: draws nowhere, plays a script of keys.
    Each step is a key, or ("click", "keep"|"forget"|(x, y)) for a mouse
    click (on a footer button, worked out when it's played)."""

    def __init__(self, popup, script):
        self.popup, self.script, self.mouse = popup, list(script), None

    def getmaxyx(self):
        return (24, 80)

    def addstr(self, *a):
        pass

    def erase(self):
        pass

    def refresh(self):
        pass

    def noutrefresh(self):
        pass

    def get_wch(self):
        if not self.script:
            raise AssertionError("the popup didn't close when the script ended")
        step = self.script.pop(0)
        if isinstance(step, tuple) and step[0] == "click":
            where = step[1]
            if isinstance(where, str):
                x0, _ = self.popup.buttons[where]
                where = (x0 + 1, 23)
            self.mouse = (0, where[0], where[1], 0, ui.curses.BUTTON1_CLICKED)
            return ui.curses.KEY_MOUSE
        return step

    def __getattr__(self, name):  # anything else curses asks of a window
        return lambda *a, **k: None


class PopupScriptTests(StateDir):
    def setUp(self):
        super().setUp()
        entries = {f"claude:s{i}": {"herdr_session": "default", "workspace_label": "Work", "agent": "claude",
                                    "session_id": f"s{i}", "last_active": T0 - i, "closed_at": T0} for i in (1, 2)}
        store.save_archive({"entries": entries, "workspaces": {"default|w9|1": {
            "herdr_session": "default", "workspace_id": "w9", "label": "Old", "closed_at": time.time(),
            "tabs": [{"label": "t", "cwd": "/tmp"}]}}})
        f = mock.patch.object(agents, "session_facts", return_value=dict(FACTS))
        f.start()
        self.addCleanup(f.stop)
        self.mask = []
        for name, fn in (("set_escdelay", None), ("curs_set", None), ("use_default_colors", None),
                         ("mousemask", lambda m: self.mask.append(m) or (m, 0))):
            p = mock.patch.object(ui.curses, name, side_effect=fn or (lambda *a: None))
            p.start()
            self.addCleanup(p.stop)
        acs = mock.patch.object(ui.curses, "ACS_HLINE", ord("-"), create=True)  # set by a real initscr
        acs.start()
        self.addCleanup(acs.stop)

    def play(self, script, view="sessions"):
        popup = ui.Popup({"workspace_label": "Work"}, view)
        scr = Screen(popup, script)
        with mock.patch.object(ui.curses, "getmouse", side_effect=lambda: scr.mouse):
            popup.run(scr)
        return popup

    def test_q_closes_and_the_mouse_is_on(self):
        self.play(["q"])
        self.assertTrue(self.mask and self.mask[0] & ui.curses.BUTTON1_CLICKED)  # "fully usable with the mouse"

    def test_keep_keeps_and_forget_forgets(self):
        self.play(["d", ("click", "keep"), "q"])
        self.assertEqual(len(store.load_archive()["entries"]), 2)
        self.play(["d", ("click", "forget"), "q"])
        self.assertEqual(len(store.load_archive()["entries"]), 1)

    def test_backspace_in_the_filter(self):
        popup = self.play(["/", "s", "2", "\x7f", "\n", "q"])
        self.assertEqual(popup.filter, "s")

    def test_a_only_widens_the_sessions_view(self):
        popup = self.play(["a", "q"], view="workspaces")
        self.assertFalse(popup.all)
        popup = self.play(["a", "q"])
        self.assertTrue(popup.all)

    def test_names_keep_their_columns_before_a_detail(self):
        popup = ui.Popup({"workspace_label": "Work"})
        drawn = []
        scr = mock.Mock()
        scr.addstr.side_effect = lambda y, x, text, attr=0: drawn.append(text)
        long_detail, short_detail = "x" * 30, "short"
        popup.draw_row(scr, 2, 50, 0, False, "a name of twenty-four c", "", [long_detail, short_detail])
        self.assertNotIn(long_detail, " ".join(drawn))  # 50 columns: the long form would leave the name under 16
        self.assertIn(short_detail, " ".join(drawn))


# ------------------------------------------------------ the message popup

class MessageKeysTests(unittest.TestCase):
    """The question's answer read from a real pseudo-terminal."""

    def answer(self, data):
        import termios
        import tty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        tty.setraw(slave, termios.TCSANOW)  # as the popup does: the keys reach it as typed
        os.write(master, data)
        time.sleep(0.05)
        return message.read_answer(slave, 0.5)

    def test_only_y_then_enter_confirms(self):
        self.assertEqual(self.answer(b"y\r"), "y")
        self.assertEqual(self.answer(b"y\x7fy\r"), "y")  # Backspace takes the y back, and it's typed again
        self.assertEqual(self.answer(b"y\x7f\r"), "")  # taken back: Enter alone keeps it running
        self.assertEqual(self.answer(b"y\x1b\r"), "")  # Esc cancels, whatever came before
        self.assertEqual(self.answer(b"y\x03\r"), "")  # so does Ctrl+C
        self.assertEqual(self.answer(b"my yard\r"), "")  # a word typed elsewhere

    def test_any_other_key_closes_at_once(self):  # review 8 R162
        start = time.time()
        self.assertEqual(self.answer(b"n"), "")
        self.assertLess(time.time() - start, 0.3)  # not the whole wait
        typed = []
        import termios
        import tty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        tty.setraw(slave, termios.TCSANOW)
        os.write(master, b"y")
        message.read_answer(slave, 0.2, echo=typed.append)
        self.assertEqual(typed, ["y"])  # a typed y is shown

    def test_a_message_goes_by_itself_soon(self):
        self.assertLessEqual(message.SHOW_WAIT, 15)
        self.assertLessEqual(message.ASK_WAIT, 120)


# ---------------------------------------------------- the command line

def earmark_main():
    spec = importlib.util.spec_from_file_location("earmark_cli", os.path.join(ROOT, "earmark.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CommandLineTests(StateDir):
    def worker_call(self, *args):
        cli = earmark_main()
        with mock.patch.object(sys, "argv", ["earmark.py", "worker", *args]), \
                mock.patch.object(suspend, "worker") as worker:
            cli.cmd_worker()
        return worker.call_args

    def test_worker_options_reach_the_worker(self):
        call = self.worker_call("--rearm-pass", "--session", "s2")
        self.assertEqual(call.args[0], "s2")
        self.assertTrue(call.kwargs["rearm_pass_only"])
        self.assertFalse(call.kwargs["rearm"])
        call = self.worker_call("--pane", "w1:p4", "--pressed", "123.5", "--accept", "a doubt")
        self.assertEqual((call.kwargs["pane_id"], call.kwargs["pressed"], call.kwargs["accept"]),
                         ("w1:p4", 123.5, "a doubt"))
        self.assertFalse(call.kwargs["rearm_pass_only"])
        self.assertTrue(self.worker_call("--rearm").kwargs["rearm"])


# --------------------------------------------- notes, layouts, round trip

class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.index, self.archive = {"sessions": {}}, {"entries": {}}
        f = mock.patch.object(agents, "session_facts", return_value=dict(FACTS))
        f.start()
        self.addCleanup(f.stop)

    def apply(self, panes, t, workspaces=None, event="pane.focused"):
        return core.apply(self.index, self.archive, "default", snap(panes, workspaces), event, {}, t)

    def test_the_pane_name_reaches_the_archive(self):
        self.apply([dict(pane("w1:p1"), label="reviewer")], T0)
        self.apply([], T0 + 5, event="tab.closed")
        self.assertEqual(self.archive["entries"]["claude:s1"]["pane_label"], "reviewer")

    def test_a_workspace_missing_from_one_snapshot_keeps_its_name(self):
        self.apply([pane("w1:p1")], T0, workspaces={"w1": "Work"})
        s = snap([pane("w1:p1")], {"w1": "Work"})
        del s["workspaces"]["w1"]  # a snapshot taken mid-change
        core.apply(self.index, self.archive, "default", s, "pane.focused", {}, T0 + 5)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["workspace_label"], "Work")

    def test_a_suspended_tabs_options_survive_a_closed_workspace(self):
        rec = record(resume=["command", "claude", "--resume", "s1", "--permission-mode", "plan"])
        layouts = core.tab_layouts(snap([pane("w1:p1", session=None)]), {}, {"w1:p1": rec})
        self.assertEqual(layouts["w1"]["tabs"][0]["resume"], rec["resume"])

    def test_prune_brings_titles_up_to_date(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s1.jsonl")
            open(path, "w").close()
            archive = {"entries": {"claude:s1": {"herdr_session": "default", "agent": "claude", "session_id": "s1",
                                                 "title": "Old", "last_active": T0, "closed_at": T0}}}
            with mock.patch.object(agents, "session_facts", return_value=dict(FACTS, title="New", source=path)):
                core.prune(archive, dict(config.DEFAULTS), T0)
        self.assertEqual(archive["entries"]["claude:s1"]["title"], "New")

    def test_marks_wait_out_a_restart(self):
        self.apply([pane("w1:p1", session=None, tab="w1:t1")], T0)
        s = self.index["sessions"]["default"]
        s["marked"] = {"w1:t1": "💤"}
        # Herdr restarted and hasn't brought the tab back yet: the mark stays.
        core.apply(self.index, self.archive, "default", snap([]), "startup", {}, T0 + 100)
        self.assertIn("w1:t1", s["marked"])

    def test_counts_forget_gone_workspaces(self):
        self.index["sessions"]["default"] = {"boot": 5}
        cache = {"sessions": {"default": {"boot": 5, "spaces": {"w1": {}, "w9": {"earmark_archived": "2"}}}}}
        core.pending_reports(self.index, self.archive, "default", snap([], {"w1": "Work"}), None, cache)
        self.assertNotIn("w9", cache["sessions"]["default"]["spaces"])


# ------------------------------------------------ the parking rule's inputs

class RuleInputTests(StateDir):
    def look(self, p, info, table, facts=None):
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "environ", return_value={}), \
                mock.patch.object(procs, "start_token", return_value="tok"), \
                mock.patch.object(agents, "session_facts", return_value=dict(facts or FACTS)):
            return suspend.look(p, {}, procs.Table(table), T0, {})

    def test_other_agents_count_their_own_activity(self):
        info = {"shell_pid": 10, "foreground_process_group_id": 50, "foreground_processes": [
            {"pid": 50, "name": "codex", "argv": ["codex", "--no-daemon"], "cmdline": "codex --no-daemon"}]}
        found = self.look(pane("w1:p1", agent="codex"), info, {10: (1, "bash", "bash"), 50: (10, "codex", "codex")},
                          facts=dict(FACTS, last_active=T0 - 60))
        self.assertGreaterEqual(found["activity"], T0 - 60)

    def test_a_folder_the_shell_cant_be_given_is_seen(self):
        info = {"shell_pid": 10, "foreground_process_group_id": 50, "foreground_processes": [
            {"pid": 50, "name": "claude", "argv": ["claude"], "cmdline": "claude"}]}
        p = dict(pane("w1:p1"), cwd="/tmp/it's here", foreground_cwd="/tmp/it's here")
        found = self.look(p, info, {10: (1, "bash", "bash"), 50: (10, "claude", "claude")})
        self.assertTrue(found["cwd_unsafe"])

    def test_bad_resume_entries_are_dropped(self):
        self.settings('[resume]\nfoo = "foo --resume {id}"\nbar = ["bar", "--resume", "{id}"]\n')
        cfg = config.load()
        self.assertNotIn("foo", cfg["resume"])
        self.assertIn("bar", cfg["resume"])

    def test_only_claude_gets_its_folder_on_the_line(self):
        self.assertEqual(agents.env_prefix("codex", "/home/a/.codex-work"), "")
        self.assertTrue(agents.env_prefix("claude", "/home/a/.claude-alt"))

    def test_a_session_name_the_shell_cant_take(self):
        self.assertTrue(suspend.line_safe("default", "w1:p1"))
        self.assertFalse(suspend.line_safe("it's", "w1:p1"))

    def test_a_claude_owned_by_someone_else_is_still_running(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sessions"))
            with open(os.path.join(d, "sessions", "4242.json"), "w") as f:
                json.dump({"pid": 4242, "sessionId": "s1", "startedAt": T0 * 1000}, f)
            with mock.patch.object(agents.os, "kill", side_effect=PermissionError), \
                    mock.patch.object(procs, "started_at", return_value=T0):
                self.assertTrue(agents.claude_running("s1", d))

    def test_the_claude_folder_is_looked_up_for_claude_only(self):
        with mock.patch.object(herdr, "process_info") as info:
            core.note_config_dirs(snap([pane("w1:p1", agent="codex")]), {})
        info.assert_not_called()

    def test_herdrs_config_follows_xdg(self):
        env = {k: v for k, v in os.environ.items() if k != "HERDR_CONFIG_PATH"}
        env["XDG_CONFIG_HOME"] = "/x"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(herdr.config_path(), "/x/herdr/config.toml")


class ProcessTableTests(unittest.TestCase):
    def test_a_parent_is_the_parent_not_the_process_group(self):
        import subprocess
        # Its own session: its process group is itself, never our pid, so a
        # parse that took the group for the parent can't pass by chance.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"], start_new_session=True)
        try:
            table = procs.Table()
            self.assertEqual(table.procs[child.pid][0], os.getpid())
            self.assertEqual(table.ppid(child.pid), os.getpid())
        finally:
            child.kill()
            child.wait()


class PlaceholderTextTests(unittest.TestCase):
    def test_tabs_take_their_columns(self):
        self.assertEqual(placeholder.crop("a\tb", 20).replace(placeholder.RESET, ""), "a    b")


# ------------------------------------------------------ records, each path

class RecordPathTests(StateDir):
    def test_the_key_files_a_session_another_one_replaced(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session="s9")), \
                mock.patch.object(herdr, "process_info", return_value={"shell_pid": 1, "foreground_process_group_id": 5,
                                                                       "foreground_processes": [{"pid": 5, "name": "claude"}]}), \
                mock.patch.object(agents, "claude_registry", return_value={"session_id": "s9"}), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            suspend.manual("default", "w1:p1", CFG)
        self.assertIn("claude:s1", store.load_archive()["entries"])

    def test_a_hangup_keeps_the_record(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})

        class NoTerminal:
            def __init__(self, fd):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass
        with mock.patch.object(placeholder, "Terminal", NoTerminal), \
                mock.patch.object(placeholder, "wait_for_key", return_value="hangup"), \
                mock.patch.object(placeholder, "unmark"), \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(placeholder.agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(sys, "stdout"):
            self.assertEqual(placeholder.main("default", "w1:p1"), 1)
        self.assertIn("w1:p1", store.load_index()["sessions"]["default"]["suspended"])  # back after the restart
        self.assertEqual(store.load_archive().get("entries", {}), {})

    def arm(self, rec, **kw):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": rec}}}})
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None, tab="w1:t1")), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None, tab="w1:t1")])), \
                mock.patch.object(herdr, "run") as run:
            suspend.arm("default", "w1:p1", **kw)
        return typed(run)

    def test_the_key_ignores_the_wait_after_a_failed_start(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record(
            arm_failed=time.time())}}}})
        bare = pane("w1:p1", session=None, tab="w1:t1")
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", return_value=snap([bare])), \
                mock.patch.object(suspend, "say"), \
                mock.patch.object(herdr, "run") as run:
            suspend.manual("default", "w1:p1", CFG)
        self.assertTrue(typed(run))  # README: "the key always tries"

    def test_a_restart_types_once(self):
        self.assertFalse(self.arm(record(armed_by_rearm=True), restart=True))

    def test_a_resume_that_failed_gets_its_placeholder_back(self):
        self.assertTrue(self.arm(record(state="waking", waking_at=T0 - 3600)))

    def test_the_last_look_hears_remote_control(self):
        from test_suspend import SuspendPaneTests

        class Flow(SuspendPaneTests):
            def runTest(self):
                pass
        flow = Flow()
        flow.setUp()
        try:
            with mock.patch.object(agents, "claude_registry", return_value={"status": "idle", "remote": True}), \
                    mock.patch.object(suspend.time, "time", return_value=T0):
                why = suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3600)
            self.assertIn("busy", why)
            self.assertFalse([e for e in flow.events if e[0] == "kill"])
        finally:
            flow.doCleanups()

    def test_a_partial_snapshot_after_a_restart_archives_nothing(self):
        index = {"sessions": {"default": {"panes": {f"w1:p{i}": {"session_id": f"s{i}", "agent": "claude"}
                                                   for i in (1, 2, 3)},
                                          "suspended": {"w1:p1": record()}}}}
        partial = snap([pane("w1:p1", session=None, tab="w1:t1")])
        partial["partial"] = True
        with mock.patch.object(core, "partial_snapshot", return_value=True), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, {"entries": {}}, "default", partial, "startup", {}, T0, server_pid=99)
        self.assertIn("w1:p1", index["sessions"]["default"]["suspended"])

    def test_memory_mode_stops_once_memory_is_back(self):
        chosen = [(pane(f"w1:p{i}", session=f"s{i}"), {}, {"activity": T0 - 7200, "agent": "claude"}) for i in (1, 2, 3)]
        memory = iter([10.0, 40.0, 40.0, 40.0])
        cfg = dict(CFG_TIME, suspend=dict(CFG_TIME["suspend"], when="memory", memory_below=20))
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(suspend, "choose", return_value=chosen), \
                mock.patch.object(procs, "available_percent", side_effect=lambda: next(memory)), \
                mock.patch.object(suspend, "suspend_pane", return_value="") as act, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", cfg)
        self.assertEqual(act.call_count, 1)

    def test_saves_replace_the_file_whole(self):
        with mock.patch.object(store.os, "replace", wraps=os.replace) as replace:
            store.save_index({"sessions": {}})
        replace.assert_called_once()
        self.assertEqual(store.load_index(), {"sessions": {}})


if __name__ == "__main__":
    unittest.main()
