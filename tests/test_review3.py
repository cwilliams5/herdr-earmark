"""Tests for strict review 3 (docs/PLAN.md R53-R68): one per finding, and
one per mutation the reviewers' own runs showed surviving. Run:
python3 -m unittest discover tests

Made-up snapshots, process tables, transcripts and terminals; nothing
touches a running Herdr or a real process."""
import io
import json
import os
import pty
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, herdr, message, placeholder, procs, store, suspend, ui  # noqa: E402
from test_suspend import CFG, T0, SuspendPaneTests, found, pane, shell_info, snap, typed  # noqa: E402
from test_review1 import CFG_TIME, StateDir  # noqa: E402

FACTS = {"known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}
MANUAL = dict(CFG, suspend=dict(CFG["suspend"], when="manual"))


def suspended_rec(**kw):
    rec = {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "workspace_label": "Work",
           "agent": "claude", "session_id": "s1", "state": "suspended", "at": T0 - 100, "cwd": "/proj",
           "resume": ["command", "claude", "--resume", "s1"],
           "base": {"screen": "shell", "at": 0}}  # its shell seen back a while ago, unchanged since
    rec.update(kw)
    return rec


# ------------------------------------------------------------------ R53

class RestartRaceTests(StateDir):
    """R27 again, through the real hook sequence: Herdr listed the stopped
    session in its pane before the restart, so its restore may relaunch it;
    nothing may type a placeholder into that pane during the boot grace."""

    def setUp(self):
        super().setUp()
        self.boot = time.time()
        index, archive = {"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}}, \
            {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            # Before the restart: Herdr lists s1 in the pane where the placeholder runs.
            core.apply(index, archive, "default", snap([pane("w1:p1")]), "pane.focused", {}, self.boot - 50)
            self.assertTrue(index["sessions"]["default"]["suspended"]["w1:p1"].get("herdr_listed"))
            # The restart: the restored pane shows no agent while Herdr's resume waits.
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "startup", {}, self.boot)
        self.assertNotIn("w1:p1", index["sessions"]["default"]["panes"])  # the note is gone...
        self.assertTrue(index["sessions"]["default"]["suspended"]["w1:p1"]["herdr_listed"])  # ...the record says it
        store.save_index(index)

    def run_with(self, fn, step=None, at=None):
        """Run fn with Herdr faked (a bare shell in the suspended pane) and,
        optionally, a clock: fixed (`at`) or advancing `step` seconds per
        reading from the boot. Returns (typing calls, clock at the first)."""
        bare = pane("w1:p1", session=None)
        state = {"now": self.boot, "first": None}

        def clock():
            if at is not None:
                return at
            state["now"] += step
            return state["now"]

        def run(*args, **kw):
            if args[:2] in (("pane", "send-keys"), ("pane", "run")) and state["first"] is None:
                state["first"] = state["now"] if at is None else at
            return {}
        recorder = mock.MagicMock(side_effect=run)
        patches = [mock.patch.object(herdr, "process_info", return_value=shell_info()),
                   mock.patch.object(herdr, "pane", return_value=bare),
                   mock.patch.object(herdr, "snapshot", return_value=snap([bare])),
                   mock.patch.object(herdr, "run", recorder)]
        if step is not None or at is not None:
            patches.append(mock.patch.object(suspend.time, "time", side_effect=clock))
        for p in patches:
            p.start()
        try:
            fn()
        finally:
            for p in reversed(patches):
                p.stop()
        return typed(recorder), state["first"]

    def test_no_path_types_during_the_grace(self):
        self.assertEqual(self.run_with(lambda: suspend.arm("default", "w1:p1", restart=True))[0], [])
        with mock.patch.object(suspend.message, "show") as show:
            self.assertEqual(self.run_with(lambda: suspend.manual("default", "w1:p1", MANUAL))[0], [])  # the key
        show.assert_called_once()
        self.assertEqual(self.run_with(
            lambda: suspend.rearm_pass("default", snap([pane("w1:p1", session=None)])))[0], [])

    def test_rearm_all_waits_out_the_grace_then_types(self):
        got, first = self.run_with(lambda: suspend.rearm_all("default"), step=2)
        self.assertTrue(got)  # it keeps trying past the grace...
        self.assertGreaterEqual(first, self.boot + core.BOOT_GRACE)  # ...and types only after it

    def test_after_the_grace_the_placeholder_comes_back(self):
        t = self.boot + core.BOOT_GRACE + 1
        # First sight of the new server's shell: watched from now...
        self.assertEqual(self.run_with(lambda: suspend.arm("default", "w1:p1", restart=True), at=t)[0], [])
        # ...and unchanged a moment later: the placeholder.
        got, _ = self.run_with(lambda: suspend.arm("default", "w1:p1", restart=True), at=t + suspend.STABLE)
        self.assertTrue(got)

    def test_the_mark_clears_once_herdr_shows_the_pane_without_it_after_the_grace(self):
        index, archive = store.load_index(), {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.focused", {},
                       self.boot + 10)
            self.assertTrue(index["sessions"]["default"]["suspended"]["w1:p1"].get("herdr_listed"))  # still booting
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.focused", {},
                       self.boot + core.BOOT_GRACE + 5)
        self.assertNotIn("herdr_listed", index["sessions"]["default"]["suspended"]["w1:p1"])


# ------------------------------------------------------------------ R54

class BrokenConfigTests(StateDir):
    def old_archive(self):
        old = T0 - 90 * 86400
        store.save_archive({"entries": {"pi:x": {"herdr_session": "default", "workspace_label": "Work", "agent": "pi",
                                                 "session_id": "x", "last_active": old, "closed_at": old}},
                            "workspaces": {"k": {"key": "k", "herdr_session": "default", "label": "Gone",
                                                 "closed_at": old, "tabs": []}}})

    def test_the_popup_never_prunes_with_a_broken_config(self):
        self.settings("keep_days = 0\n[suspend\n")
        self.old_archive()
        before = store.load_archive()
        ui.Popup({"workspace_label": "Work"})
        self.assertEqual(store.load_archive(), before)

    def test_every_key_and_value_is_checked(self):
        for text in ('keep_days = "0"\n', "keep_days = -1\n", "keep_day = 0\n", "report_count = 1\n",
                     'title_first = "name"\n', '[resume]\nclaude = "claude --resume {id}"\n', 'suspend = "on"\n'):
            self.settings(text)
            self.assertTrue(config.load().get("_broken"), text)
            self.assertTrue(config.check(), text)
        self.settings('keep_days = 0\nreport_count = false\n[resume]\nclaude = ["claude", "-r", "{id}"]\n')
        self.assertNotIn("_broken", config.load())

    def test_unreadable_and_dangling_files_are_problems_and_missing_isnt(self):
        path = os.path.join(self.dir.name, "config", "config.toml")
        self.assertNotIn("_broken", config.load())  # no file: defaults, fine
        os.symlink(os.path.join(self.dir.name, "nowhere.toml"), path)
        self.assertTrue(config.load().get("_broken"))
        os.unlink(path)
        self.settings("keep_days = 0\n")
        with mock.patch("builtins.open", side_effect=PermissionError(13, "Permission denied")):
            self.assertIn("can't read", config.load()["_broken"])


# ------------------------------------------------------------------ R55

class ArmFocusTests(StateDir):
    def test_focus_moving_to_the_tab_during_the_claim_stops_it(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        bare = pane("w1:p1", session=None, tab="w1:t1")
        views = [snap([bare, pane("w1:p9", session=None, tab="w1:t9", focused=True)]),
                 snap([bare, pane("w1:p8", session=None, tab="w1:t1", focused=True)])]  # a split of its tab
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", side_effect=lambda: views.pop(0) if len(views) > 1 else views[0]), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertEqual(typed(run), [])
        self.assertEqual(suspend.record("default", "w1:p1")["arming"], 0)

    def test_a_split_of_its_tab_in_view_counts(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        bare = pane("w1:p1", session=None, tab="w1:t1")
        view = snap([bare, pane("w1:p8", session=None, tab="w1:t1", focused=True)])
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", return_value=view), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertEqual(typed(run), [])

    def test_only_a_known_shell_is_typed_into(self):  # R61: a program exec'd in the shell's place
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        bare = pane("w1:p1", session=None, tab="w1:t1")
        info = {"shell_pid": 1, "foreground_process_group_id": 1,
                "foreground_processes": [{"pid": 1, "name": "codex", "argv": ["codex"]}]}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", return_value=snap([bare])), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertEqual(typed(run), [])
        self.assertTrue(suspend.bare_shell(shell_info()))
        self.assertTrue(suspend.bare_shell(dict(shell_info(), foreground_processes=[{"pid": 1, "name": "-zsh"}])))


# ------------------------------------------------------------- R56, R64

class WorkerAcceptTests(StateDir):
    def test_the_worker_suspends_with_the_doubt_and_reports_only_a_refusal(self):  # review 4 R74
        with mock.patch.object(suspend, "confirm", return_value="") as confirm, \
                mock.patch.object(suspend, "say") as say:
            suspend.worker("default", MANUAL, pane_id="w1:p1", accept="the doubt")
        confirm.assert_called_once_with("default", "w1:p1", "the doubt")
        say.assert_not_called()
        with mock.patch.object(suspend, "confirm", return_value="it got busy"), \
                mock.patch.object(suspend, "say") as say, mock.patch.object(suspend, "manual") as manual:
            suspend.worker("default", MANUAL, pane_id="w1:p1", accept="the doubt")
        self.assertIn("It got busy", say.call_args.args[2])
        manual.assert_not_called()


class ResumeModeTests(SuspendPaneTests):
    def test_the_suspend_uses_the_mode_from_the_whole_read(self):  # R70
        base = self.fake_look

        def look(*a):
            return dict(base(*a), mode="plan", facts=dict(FACTS, source="/nowhere.jsonl"))
        with mock.patch.object(suspend, "look", side_effect=look), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True), "")
        self.assertEqual(suspend.record("default", "w1:p1")["resume"][-2:], ["--permission-mode", "plan"])


class KeyDoubtTests(SuspendPaneTests):
    def kills(self):
        return [e for e in self.events if e[0] == "kill"]

    def test_unknown_status_asks(self):
        p = pane("w1:p1", status="unknown")
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([p])), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertTrue(why.startswith(suspend.CONFIRM) and "unknown" in why, why)
        self.assertEqual(self.kills(), [])

    def test_an_unreadable_claude_folder_asks(self):
        base = self.fake_look

        def look(*a):
            return dict(base(*a), facts={"known": False, "exists": True, "has_content": True})
        with mock.patch.object(suspend, "look", side_effect=look), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertTrue(why.startswith(suspend.CONFIRM) and "Claude folder" in why, why)
        self.assertEqual(self.kills(), [])

    def test_two_presses_never_confirm(self):  # H1: Herdr's notifications are off by default
        self.screen = "some output\n$ "
        with mock.patch.object(suspend.message, "show") as show, \
                mock.patch.object(suspend.time, "time", return_value=T0):
            suspend.manual("default", "w1:p1", MANUAL)
            suspend.manual("default", "w1:p1", MANUAL)
        self.assertEqual(self.kills(), [])
        self.assertEqual(show.call_count, 2)
        self.assertTrue(all(c.kwargs.get("ask") for c in show.call_args_list))

    def test_the_key_with_suspending_off_does_nothing(self):
        off = dict(CFG, suspend=dict(CFG["suspend"], when="off"))
        with mock.patch.object(suspend.message, "show") as show, \
                mock.patch.object(suspend.time, "time", return_value=T0):
            suspend.manual("default", "w1:p1", off)
        self.assertEqual(self.kills(), [])
        self.assertIn("off", show.call_args.args[0])

    def test_blocked_at_the_last_look_stops_the_key(self):  # fit M2: R44 "blocked"
        # The snapshot (the first look) says idle; Herdr's pane, read right
        # before the signal, says a question just opened.
        with mock.patch.object(suspend.herdr, "pane", return_value=pane("w1:p1", status="blocked")), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("busy", why)
        self.assertEqual(self.kills(), [])

    def test_a_record_a_hook_changed_gets_no_signal(self):  # fit M2: R42's state comparison
        def pane_and_change_it(pane_id):
            index = store.load_index()
            rec = index["sessions"]["default"].get("suspended", {}).get("w1:p1")
            if rec:
                rec["state"] = "suspended"
                store.save_index(index)
            return self.fake_pane(pane_id)
        with mock.patch.object(suspend.herdr, "pane", side_effect=pane_and_change_it), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("record changed", why)
        self.assertEqual(self.kills(), [])

    def test_the_screen_copy_is_private(self):  # safety survivor
        with mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True), "")
        path = suspend.record("default", "w1:p1")["screen"]
        self.assertEqual(os.stat(path).st_mode & 0o077, 0)
        self.assertEqual(os.stat(os.path.dirname(path)).st_mode & 0o077, 0)

    def test_the_launchers_start_time_is_checked_too(self):  # safety survivor
        base = self.fake_look

        def look(*a):
            return dict(base(*a), chain=[50, 40], tokens={50: "L", 40: "W"})
        tokens = {50: "L", 40: "changed"}
        with mock.patch.object(suspend, "look", side_effect=look), \
                mock.patch.object(suspend.procs, "start_token", side_effect=lambda pid: tokens.get(pid)), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("process changed", why)
        self.assertEqual(self.kills(), [])


class MessagePopupTests(unittest.TestCase):
    def run_popup(self, payload, keys, spawned=True, confirm_result="", early=b""):
        import termios
        import tty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        # Raw before the keys arrive, as in Herdr's popup (written to a cooked
        # tty, Enter would arrive as "\n", not the "\r" Herdr sends).
        tty.setraw(slave, termios.TCSANOW)
        if early:
            os.write(master, early)  # typed before the question was on screen
        draw, drawn = message.draw, []
        import threading

        def draw_then_type(*args):
            draw(*args)
            if keys and not drawn:  # typed once the question is shown (after its first moment)
                threading.Timer(0.15, os.write, (master, keys)).start()
            drawn.append(args)
        stdin = mock.Mock()
        stdin.fileno.return_value = slave
        with mock.patch.object(message, "draw", side_effect=draw_then_type), \
                mock.patch.dict(os.environ, {message.ENV: json.dumps(payload)}), \
                mock.patch.object(message.sys, "stdin", stdin), \
                mock.patch.object(message.sys, "stdout", io.StringIO()), \
                mock.patch.object(message, "SHOW_WAIT", 0.3), mock.patch.object(message, "ASK_WAIT", 0.6), \
                mock.patch.object(message, "KEY_DELAY", 0.05), \
                mock.patch.object(suspend, "spawn_worker", return_value=spawned) as spawn, \
                mock.patch.object(suspend, "confirm", return_value=confirm_result) as confirm:
            self.assertEqual(message.main(), 0)
        return spawn, confirm

    def test_y_hands_exactly_the_doubt_shown_to_a_worker(self):
        ask = {"session": "default", "pane_id": "w1:p1", "why": "Earmark can't read its prompt"}
        spawn, confirm = self.run_popup({"title": "Suspend?", "body": "x", "ask": ask}, b"y\r")
        args = spawn.call_args.args[0]
        self.assertEqual(args[:6], ["--session", "default", "--pane", "w1:p1",
                                    "--accept", "Earmark can't read its prompt"])
        self.assertEqual(args[6], "--pressed")  # when `y` was confirmed: a late answer then doesn't take the keyboard
        self.assertLess(abs(float(args[7]) - time.time()), 60)
        confirm.assert_not_called()  # the popup closes; the worker suspends

    def test_a_key_typed_before_the_question_doesnt_answer_it(self):  # review 4 R85
        ask = {"session": "default", "pane_id": "w1:p1", "why": "d"}
        spawn, confirm = self.run_popup({"title": "Suspend?", "ask": ask}, b"", early=b"y")
        spawn.assert_not_called()
        confirm.assert_not_called()

    def test_without_a_worker_it_suspends_itself(self):
        ask = {"session": "default", "pane_id": "w1:p1", "why": "d"}
        _, confirm = self.run_popup({"title": "Suspend?", "ask": ask}, b"Y\r", spawned=False)
        confirm.assert_called_once_with("default", "w1:p1", "d")

    def test_anything_else_or_nothing_keeps_it(self):
        ask = {"session": "default", "pane_id": "w1:p1", "why": "d"}
        # Enter alone, a "y" without Enter, a word with a y in it, Esc, or the time running out (R128)
        for keys in (b"n\r", b"\r", b"\n", b"y", b"my yard\r", b"yes\r", b"\x1b", b""):
            spawn, confirm = self.run_popup({"title": "Suspend?", "ask": ask}, keys)
            spawn.assert_not_called()
            confirm.assert_not_called()

    def test_a_message_just_shows(self):
        spawn, confirm = self.run_popup({"title": "Earmark can't suspend this tab", "body": "It's working."}, b"y")
        spawn.assert_not_called()
        confirm.assert_not_called()

    def test_show_opens_the_popup_or_falls_back_to_a_notification(self):
        with mock.patch.object(herdr, "run") as run, mock.patch.object(herdr, "notify") as notify:
            self.assertTrue(message.show("T", "B", ask={"session": "s", "pane_id": "p", "why": "w"}))
        argv = run.call_args.args
        self.assertEqual(argv[:3], ("plugin", "pane", "open"))
        env = argv[argv.index("--env") + 1]
        self.assertEqual(json.loads(env.split("=", 1)[1])["ask"]["why"], "w")
        notify.assert_not_called()
        with mock.patch.object(herdr, "run", side_effect=herdr.HerdrError("no")), \
                mock.patch.object(herdr, "notify") as notify:
            self.assertFalse(message.show("T", "B"))
        notify.assert_called_once_with("T", "B")

    def test_the_hint_stays_on_screen_in_a_small_popup(self):  # review 4 R74
        hint = "y: suspend it anyway    any other key: keep it running"
        rows = message.lines("Suspend this tab anyway?", "a long doubt " * 30, hint, 46, 6)
        self.assertLessEqual(len(rows), 4)  # rows 2..5 of a 6-row popup
        self.assertTrue(rows[1].startswith("y: suspend"))
        self.assertTrue(rows[-1].endswith("…"))
        self.assertTrue(all(len(r) <= 42 for r in rows))
        roomy = message.lines("T", "short", "hint", 60, 20)
        self.assertEqual(roomy, ["T", "hint", "", "short"])


# ------------------------------------------------------------------ R57

class ConfigDirLookupTests(unittest.TestCase):
    def test_a_failed_look_records_nothing_and_is_tried_again_later(self):
        index, archive = {"sessions": {}}, {"entries": {}}
        s = store.session_state(index, "default")
        p = pane("w1:p1")
        with mock.patch.object(core, "now", return_value=T0), \
                mock.patch.object(herdr, "process_info", side_effect=herdr.HerdrError("timeout")):
            core.note_config_dirs(snap([p]), s)
            self.assertNotIn("_config_dir", p)
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([p]), "pane.focused", {}, T0)
        note = index["sessions"]["default"]["panes"]["w1:p1"]
        self.assertNotIn("config_dir", note)  # unknown, not "~/.claude"
        info = {"shell_pid": 1, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        p2 = pane("w1:p1")
        with mock.patch.object(core, "now", return_value=T0 + 100), \
                mock.patch.object(herdr, "process_info", return_value=info) as pi:
            core.note_config_dirs(snap([p2]), index["sessions"]["default"])
        pi.assert_not_called()  # not on every hook
        with mock.patch.object(core, "now", return_value=T0 + core.CONFIG_DIR_RETRY + 1), \
                mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "environ_var", return_value="/cfg"):
            core.note_config_dirs(snap([p2]), index["sessions"]["default"])
        self.assertEqual(p2["_config_dir"], "/cfg")

    def test_unknown_means_earmarks_own_setting_and_empty_means_the_default(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/server"}):
            self.assertEqual(agents._claude_dir(None), "/server")
            self.assertEqual(agents._claude_dir(""), os.path.expanduser("~/.claude"))


# ------------------------------------------------------------------ R58

class CodexDaemonTests(unittest.TestCase):
    def test_codex_without_no_daemon_is_never_suspended(self):
        f = found(T0 - 7200, agent="codex", session_id="019abc", launch=["codex"])
        for manual in (False, True):
            why = suspend.refusal(f, pane("w1:p1", agent="codex", session="019abc"), CFG_TIME, T0, manual, None)
            self.assertIn("--no-daemon", why)
        f = found(T0 - 7200, agent="codex", session_id="019abc", launch=["codex", "--no-daemon"])
        self.assertNotIn("--no-daemon", suspend.refusal(f, pane("w1:p1", agent="codex", session="019abc"),
                                                         CFG_TIME, T0, True, None))


# ------------------------------------------------------------------ R59

class LongLineTests(unittest.TestCase):
    def test_a_line_longer_than_the_window_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            call = {"type": "assistant", "timestamp": "2027-01-15T08:00:00Z", "message": {"content": [
                {"type": "tool_use", "name": "CronCreate", "input": {}}]}}
            with open(path, "w") as f:
                f.write(json.dumps({"type": "user", "pad": "x" * 3000}) + "\n" + json.dumps(call) + "\n")
            cache = {}
            with mock.patch.object(agents, "TIMER_READ", 1000):
                for _ in range(8):
                    wake, tasks = agents.claude_timers(path, 0, cache, T0)
            self.assertEqual(tasks, 1)
            self.assertFalse(cache["behind"])


# ------------------------------------------------------------------ R60

class PlaceholderMarkTests(StateDir):
    def test_only_its_own_sessions_marks(self):
        store.save_index({"sessions": {
            "default": {"panes": {}, "suspended": {"w1:p2": suspended_rec(pane_id="w1:p2", tab_id="w1:t2")},
                        "marked": {"w1:t2": "💤"}},
            "work": {"panes": {}, "suspended": {}, "marked": {"w1:t2": "💤"}}}})
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p2", tab="w1:t2")), \
                mock.patch.object(herdr, "run", return_value={"tab": {"label": "💤 api"}}):
            placeholder.unmark("work", "w1:p2")
        index = store.load_index()
        self.assertEqual(index["sessions"]["default"]["marked"], {"w1:t2": "💤"})
        self.assertEqual(index["sessions"]["work"]["marked"], {})


# ------------------------------------------------------------------ R61

class MarkOrderTests(StateDir):
    def test_the_tab_is_listed_before_it_is_renamed(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        seen = []

        def run(*args):
            if args[:2] == ("tab", "get"):
                return {"tab": {"label": "auth"}}
            if args[:2] == ("tab", "rename"):
                seen.append(store.load_index()["sessions"]["default"].get("marked", {}).get("w1:t1"))
            return {}
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", tab="w1:t1")), \
                mock.patch.object(herdr, "run", side_effect=run):
            suspend.mark_tab("default", "w1:p1", "💤")
        self.assertEqual(seen, ["💤"])

    def test_a_failed_rename_unlists_it(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})

        def run(*args):
            if args[:2] == ("tab", "get"):
                return {"tab": {"label": "auth"}}
            raise herdr.HerdrError("gone")
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", tab="w1:t1")), \
                mock.patch.object(herdr, "run", side_effect=run):
            suspend.mark_tab("default", "w1:p1", "💤")
        self.assertEqual(store.load_index()["sessions"]["default"].get("marked"), {})


# ------------------------------------------------------------------ R66

class WriteTests(StateDir):
    def hook(self, t, panes):
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes)), \
                mock.patch.object(herdr, "process_info", return_value={}), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(core, "now", return_value=t), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True), \
                mock.patch.object(suspend, "unmark_tab"):
            core.handle_event("pane.focused", {"data": {}}, env={})

    def test_identical_hooks_with_a_suspended_tab_dont_rewrite_the_index(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        panes = [pane("w1:p1", session=None, tab="w1:t1"), pane("w1:p2", session="s2", tab="w1:t2")]
        self.hook(T0, panes)
        self.hook(T0 + 5, panes)
        self.assertIn("w1:p1", store.load_index()["sessions"]["default"]["suspended"])  # still suspended
        with mock.patch.object(store, "save_index", wraps=store.save_index) as save:
            self.hook(T0 + 10, panes)
            self.hook(T0 + 15, panes)
        self.assertEqual(save.call_count, 0)

    def test_unchanged_timers_arent_rewritten(self):
        suspend.save_timers("default", {"claude:s1": {"offset": 5}})
        with mock.patch.object(store, "save_json", wraps=store.save_json) as save:
            suspend.save_timers("default", {"claude:s1": {"offset": 5}})
            save.assert_not_called()
            suspend.save_timers("default", {"claude:s1": {"offset": 6}})
            save.assert_called_once()


# ------------------------------------------------------------------ R67

class PopupClickTests(StateDir):
    def test_clicks_below_the_list_hit_nothing(self):
        entries = {f"claude:s{i}": {"herdr_session": "default", "workspace_label": "Work", "agent": "claude",
                                    "session_id": f"s{i}", "last_active": T0 - i, "closed_at": T0} for i in range(20)}
        store.save_archive({"entries": entries})
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            popup = ui.Popup({"workspace_label": "Work"})
        self.assertEqual(len(popup.rows), 20)
        self.assertIsNone(popup.row_at(8, 10))  # the rule
        self.assertIsNone(popup.row_at(9, 10))  # the help line
        self.assertEqual(popup.row_at(7, 10), 5)
        self.assertIsNone(popup.row_at(1, 10))


# ------------------------------------------------------------------ R68

class SharedPiecesTests(unittest.TestCase):
    def test_one_definition_of_what_cant_be_typed(self):
        self.assertFalse(hasattr(suspend, "_UNSAFE_FOR_SHELLS") or hasattr(agents, "_UNTYPABLE"))
        self.assertEqual(agents.env_prefix("claude", "/a b"), "CLAUDE_CONFIG_DIR='/a b' ")  # quoted
        self.assertEqual(agents.env_prefix("claude", "/a'b"), "")

    def test_claude_facts_dont_load_sqlite(self):
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); import earmark.placeholder, earmark.agents as a; "
                "a.session_facts('claude', 'abc'); print('sqlite3' in sys.modules)") % os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=dict(os.environ, HOME=tempfile.gettempdir()), timeout=30)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)


# ------------------------------------------------------- reviewers' survivors

class ReviewerSurvivorTests(StateDir):
    """One test per mutation of the round 3 reviewers that the suite let
    through (tests/mutations.md, "r3-")."""

    def test_in_view_at_the_first_look_is_enough(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        bare = pane("w1:p1", session=None, tab="w1:t1")
        views = [snap([bare, pane("w1:p8", session=None, tab="w1:t1", focused=True)]), snap([bare])]
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", side_effect=lambda: views.pop(0) if len(views) > 1 else views[0]), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertEqual(typed(run), [])

    def test_only_this_panes_placeholder_counts(self):
        from test_suspend import ph_info
        self.assertFalse(suspend.placeholder_pid("default", "w1:p1", ph_info(pane_id="w1:p9")))
        self.assertFalse(suspend.placeholder_pid("default", "w1:p1", ph_info(session="other")))
        self.assertTrue(suspend.placeholder_pid("default", "w1:p1", ph_info()))

    def test_the_return_grace_holds_to_its_end(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}, "quiet_until": time.time() + 60}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_not_called()

    def test_a_draft_starting_with_try_is_a_draft(self):
        rule = "─" * 30
        screen = "\n".join([rule, "❯ Try harder on the parser", rule])
        self.assertEqual(agents.draft_text(screen, "claude"), "Try harder on the parser")

    def test_check_pane_tells_arm_its_a_restart(self):
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(suspend, "arm", return_value=True) as arm:
            suspend.check_pane("default", "w1:p1", suspended_rec(), pane("w1:p1", session=None), restart=True)
        self.assertIs(arm.call_args.kwargs["restart"], True)

    def test_another_agents_process_isnt_its_resume_unless_herdr_lists_it(self):
        rec = suspended_rec(agent="codex", session_id="019abc")
        info = {"shell_pid": 1, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "codex", "argv": ["codex"]}]}
        self.assertFalse(suspend.resumed_by_herdr(rec, pane("w1:p1", session=None), info))
        self.assertTrue(suspend.resumed_by_herdr(rec, pane("w1:p1", agent="codex", session="019abc"), info))

    def test_drop_screen_deletes_only_its_own_copies(self):
        outside = os.path.join(self.dir.name, "keep.txt")
        open(outside, "w").close()
        suspend.drop_screen({"screen": outside})
        self.assertTrue(os.path.exists(outside))
        inside = os.path.join(store.screens_dir(), "x.ansi")
        open(inside, "w").close()
        suspend.drop_screen({"screen": inside})
        self.assertFalse(os.path.exists(inside))

    def test_screen_copies_are_private(self):
        self.assertEqual(os.stat(store.screens_dir()).st_mode & 0o077, 0)

    def test_manual_mode_runs_no_automatic_check(self):
        with mock.patch.object(suspend, "auto") as auto:
            suspend.worker("default", MANUAL)
        auto.assert_not_called()

    def test_a_stop_isnt_called_stalled_before_stop_stale(self):
        rec = suspended_rec(state="stopping", at=T0)
        suspended, entries = {"w1:p1": rec}, {}
        s = snap([pane("w1:p1", session=None)])
        core.settle_suspended(suspended, entries, "default", s, T0 + 5, lambda n: n, flags={})
        self.assertEqual(suspended["w1:p1"]["state"], "stopping")
        core.settle_suspended(suspended, entries, "default", s, T0 + suspend.STOP_STALE + 1, lambda n: n,
                              flags={})
        self.assertEqual(suspended["w1:p1"]["state"], "suspended")

    def test_memory_mode_acts_only_below_the_line(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="memory", memory_below=20))
        looks = [(pane("w1:p1"), {}, found(T0 - 3600))]
        self.assertEqual(suspend.choose(looks, cfg, T0, available=20.0, total_kb=10_000_000), [])
        self.assertTrue(suspend.choose(looks, cfg, T0, available=19.0, total_kb=10_000_000))

    def test_memavailable_not_memfree(self):
        path = os.path.join(self.dir.name, "meminfo")
        with open(path, "w") as f:
            f.write("MemTotal: 1000 kB\nMemFree: 50 kB\nMemAvailable: 600 kB\n")
        with mock.patch.object(procs, "MEMINFO", path):
            self.assertEqual(procs.available_percent(), 60.0)

    def test_an_agent_active_recently_isnt_looked_at(self):
        now = time.time()
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1", "since": now - 60}},
                                                   "suspended": {}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_not_called()


class ReviewerSurvivorTimerTests(unittest.TestCase):
    def look(self, wake=0, behind=False):
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}

        def timers(path, since, cache, now):
            if behind:
                cache["behind"] = True
            return wake, 0
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "started_at", return_value=None), \
                mock.patch.object(agents, "claude_activity", return_value=0), \
                mock.patch.object(agents, "claude_registry", return_value={}), \
                mock.patch.object(agents, "claude_timers", side_effect=timers), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source="/t.jsonl")):
            return suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}),
                                T0, {})

    def test_a_wake_up_a_little_overdue_still_counts(self):
        self.assertIn("/loop", self.look(wake=T0 - 60)["timers"])
        self.assertEqual(self.look(wake=T0 - suspend.TIMER_GRACE - 60)["timers"], "")

    def test_look_keeps_the_mode_from_the_whole_read(self):  # R70
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}

        def timers(path, since, cache, now):
            cache["mode"] = "plan"
            return 0, 0
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "started_at", return_value=None), \
                mock.patch.object(agents, "claude_activity", return_value=0), \
                mock.patch.object(agents, "claude_registry", return_value={}), \
                mock.patch.object(agents, "claude_timers", side_effect=timers), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source="/t.jsonl")):
            found_ = suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}),
                                  T0, {})
        self.assertEqual(found_["mode"], "plan")

    def test_a_transcript_not_read_to_the_end_keeps_it_awake(self):
        self.assertIn("hasn't read", self.look(behind=True)["timers"])


class ReviewerSurvivorArchiveTests(unittest.TestCase):
    def setUp(self):
        self.index, self.archive = {"sessions": {}}, {"entries": {}}

    def apply(self, panes, t, event="pane.focused"):
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            return core.apply(self.index, self.archive, "default", snap(panes), event, {}, t)

    def test_other_sessions_are_forgotten_after_days_not_hours(self):
        self.index["sessions"]["other"] = {"panes": {}, "seen": T0 - 2 * 86400}
        self.apply([], T0)
        self.assertIn("other", self.index["sessions"])
        self.index["sessions"]["other"]["seen"] = T0 - (core.FORGET_SESSION_DAYS + 1) * 86400
        self.apply([], T0 + 1)
        self.assertNotIn("other", self.index["sessions"])

    def test_the_agents_own_folder_not_the_shells(self):
        self.apply([dict(pane("w1:p1"), cwd="/shell", foreground_cwd="/agent")], T0)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["cwd"], "/agent")

    def test_a_suspended_tabs_layout_keeps_its_records_folder(self):
        s = snap([dict(pane("w1:p1", session=None, tab="w1:t1"), cwd="/shell", foreground_cwd="/shell")])
        layout = core.tab_layouts(s, {}, {"w1:p1": suspended_rec(cwd="/rec")})
        self.assertEqual(layout["w1"]["tabs"][0]["cwd"], "/rec")

    def test_a_layout_keeps_the_claude_folder(self):
        s = snap([pane("w1:p1", tab="w1:t1")])
        layout = core.tab_layouts(s, {"w1:p1": {"session_id": "s1", "config_dir": "/cfg"}}, {})
        self.assertEqual(layout["w1"]["tabs"][0]["config_dir"], "/cfg")

    def test_last_active_is_the_sessions_own(self):
        entries = {}
        note = {"pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "workspace_label": "Work",
                "workspace_id": "w1", "seen": T0 - 10}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS, last_active=T0 - 5000)):
            core.archive_note(entries, "default", note, T0, "closed")
        self.assertEqual(entries["claude:s1"]["last_active"], T0 - 5000)

    def test_closed_workspaces_age_out_by_default(self):
        archive = {"entries": {}, "workspaces": {"k": {"key": "k", "closed_at": T0 - 40 * 86400, "tabs": []}}}
        core.prune(archive, dict(config.DEFAULTS), T0)
        self.assertEqual(archive["workspaces"], {})


class ReviewerSurvivorRestoreTests(StateDir):
    def test_restore_never_resumes_a_session_open_elsewhere(self):
        record = {"key": "k", "label": "Elsewhere", "tabs": [{"label": "auth", "cwd": "/proj", "agent": "claude",
                                                               "session_id": "s1"}]}
        created = {"workspace": {"workspace_id": "w5"}, "tab": {"tab_id": "w5:t1"}, "root_pane": {"pane_id": "w5:p1"}}
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(agents, "claude_running", return_value=True), \
                mock.patch.object(herdr, "run", side_effect=lambda *a, **k: created if a[:2] == ("workspace", "create") else {}) as run:
            core.restore_workspace(record, CFG)
        self.assertNotIn(("pane", "run"), [c.args[:2] for c in run.call_args_list])


class ReviewerSurvivorSmallTests(unittest.TestCase):
    def test_everything_after_double_dash_is_the_prompt(self):
        self.assertEqual(agents.launch_flags("claude", ["claude", "--", "--model", "x"]), ([], []))

    def test_plan_mode_comes_back(self):
        argv = agents.live_resume_argv("claude", "abc", {}, [], "plan")
        self.assertEqual(argv[-2:], ["--permission-mode", "plan"])

    def test_a_hash_inside_a_string_is_kept(self):
        self.assertEqual(config.parse_simple_toml('tab_mark = "#z" # note\n')["tab_mark"], "#z")

    def test_fit_leaves_room_for_the_ellipsis(self):
        self.assertEqual(ui.fit("abcdef", 4), "abc…")
        self.assertEqual(ui.cols(ui.fit("一二三四五", 5)), 5)

    def test_sessions_that_arent_records_are_dropped(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": d}):
            with open(os.path.join(d, "index.json"), "w") as f:
                json.dump({"sessions": {"bad": {"panes": []}, "ok": {"panes": {}}}}, f)
            self.assertEqual(list(store.load_index()["sessions"]), ["ok"])

    def test_the_key_takes_the_pane_herdr_says_is_in_view(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "earmark_cli", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "earmark.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"focused_pane_id": "w1:p2"}),
                                          "HERDR_PANE_ID": "w1:p9"}), \
                mock.patch.object(suspend, "key") as key, mock.patch.object(herdr, "session_name", return_value="default"):
            cli.cmd_suspend()
        key.assert_called_once_with("default", "w1:p2")


class ReviewerSurvivorPopupTests(StateDir):
    def test_while_asking_only_the_footer_buttons_act(self):
        store.save_archive({"entries": {"claude:s1": {"herdr_session": "default", "workspace_label": "Work",
                                                      "agent": "claude", "session_id": "s1", "last_active": T0,
                                                      "closed_at": T0}}})
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            popup = ui.Popup({"workspace_label": "Work"})
        popup.confirm, popup.buttons = "claude:s1", {"forget": (0, 40)}

        class Scr:
            def getmaxyx(self):
                return (20, 80)
        with mock.patch.object(ui.curses, "getmouse", return_value=(0, 5, 3, 0, ui.curses.BUTTON1_CLICKED)):
            popup.on_mouse(Scr())
        self.assertEqual(len(store.load_archive()["entries"]), 1)
        self.assertEqual(popup.confirm, "claude:s1")


# ------------------------------------- messages = "toast" (Cody, 2026-11-26)

TOAST = dict(CFG, suspend=dict(CFG["suspend"], when="manual", messages="toast"))


class HerdrToastSettingTests(unittest.TestCase):
    def read(self, text, fallback=False):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.toml")
            if text is not None:
                with open(path, "w") as f:
                    f.write(text)
            with mock.patch.dict(os.environ, {"HERDR_CONFIG_PATH": path}), \
                    mock.patch.object(config, "tomllib", None if fallback else config.tomllib):
                return herdr.toasts_on()

    def test_herdrs_toast_setting_is_read(self):
        for fallback in (False, True):
            self.assertIs(self.read(None, fallback), False)  # no config: Herdr's default, off
            self.assertIs(self.read("[ui]\nx = 1\n", fallback), False)
            self.assertIs(self.read('[ui.toast]\ndelivery = "off"\n', fallback), False)
            self.assertIs(self.read('[ui.toast]\ndelivery = "herdr"\n', fallback), True)
            self.assertIs(self.read('[[keys.command]]\nkey = "prefix+a"\n[ui.toast]\ndelivery = "system"\n',
                                    fallback), True)

    def test_the_setting_is_checked(self):
        self.assertEqual(config.SUSPEND_DEFAULTS["messages"], "popup")  # nobody gets nothing by default
        self.assertEqual(config.suspend_settings({"messages": "toast"})["messages"], "toast")
        self.assertEqual(config.suspend_settings({"messages": "loud"})["messages"], "popup")


class ToastModeTests(SuspendPaneTests):
    """messages = "toast" goes by Herdr's own answer to whether a toast
    was shown (review 4 R69); a question goes by toast only with Herdr's
    in-app delivery, read from its config (R80)."""

    def kills(self):
        return [e for e in self.events if e[0] == "kill"]

    def test_toast_mode_answers_in_toasts_herdr_showed(self):
        with mock.patch.object(suspend.herdr, "notify", return_value=True) as notify, \
                mock.patch.object(suspend.message, "show") as show:
            suspend.say(TOAST, "T", "B")
            suspend.say(MANUAL, "T2", "B2")
        notify.assert_called_once_with("T", "B")
        show.assert_called_once_with("T2", "B2", focus=True)

    def test_a_toast_herdr_didnt_show_goes_to_the_popup(self):
        for answer in (False, None):  # not shown (off, rate limited, busy, no client), or no answer
            with mock.patch.object(suspend.herdr, "notify", return_value=answer), \
                    mock.patch.object(suspend.message, "show") as show:
                suspend.say(TOAST, "T", "B")
            show.assert_called_once_with("T", "B", focus=True)

    def press(self, at, shown=True, delivery="herdr"):
        with mock.patch.object(suspend.herdr, "setting", return_value=delivery), \
                mock.patch.object(suspend.herdr, "notify", return_value=shown) as notify, \
                mock.patch.object(suspend.message, "show") as show, \
                mock.patch.object(suspend.time, "time", return_value=at):
            suspend.manual("default", "w1:p1", TOAST)
        return notify, show

    def test_toast_mode_confirms_with_a_second_press_in_time(self):
        self.screen = "some output\n$ "  # a prompt Earmark can't read
        notify, show = self.press(T0)
        self.assertEqual(self.kills(), [])
        self.assertIn("press again", notify.call_args.args[0])
        show.assert_not_called()
        self.press(T0 + suspend.CONFIRM_WINDOW + 1)  # too late: asks again
        self.assertEqual(self.kills(), [])
        self.press(T0 + suspend.CONFIRM_WINDOW + 3)
        self.assertEqual(len(self.kills()), 1)

    def test_a_question_herdr_didnt_show_is_never_confirmed_by_a_second_press(self):
        self.screen = "some output\n$ "
        _, show = self.press(T0, shown=False)
        self.assertTrue(show.call_args.kwargs.get("ask"))  # the popup asks instead
        self.press(T0 + 2, shown=False)
        self.assertEqual(self.kills(), [])

    def test_a_second_press_confirms_only_the_same_doubt(self):
        self.assertFalse(suspend.confirmed("default", "w1:p1", "A", T0))  # nothing asked
        suspend.remember_ask("default", "w1:p1", "A", T0)
        self.assertFalse(suspend.confirmed("default", "w1:p1", "B", T0 + 1))  # another doubt (and used up)
        suspend.remember_ask("default", "w1:p1", "B", T0 + 2)
        self.assertTrue(suspend.confirmed("default", "w1:p1", "B", T0 + 3))
        self.assertFalse(suspend.confirmed("default", "w1:p1", "B", T0 + 4))  # used up


class CheckToastNoteTests(StateDir):
    def test_check_says_when_toast_mode_falls_back(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "earmark_cli", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "earmark.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        self.settings('[suspend]\nwhen = "manual"\nmessages = "toast"\n')
        out = io.StringIO()
        with mock.patch.object(herdr, "toasts_on", return_value=False), mock.patch.object(sys, "stdout", out):
            cli.cmd_check()
        self.assertIn("answers in its popup", out.getvalue())


# ------------------------------------------------------------------ round 4

class HerdrReplyTests(unittest.TestCase):
    def test_notify_reports_herdrs_answer(self):  # R69
        for reply, want in (({"type": "notification_show", "shown": True, "reason": "shown"}, True),
                            ({"type": "notification_show", "shown": False, "reason": "rate_limited"}, False),
                            ({}, None), (None, None)):
            with mock.patch.object(herdr, "run", return_value=reply):
                self.assertIs(herdr.notify("T"), want)
        with mock.patch.object(herdr, "run", side_effect=herdr.HerdrError("x")):
            self.assertIs(herdr.notify("T"), False)


class PermissionModeTests(unittest.TestCase):  # R70
    def test_an_unknown_mode_never_resumes_bypassing(self):
        flags = agents.claude_resume_flags(["--dangerously-skip-permissions", "--model", "m"], "")
        self.assertEqual(flags, ["--allow-dangerously-skip-permissions", "--model", "m"])
        self.assertEqual(agents.claude_resume_flags(["--dangerously-skip-permissions"], "bypassPermissions"),
                         ["--allow-dangerously-skip-permissions", "--permission-mode", "bypassPermissions"])

    def test_the_mode_is_read_over_the_whole_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "permission-mode", "permissionMode": "bypassPermissions"}) + "\n")
                f.write(json.dumps({"type": "permission-mode", "permissionMode": "default"}) + "\n")
                for _ in range(400):  # a long autonomous run since: 400 KB past the last mode record
                    f.write(json.dumps({"type": "assistant", "pad": "x" * 1000}) + "\n")
            cache = {}
            for _ in range(3):
                agents.claude_timers(path, 0, cache, T0)
            self.assertEqual(cache["mode"], "default")
            argv = agents.live_resume_argv("claude", "abc-123", {}, ["--dangerously-skip-permissions"], cache["mode"])
            self.assertNotIn("--dangerously-skip-permissions", argv)


class HookWriteTests(StateDir):  # R71
    def hook(self, t, panes, event="pane.agent_status_changed"):
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes)), \
                mock.patch.object(herdr, "process_info", return_value={}), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(core, "now", return_value=t), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True):
            core.handle_event(event, {"data": {}}, env={})

    def test_hooks_with_a_tab_in_view_and_suspend_off_dont_rewrite_the_index(self):
        panes = [pane("w1:p1", focused=True), pane("w1:p2", session="s2", tab="w1:t2")]
        self.hook(T0, panes)
        with mock.patch.object(store, "save_index", wraps=store.save_index) as save:
            for k in (1, 2, 3):
                self.hook(T0 + 45 * k, panes)
        self.assertEqual(save.call_count, 0)


class PlaceholderAliveTests(StateDir):  # R72
    def test_a_live_placeholder_is_seen_without_asking_herdr(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {
            "w1:p1": suspended_rec(ph=[4242, "tok"])}}}})
        with mock.patch.object(procs, "start_token", return_value="tok"), \
                mock.patch.object(herdr, "process_info") as pi, \
                mock.patch.object(suspend, "check_pane") as check:
            suspend.rearm_pass("default", snap([pane("w1:p1", session=None)]))
        pi.assert_not_called()
        check.assert_not_called()
        with mock.patch.object(procs, "start_token", return_value="another process"), \
                mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(suspend, "check_pane", return_value=False) as check:
            suspend.rearm_pass("default", snap([dict(pane("w1:p1", session=None), revision=4)]))
        check.assert_called_once()

    def test_arm_remembers_the_placeholder(self):
        from test_suspend import ph_info
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        with mock.patch.object(herdr, "process_info", return_value=ph_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(procs, "start_token", return_value="tok"):
            self.assertTrue(suspend.arm("default", "w1:p1", view_ok=True))
        self.assertEqual(suspend.record("default", "w1:p1")["ph"], [60, "tok"])

    def test_no_process_scan_when_nobody_needs_a_look(self):
        now = time.time()
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1", "since": now}},
                                                   "suspended": {}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(procs, "Table") as table, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        table.assert_not_called()


class RestartSignalTests(unittest.TestCase):  # R73
    def test_a_new_parent_on_every_hook_stops_counting_as_restarts(self):
        index, archive = {"sessions": {}}, {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            for k, ppid in enumerate((100, 101, 102, 103)):
                core.apply(index, archive, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0 + 10 * k,
                           server_pid=ppid)
            self.assertTrue(index["sessions"]["default"]["ppid_unreliable"])
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.agent_detected",
                       {"pane_id": "w1:p1", "released": True}, T0 + 120, server_pid=104)
        self.assertIn("claude:s1", archive["entries"])  # /exit still archived

    def test_one_new_parent_is_a_restart(self):
        index, archive = {"sessions": {}}, {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0, server_pid=100)
            core.apply(index, archive, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0 + 10, server_pid=101)
        self.assertEqual(index["sessions"]["default"]["boot"], T0 + 10)

    def test_the_grace_stretches_with_herdrs_restore_delay(self):
        with mock.patch.object(herdr, "setting", return_value=2000):
            self.assertEqual(core.boot_grace_for(40), 30 + 80)
        with mock.patch.object(herdr, "setting", return_value=None):
            self.assertEqual(core.boot_grace_for(40), core.BOOT_GRACE)


class EnvironmentReadTests(unittest.TestCase):  # R75
    def test_unset_and_unreadable_differ(self):
        self.assertEqual(procs.environ_var(os.getpid(), "EARMARK_SURELY_UNSET_X"), "")
        self.assertIsNone(procs.environ_var(2 ** 22 + 12345, "HOME"))  # no such process

    def test_macos_values_with_spaces(self):
        out = mock.Mock(returncode=0, stdout=b"node /x/cli.js --model m CLAUDE_CONFIG_DIR=/Users/a/Library/Application "
                                             b"Support/claude HOME=/Users/a\n")
        with mock.patch.object(procs, "linux", return_value=False), \
                mock.patch.object(procs.subprocess, "run", return_value=out):
            self.assertEqual(procs.environ_var(1, "CLAUDE_CONFIG_DIR"), "/Users/a/Library/Application Support/claude")
            self.assertEqual(procs.environ_var(1, "NOT_THERE"), "")
        with mock.patch.object(procs, "linux", return_value=False), \
                mock.patch.object(procs.subprocess, "run", return_value=mock.Mock(returncode=1, stdout=b"")):
            self.assertIsNone(procs.environ_var(1, "CLAUDE_CONFIG_DIR"))

    def test_an_unreadable_environment_is_asked_again(self):
        info = {"shell_pid": 1, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        p = pane("w1:p1")
        with mock.patch.object(core, "now", return_value=T0), \
                mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "environ_var", return_value=None):
            core.note_config_dirs(snap([p]), {"panes": {}})
        self.assertNotIn("_config_dir", p)
        self.assertEqual(p["_config_dir_tried"], T0)

    def test_readme_resume_examples_keep_command(self):
        readme = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")).read()
        import re
        examples = re.findall(r'claude = \[([^\]]*)\]', readme)
        self.assertTrue(examples)
        self.assertTrue(all(e.strip().startswith('"command"') for e in examples), examples)


class SidebarOffTests(unittest.TestCase):  # R76
    def test_turning_the_count_off_clears_it_once(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": d, "HERDR_PLUGIN_CONFIG_DIR": d}):
            with open(os.path.join(d, "config.toml"), "w") as f:
                f.write("report_count = false\n")
            store.save_index({"sessions": {"default": {"panes": {}, "reported": {"w1": "3 archived"}}}})
            sent = []
            with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                    mock.patch.object(core, "send_reports", side_effect=lambda r: sent.append(list(r))), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True):
                core.handle_event("pane.focused", {"data": {}}, env={})
                core.handle_event("pane.focused", {"data": {}}, env={})
            self.assertEqual([[(w, t) for w, t, _ in r] for r in sent], [[("w1", "")], []])


# ------------------------------------------- round 4 reviewer's survivors

class R4SurvivorTests(StateDir):
    """One test per mutation of the round 4 fit reviewer that the suite let
    through (tests/mutations.md, "r4-fit:")."""

    def test_the_worker_lock_is_one_at_a_time(self):
        with store.try_lock("x") as first:
            with store.try_lock("x") as second:
                self.assertEqual((first, second), (True, False))
        with store.try_lock("worker-" + __import__("hashlib").sha256(b"default").hexdigest()[:12]) as mine:
            self.assertTrue(mine)
            with mock.patch.object(suspend, "auto") as auto:
                suspend.worker("default", CFG_TIME)
            auto.assert_not_called()  # another worker is checking

    def test_a_new_tab_never_gets_a_folder_that_isnt_there(self):
        with mock.patch.object(herdr, "run", return_value={"tab": {"tab_id": "t"}, "root_pane": {"pane_id": "p"}}) as run:
            herdr.new_tab("w1", "/nowhere/at/all", "x")
        self.assertNotIn("--cwd", run.call_args.args)

    def test_a_zero_count_clears_the_token(self):
        with mock.patch.object(herdr, "run") as run:
            herdr.report_count("w1", "", 5)
        self.assertIn("--clear-token", run.call_args.args)
        self.assertEqual(core.count_text(0), "")

    def test_a_long_tab_mark_is_refused(self):
        self.assertEqual(config.suspend_settings({"tab_mark": "zzzzzzzzz"})["tab_mark"], "💤")

    def test_keep_days_zero_keeps_closed_workspaces(self):
        self.settings("keep_days = 0\n")
        cfg = config.load()
        self.assertEqual(cfg["keep_days"], 0)
        archive = {"entries": {}, "workspaces": {"k": {"key": "k", "closed_at": T0 - 400 * 86400, "tabs": []}}}
        core.prune(archive, cfg, T0)
        self.assertIn("k", archive["workspaces"])

    def hook(self, t, event="pane.focused", data=None, panes=None):
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes if panes is not None else [pane("w1:p1")])), \
                mock.patch.object(herdr, "process_info", return_value={}), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(core, "now", return_value=t), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True), \
                mock.patch.object(core, "_wait_for_session") as wait:
            core.handle_event(event, {"data": data or {}}, env={})
        return wait

    def test_a_short_quiet_spell_isnt_an_absence(self):
        self.settings('[suspend]\nwhen = "time"\n')
        self.hook(T0)
        self.hook(T0 + suspend.RETURN_GRACE + 120)  # longer than the grace, shorter than AWAY_GAP
        self.assertNotIn("quiet_until", store.load_index()["sessions"]["default"])

    def test_a_released_agent_isnt_waited_for(self):
        wait = self.hook(T0, event="pane.agent_detected", data={"pane_id": "w1:p1", "released": True})
        wait.assert_not_called()
        wait = self.hook(T0 + 1, event="pane.agent_detected", data={"pane_id": "w1:p1"})
        wait.assert_called_once()

    def test_the_session_wait_ends_when_the_pane_has_no_agent(self):
        clock = iter(range(1000))
        with mock.patch.object(core, "now", side_effect=lambda: float(next(clock))), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)) as get:
            core._wait_for_session("w1:p1")
        self.assertEqual(get.call_count, 1)

    def test_reopen_takes_the_entry_out_of_the_archive(self):
        entry = {"key": "claude:s1", "herdr_session": "default", "agent": "claude", "session_id": "s1",
                 "workspace_id": "w1", "workspace_label": "Work", "cwd": "/proj"}
        store.save_archive({"entries": {"claude:s1": dict(entry)}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(herdr, "new_tab", return_value=("w1:t2", "w1:p2")), \
                mock.patch.object(herdr, "run"), mock.patch.object(core, "_wait_for_session"), \
                mock.patch.object(agents, "claude_running", return_value=False):
            self.assertIsNone(core.reopen(entry, {"workspace_id": "w1"}, CFG))
        self.assertEqual(store.load_archive()["entries"], {})

    def test_restore_leaves_default_tab_names_and_focuses_the_first_tab(self):
        record = {"key": "k", "label": "Work", "tabs": [{"label": "1", "number": 1, "cwd": "/proj"},
                                                         {"label": "2", "number": 2, "cwd": "/proj"},
                                                         {"label": "3", "number": 3, "cwd": "/proj"}]}
        calls = []
        with mock.patch.object(herdr, "snapshot", return_value=snap([], workspaces={"w1": "Work"})), \
                mock.patch.object(herdr, "run", return_value={}), \
                mock.patch.object(herdr, "new_tab", side_effect=lambda w, c, l, focus=True: (
                    calls.append((l, focus)) or (f"w1:t{len(calls)}", f"w1:p{len(calls)}"))):
            core.restore_workspace(record, CFG)
        self.assertEqual(calls, [("", True), ("", False), ("", False)])

    def test_reporting_off_never_sends_a_count(self):
        self.settings("report_count = false\n")
        store.save_archive({"entries": {"claude:x": {"herdr_session": "default", "workspace_label": "Work",
                                                     "agent": "claude", "session_id": "x", "last_active": T0,
                                                     "closed_at": T0}}})
        sent = []
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(core, "send_reports", side_effect=lambda r: sent.extend(r)), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True):
            core.handle_event("pane.focused", {"data": {}}, env={})
        self.assertEqual(sent, [])

    def test_memory_mode_goes_on_while_memory_stays_low(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="memory", memory_below=20))
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        chosen = [(pane(f"w1:p{i}", session=f"s{i}"), {}, found(T0 - 3600, pane_id=f"w1:p{i}")) for i in (1, 2, 3)]
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(suspend, "choose", return_value=chosen), \
                mock.patch.object(procs, "available_percent", return_value=10.0), \
                mock.patch.object(procs, "total_kb", return_value=10_000_000), \
                mock.patch.object(suspend, "suspend_pane", return_value="") as act, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", cfg)
        self.assertEqual(act.call_count, 3)

    def test_timers_of_closed_sessions_are_dropped(self):
        suspend.save_timers("default", {"claude:gone": {"offset": 1}, "claude:s1": {"offset": 2}})
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        self.assertEqual(set(suspend.load_timers("default")), {"claude:s1"})

    def test_the_worker_log_is_rotated_and_the_worker_detached(self):
        path = os.path.join(store.state_dir(), "worker.log")
        with open(path, "w") as f:
            f.write("x" * (300 * 1024))
        with mock.patch.object(suspend.subprocess, "Popen") as popen:
            self.assertTrue(suspend.spawn_worker(["--rearm"]))
        self.assertTrue(os.path.exists(path + ".1"))
        self.assertIs(popen.call_args.kwargs["start_new_session"], True)

    def test_a_placeholder_slow_to_start_is_waited_for(self):
        from test_suspend import ph_info
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        infos = [shell_info(), shell_info(), shell_info(), shell_info(), ph_info()]
        with mock.patch.object(herdr, "process_info", side_effect=lambda pid: infos.pop(0) if len(infos) > 1 else infos[0]), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "run"), \
                mock.patch.object(procs, "start_token", return_value="tok"):
            self.assertTrue(suspend.arm("default", "w1:p1", view_ok=True))
        self.assertEqual(suspend.record("default", "w1:p1")["ph"], [60, "tok"])  # R72: remembered once typed

    def test_memory_counts_the_agents_children_too(self):
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "memory_kb", return_value=1) as mem, \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude"),
                                                         70: (50, "node", "node mcp-server")}), T0, {})
        self.assertEqual(sorted(mem.call_args.args[0]), [50, 70])

    def test_a_stopped_tab_without_its_placeholder_says_so(self):  # R22, its real branch
        with mock.patch.object(suspend, "record", return_value={"state": "suspended"}), \
                mock.patch.object(suspend.message, "show") as show:
            suspend.tell("default", "w1:p1", "its placeholder didn't start", MANUAL)
        self.assertEqual(show.call_args.args[0], "Suspended")

    def test_an_arm_in_progress_is_left_alone(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {
            "w1:p1": suspended_rec(arming=time.time() - 5)}}}})
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1", view_ok=True))
        self.assertEqual(typed(run), [])

    def test_a_tiny_pane_gets_the_notice_not_the_frozen_view(self):
        from test_suspend import claude_screen
        rows = placeholder.compose({"agent": "claude", "tab_label": "auth", "at": T0}, CFG, claude_screen("x"), 4, 24, T0)
        self.assertFalse(any("Done. The tests pass" in r for r in rows))

    def test_the_mark_stays_while_another_split_sleeps(self):
        store.save_index({"sessions": {"default": {"panes": {}, "marked": {"w1:t1": "💤"}, "suspended": {
            "w1:p1": suspended_rec(), "w1:p2": suspended_rec(pane_id="w1:p2", session_id="s2")}}}})
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", tab="w1:t1")), \
                mock.patch.object(herdr, "run", return_value={"tab": {"label": "💤 auth"}}), \
                mock.patch.object(suspend, "unmark_tab") as unmark:
            placeholder.unmark("default", "w1:p1")
        unmark.assert_not_called()

    def test_text_widths_and_ages(self):
        from earmark import text
        self.assertEqual(text.char_cols("Ａ"), 2)  # fullwidth A
        self.assertEqual(text.ago(T0 - 80, T0), "just now")
        self.assertEqual(text.ago(T0 - 100, T0), "1 min ago")


class R4SurvivorPopupTests(StateDir):
    def popup(self, entries):
        store.save_archive({"entries": entries})
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            return ui.Popup({"workspace_label": "Work"})

    def entries(self, n=3):
        return {f"claude:s{i}": {"herdr_session": "default", "workspace_label": "Work", "agent": "claude",
                                 "session_id": f"s{i}", "last_active": T0 - i, "closed_at": T0,
                                 "tab_label": "auth" if i == 1 else f"t{i}"} for i in range(n)}

    def mouse(self, popup, x, y, button):
        class Scr:
            def getmaxyx(self):
                return (20, 80)
        with mock.patch.object(ui.curses, "getmouse", return_value=(0, x, y, 0, button)):
            return popup.on_mouse(Scr())

    def test_enter_never_confirms_forgetting(self):
        popup = self.popup(self.entries())
        popup.on_key("d")
        popup.on_key("\n")
        self.assertEqual(len(store.load_archive()["entries"]), 3)

    def test_only_the_x_asks_to_forget(self):
        popup = self.popup(self.entries())
        self.mouse(popup, 80 - ui.FORGET_COL - 6, 2, ui.curses.BUTTON1_CLICKED)
        self.assertIsNone(popup.confirm)

    def test_the_wheel_moves_the_right_way(self):
        popup = self.popup(self.entries())
        popup.sel = 2
        self.mouse(popup, 10, 3, ui.curses.BUTTON4_PRESSED)
        self.assertEqual(popup.sel, 1)

    def test_the_filter_finds_a_tabs_own_name(self):
        popup = self.popup(self.entries())
        popup.filter = "auth"
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            popup.load()
        self.assertEqual([r["session_id"] for r in popup.rows], ["s1"])

    def test_reopening_updates_the_sidebar_count(self):
        popup = self.popup(self.entries())
        with mock.patch.object(core, "reopen", return_value=None), \
                mock.patch.object(core, "update_counts") as counts:
            self.assertTrue(popup.do_open())
        counts.assert_called_once()


class R4SurvivorAgentTests(unittest.TestCase):
    def test_the_users_own_title_wins(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "custom-title", "customTitle": "Mine"}) + "\n")
                f.write(json.dumps({"type": "ai-title", "aiTitle": "Theirs"}) + "\n")
            self.assertEqual(agents.claude_title(path) if hasattr(agents, "claude_title") else
                             agents._claude_title(path), "Mine")

    def test_only_the_agents_own_calls_set_timers(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                for kind in ("user", "system", "progress"):  # only the agent's own calls count
                    f.write(json.dumps({"type": kind, "timestamp": "2027-01-15T08:00:00Z", "message": {"content": [
                        {"type": "tool_use", "name": "CronCreate", "input": {}}]}}) + "\n")
            self.assertEqual(agents.claude_timers(path, 0, {}, T0)[1], 0)

    def test_a_relative_claude_folder_isnt_typed(self):
        self.assertEqual(agents.env_prefix("claude", "rel/dir"), "")

    def test_a_reused_pid_isnt_claude(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sessions"))
            with open(os.path.join(d, "sessions", "4242.json"), "w") as f:
                json.dump({"pid": 4242, "sessionId": "s1", "startedAt": T0 * 1000}, f)
            with mock.patch.object(agents.os, "kill"), \
                    mock.patch.object(procs, "started_at", return_value=T0 + 120):  # started 2 min later: another
                self.assertFalse(agents.claude_running("s1", d))
            with mock.patch.object(agents.os, "kill"), mock.patch.object(procs, "started_at", return_value=T0 + 5):
                self.assertTrue(agents.claude_running("s1", d))

    def test_macos_start_times_count_days(self):
        with mock.patch.object(procs, "linux", return_value=False), \
                mock.patch.object(procs.subprocess, "run", return_value=mock.Mock(stdout="2-03:04:05\n", returncode=0)), \
                mock.patch.object(procs.time, "time", return_value=T0):
            self.assertAlmostEqual(procs.started_at(1), T0 - (2 * 86400 + 3 * 3600 + 4 * 60 + 5), delta=1)


class R4OwnGapTests(StateDir):
    def test_auto_doesnt_even_look_at_a_split_in_view(self):  # R29
        long_ago = time.time() - 7200  # auto() runs on the real clock
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1", "since": long_ago}},
                                                   "suspended": {}}}})
        view = snap([pane("w1:p1", tab="w1:t1"), pane("w1:p2", session="s2", tab="w1:t1", focused=True, status="working")])
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", tab="w1:t1")])), \
                mock.patch.object(suspend, "look", return_value=None) as look, \
                mock.patch.object(suspend, "choose", return_value=[]), \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_called_once()  # out of view, it would be looked at
        with mock.patch.object(herdr, "snapshot", return_value=view), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_not_called()


# ------------------------------------------------------ round 4 (safety)

class R4SafetyTests(StateDir):
    def test_a_conversation_other_than_herdrs_is_refused(self):  # R79
        f = found(T0 - 7200, registry={"status": "idle", "remote": False, "session_id": "s-other"})
        for manual in (False, True):
            self.assertIn("different conversation", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, manual, None))
        f = found(T0 - 7200, registry={"status": "idle", "remote": False, "session_id": "s1"})
        self.assertEqual(suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None), "")

    def test_folders_that_cant_be_typed_are_refused(self):  # R82
        for kw in ({"config_dir": "/home/u/alt's claude"}, {"config_dir": "claude-alt"}, {"cwd_unsafe": True}):
            f = found(T0 - 7200, **kw)
            for manual in (False, True):
                self.assertIn("typed back safely", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, manual, None), kw)

    def test_a_missing_claude_record_refuses_automatic_suspends(self):  # R87
        f = found(T0 - 7200, registry={})
        self.assertIn("record of this process is missing", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None))
        self.assertEqual(suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, True, None), "")  # the key asks instead

    def test_a_start_time_that_cant_be_read_fails_identity(self):  # R87
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value=None):
            f = suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}),
                             T0, {})
        self.assertIn("start time", f["why"])

    def test_toast_questions_only_in_herdrs_own_toasts_and_never_on_a_double_tap(self):  # R80
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="manual", messages="toast"))
        why = suspend.CONFIRM + "Earmark can't read its prompt"
        with mock.patch.object(herdr, "setting", return_value="terminal"), \
                mock.patch.object(herdr, "notify", return_value=True) as notify, \
                mock.patch.object(suspend.message, "show") as show:
            suspend.tell("default", "w1:p1", why, cfg)
        notify.assert_not_called()
        self.assertTrue(show.call_args.kwargs.get("ask"))
        suspend.remember_ask("default", "w1:p1", "d", T0)
        self.assertFalse(suspend.confirmed("default", "w1:p1", "d", T0 + 0.3))  # a double tap
        suspend.remember_ask("default", "w1:p1", "d", T0)
        self.assertTrue(suspend.confirmed("default", "w1:p1", "d", T0 + 1.5))
        suspend.remember_ask("default", "w1:p2", "d", T0)
        suspend.remember_ask("default", "w1:p3", "d", T0 + 100)  # w1:p2's ask is long over: dropped
        self.assertEqual(set(store.load_index()["sessions"]["default"]["confirm"]), {"w1:p3"})

    def test_a_partial_pane_list_closes_nothing(self):  # R83
        index, archive = {"sessions": {}}, {"entries": {}}
        rec = suspended_rec(pane_id="w1:p2", tab_id="w1:t2")
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p1"), pane("w1:p2", session=None, tab="w1:t2")]),
                       "pane.focused", {}, T0 - 600)
            index["sessions"]["default"]["suspended"] = {"w1:p2": rec}
            odd = snap([])
            odd["tabs"] = {"w1:t1": {"tab_id": "w1:t1", "workspace_id": "w1", "label": "a"},
                           "w1:t2": {"tab_id": "w1:t2", "workspace_id": "w1", "label": "b"}}
            core.apply(index, archive, "default", odd, "pane.focused", {}, T0)
        self.assertEqual(archive["entries"], {})
        self.assertIn("w1:p2", index["sessions"]["default"]["suspended"])
        self.assertIn("w1:p1", index["sessions"]["default"]["panes"])
        self.assertTrue(core.partial_snapshot({"workspaces": {}, "tabs": {}, "panes": {}}))

    def test_ctrl_c_then_ctrl_e_then_ctrl_u(self):  # R84, review 7 R137
        # Ctrl+C cancels an unfinished command (a continuation line); Ctrl+E
        # Ctrl+U then clears the line, all before the placeholder is typed.
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "run") as run:
            suspend.arm("default", "w1:p1", view_ok=True)
        calls = [c.args for c in run.call_args_list if c.args[:2] in (("pane", "send-keys"), ("pane", "run"))]
        self.assertEqual([c[3:] if c[1] == "send-keys" else "run" for c in calls],
                         [("ctrl+c",), ("ctrl+e", "ctrl+u"), "run"])

    def rearm_passes(self, screens, gap=60):
        """Regular re-arm passes, one per screen the pane's bare shell shows,
        `gap` seconds apart, through the real check_pane and arm; returns the
        passes that typed."""
        typed_at, now = [], [T0]
        p = {"p": pane("w1:p1", session=None, tab="w1:t1"), "screen": ""}
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", side_effect=lambda pid: p["p"]), \
                mock.patch.object(herdr, "snapshot", side_effect=lambda: snap([p["p"]])), \
                mock.patch.object(suspend, "screen_print", side_effect=lambda pane_: p["screen"]), \
                mock.patch.object(suspend.time, "time", side_effect=lambda: now[0]), \
                mock.patch.object(suspend.time, "sleep"), \
                mock.patch.object(herdr, "run") as run:
            for i, screen in enumerate(screens):
                p["screen"] = screen
                before = len(typed(run))
                suspend.rearm_pass("default", snap([p["p"]]))
                if len(typed(run)) > before:
                    typed_at.append(i)
                now[0] += gap
        return typed_at

    def test_the_periodic_rearm_waits_for_an_idle_shell(self):  # R84, review 6 R127
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec(base=None)}}}})
        self.assertEqual(self.rearm_passes(["$ ", "$ "]), [1])  # first sight, then unchanged a check later: typed
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec(base=None)}}}})
        # Used since it came back: never automatically, however long it then sits.
        self.assertEqual(self.rearm_passes(["$ ", "$ ls", "$ ls", "$ ls"]), [])

    def test_the_placeholder_drops_queued_keys_before_resuming(self):  # R85
        import select as select_
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        import termios
        import tty
        tty.setraw(slave, termios.TCSANOW)
        os.write(master, b"\r")
        time.sleep(0.05)
        placeholder.discard_input(slave)
        self.assertEqual(select_.select([slave], [], [], 0.05)[0], [])

    def test_a_check_stops_on_a_clock_jump_and_on_a_config_broken_meanwhile(self):  # R86
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        chosen = [(pane(f"w1:p{i}", session=f"s{i}"), {}, found(T0 - 7200, pane_id=f"w1:p{i}")) for i in (1, 2)]
        now = [T0]

        def sleep_through_it(*a, **k):
            now[0] += suspend.AWAY_GAP + 60  # the laptop slept during this suspend
            return ""
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(suspend, "choose", return_value=chosen), \
                mock.patch.object(suspend.time, "time", side_effect=lambda: now[0]), \
                mock.patch.object(suspend, "suspend_pane", side_effect=sleep_through_it) as act, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        self.assertEqual(act.call_count, 1)
        self.settings('[suspend]\nwhen = "time"\n')
        path = config.config_path()

        def act_then_break(*a, **k):
            with open(path, "w") as f:
                f.write('[suspend]\nwhen = "time"\nidle_minutes = "30"\n')
            os.utime(path, (time.time() + 50, time.time() + 50))
            return ""
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(suspend, "choose", return_value=chosen), \
                mock.patch.object(suspend, "suspend_pane", side_effect=act_then_break) as act, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", config.load())
        self.assertEqual(act.call_count, 1)

    def test_a_long_silence_is_recorded_as_an_absence(self):  # R86
        self.settings('[suspend]\nwhen = "time"\n')
        for t in (T0, T0 + suspend.AWAY_GAP + 600):
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                    mock.patch.object(herdr, "process_info", return_value={}), \
                    mock.patch.object(core, "send_reports"), \
                    mock.patch.object(core, "now", return_value=t), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True):
                core.handle_event("pane.focused", {"data": {}}, env={})
        self.assertEqual(store.load_index()["sessions"]["default"]["away"], [T0, T0 + suspend.AWAY_GAP + 600])

    def test_a_wake_up_due_while_asleep_counts_the_sleep(self):  # R86
        # Any sleep after the wake-up was set pushes it back (review 5 R94).
        self.assertEqual(suspend.slept([T0 - 3600, T0 - 60], T0 - 1800), 1740)
        self.assertEqual(suspend.slept([T0 - 3600, T0 - 60], T0 - 4000), 3540)
        self.assertEqual(suspend.slept([T0 - 3600, T0 - 60], T0), 0)
        self.assertEqual(suspend.slept(None, T0), 0)

    def test_the_session_wait_is_bounded_even_if_the_clock_stands_still(self):  # R88
        with mock.patch.object(core, "now", return_value=T0), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None, agent="claude")) as get, \
                mock.patch.object(core.time, "sleep"):
            # an agent with no session yet: waited for, but not for ever
            get.return_value = dict(pane("w1:p1"), agent_session=None, agent="claude")
            core._wait_for_session("w1:p1")
        self.assertLessEqual(get.call_count, int(core.SESSION_WAIT / 0.4) + 1)

    def test_a_damaged_file_set_aside_by_another_reader(self):  # R88
        path = os.path.join(store.state_dir(), "index.json")
        with open(path, "w") as f:
            f.write("{ not json")
        with mock.patch.object(store.os, "replace", side_effect=FileNotFoundError):
            self.assertEqual(store.load_index().get("sessions", {}), {})


class R4SafetySurvivorTests(StateDir):
    def test_last_event_moves_with_the_hooks(self):
        self.settings('[suspend]\nwhen = "time"\n')
        for k in range(5):  # a hook every 5 minutes for 20 minutes: never an absence
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                    mock.patch.object(herdr, "process_info", return_value={}), \
                    mock.patch.object(core, "send_reports"), \
                    mock.patch.object(core, "now", return_value=T0 + 300 * k), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True):
                core.handle_event("pane.focused", {"data": {}}, env={})
        self.assertNotIn("quiet_until", store.load_index()["sessions"]["default"])

    def test_the_placeholder_ignores_a_record_in_an_unknown_state(self):
        class NoTerminal:
            def __init__(self, fd):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass
        with mock.patch.object(suspend, "record", return_value={"state": "gone", "agent": "claude"}), \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(placeholder, "Terminal", NoTerminal), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(placeholder, "wait_for_key", return_value="hangup") as wait, \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(placeholder.main("default", "w1:p1"), 1)
        wait.assert_not_called()


class R4SafetyFlowTests(SuspendPaneTests):
    def test_a_newer_stopping_record_gets_no_signal(self):
        def pane_and_restamp(pane_id):
            index = store.load_index()
            rec = index["sessions"]["default"].get("suspended", {}).get("w1:p1")
            if rec:
                rec["at"] = rec["at"] + 5  # another worker's record for the same pane
                store.save_index(index)
            return self.fake_pane(pane_id)
        with mock.patch.object(suspend.herdr, "pane", side_effect=pane_and_restamp), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("record changed", why)
        self.assertEqual([e for e in self.events if e[0] == "kill"], [])

    def test_a_cron_delete_never_takes_another_task(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")

            def call(name, stamp, tool_id=None, **args):
                item = {"type": "tool_use", "name": name, "input": args}
                if tool_id:
                    item["id"] = tool_id
                return {"type": "assistant", "timestamp": stamp, "message": {"content": [item]}}

            def answer(tool_id, text):
                return {"type": "user", "timestamp": "2027-01-15T08:00:00Z", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}
            with open(path, "w") as f:
                for r in (call("CronCreate", "2027-01-15T08:00:00Z", "t1", cron="*/5 * * * *"),
                          answer("t1", "Scheduled recurring job rec11111"),
                          call("CronCreate", "2027-01-15T08:01:00Z", "t2", recurring=False),
                          answer("t2", "Scheduled one-shot job one22222"),
                          call("CronDelete", "2027-01-15T08:02:00Z", id="one22222")):
                    f.write(json.dumps(r) + "\n")
            later = T0 + 25 * 3600
            self.assertEqual(agents.claude_timers(path, 0, {}, later)[1], 1)  # the recurring one, still there


# ------------------------------------------------------------------ round 5

class R5Tests(StateDir):
    def test_a_recreated_sessions_tab_isnt_the_records(self):  # R93
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p2": suspended_rec(
            pane_id="w1:p2", tab_id="w1:t2", tab_label="auth", tab_number=2, workspace_label="Work")}}}})
        new = dict(pane("w1:p2", session=None, tab="w1:t2"))
        view = snap([new], workspaces={"w1": "Scratch"})
        view["tabs"]["w1:t2"].update(label="", number=1)
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=new), \
                mock.patch.object(herdr, "snapshot", return_value=view), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p2", restart=True))
        self.assertEqual(typed(run), [])
        self.assertIsNone(suspend.record("default", "w1:p2"))
        self.assertIn("claude:s1", store.load_archive()["entries"])

    def test_the_record_follows_its_tabs_renames(self):  # R93
        index, archive = {"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec(tab_label="auth")}}}}, \
            {"entries": {}}
        view = snap([pane("w1:p1", session=None, tab="w1:t1")], workspaces={"w1": "Work"})
        view["tabs"]["w1:t1"].update(label="auth v2", number=3)
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", view, "tab.renamed", {}, T0)
        rec = index["sessions"]["default"]["suspended"]["w1:p1"]
        self.assertEqual((rec["tab_label"], rec["tab_number"], rec["workspace_label"]), ("auth v2", 3, "Work"))
        self.assertTrue(suspend.same_tab("default", rec, pane("w1:p1", session=None, tab="w1:t1"), view))

    def test_a_sleep_during_the_wait_pushes_the_wake_up_back(self):  # R94
        cache = {"wake_from": T0 - 3600, "wake_slept": 100.0}
        with mock.patch.object(procs, "suspended_seconds", return_value=100.0 + 1800):
            self.assertEqual(suspend.pushed_back(cache, None, T0 - 600), 1800)
        with mock.patch.object(procs, "suspended_seconds", return_value=None):
            self.assertEqual(suspend.pushed_back(cache, [T0 - 3000, T0 - 1200], T0 - 600), 1800)

    def test_a_press_before_the_toast_never_confirms(self):  # R95
        suspend.remember_ask("default", "w1:p1", "d", T0 + 1.0)  # the toast went up at T0+1
        # the second press was at T0+0.3, its worker only got here at T0+2.1
        self.assertFalse(suspend.confirmed("default", "w1:p1", "d", T0 + 0.3))

    def test_a_stale_listing_elsewhere_keeps_the_record(self):  # R96
        rec = suspended_rec()
        suspended, entries = {"w1:p1": dict(rec)}, {}
        view = snap([pane("w1:p1", session=None), pane("w1:p2", session="s1", tab="w1:t2")])
        with mock.patch.object(agents, "claude_running", return_value=False):
            core.settle_suspended(suspended, entries, "default", view, T0, lambda n: n, flags={})
        self.assertIn("w1:p1", suspended)
        with mock.patch.object(agents, "claude_running", return_value=True):
            core.settle_suspended(suspended, entries, "default", view, T0, lambda n: n, flags={})
        self.assertNotIn("w1:p1", suspended)

    def test_a_stale_listing_in_its_own_pane_isnt_a_failed_stop(self):  # R96
        suspended = {"w1:p1": suspended_rec(state="stopping", at=T0)}
        view = snap([pane("w1:p1")])
        with mock.patch.object(agents, "claude_running", return_value=False):
            core.settle_suspended(suspended, {}, "default", view, T0 + suspend.STOP_STALE + 5, lambda n: n, flags={})
        self.assertIn("w1:p1", suspended)

    def test_an_unknown_folder_never_drops_the_record(self):  # R97
        rec = {"agent": "claude", "session_id": "s1", "state": "suspended", "at": T0, "config_dir": None}
        with mock.patch.object(suspend, "record", return_value=rec), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, exists=False)), \
                mock.patch.object(suspend, "drop_record") as drop, \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(placeholder, "Terminal", NoTerminalR5), \
                mock.patch.object(placeholder, "wait_for_key", return_value="hangup"), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            placeholder.main("default", "w1:p1")
        drop.assert_not_called()

    def test_a_config_problem_is_logged_once_and_shown_in_the_popup(self):  # R108
        self.settings('[suspend]\nwhen = "tme"\n')
        logs = []
        for k in range(2):
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=T0 + k), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True), \
                    mock.patch.object(suspend, "log", side_effect=logs.append):
                core.handle_event("pane.focused", {"data": {}}, env={})
        self.assertEqual(len([m for m in logs if "config.toml" in m]), 1)
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            popup = ui.Popup({"workspace_label": "Work"})
        self.assertIn("config.toml", popup.message)

    def test_marks_of_closed_tabs_are_forgotten(self):  # R110
        index, archive = {"sessions": {"default": {"panes": {}, "suspended": {}, "marked": {"w1:t7": "💤"}}}}, {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p1")]), "tab.closed", {}, T0)
        self.assertEqual(index["sessions"]["default"]["marked"], {})

    def test_a_late_answer_goes_by_toast_if_herdr_shows_it(self):  # R111
        with mock.patch.object(herdr, "notify", return_value=True) as notify, \
                mock.patch.object(suspend.message, "show") as show:
            suspend.say(MANUAL, "T", "B", pressed=time.time() - 20)
            suspend.say(MANUAL, "T2", "B2", pressed=time.time())
        notify.assert_called_once_with("T", "B")
        show.assert_called_once_with("T2", "B2", focus=True)
        with mock.patch.object(herdr, "notify", return_value=False), \
                mock.patch.object(suspend.message, "show") as show:  # toasts off (Herdr's default): R118
            suspend.say(MANUAL, "T", "B", pressed=time.time() - 20)
        show.assert_called_once_with("T", "B", focus=False)  # seen, without taking the keyboard

    def test_hooks_rearm_missing_placeholders_outside_the_automatic_modes(self):  # R101
        self.settings('[suspend]\nwhen = "manual"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=T0), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True) as spawn:
            core.handle_event("pane.focused", {"data": {}}, env={})
        spawn.assert_called_once_with(["--rearm-pass"])
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(suspend, "rearm_pass") as rp:
            suspend.worker("default", MANUAL, rearm_pass_only=True)
        rp.assert_called_once()

    def test_a_restart_ignores_the_backoff(self):  # R101
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec(
            arm_failed=time.time())}}}})
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(herdr, "run") as run:
            suspend.arm("default", "w1:p1", restart=True)
        self.assertTrue(typed(run))

    def test_settle_now_reads_no_archive_with_nothing_suspended(self):  # R113
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        with mock.patch.object(store, "load_archive") as load:
            core.settle_now("default", snap([]), T0)
        load.assert_not_called()

    def test_herdrs_default_restore_delay_counts(self):  # R113
        with mock.patch.object(herdr, "setting", return_value=None):
            self.assertEqual(core.boot_grace_for(400), 30 + 40)


class NoTerminalR5:
    def __init__(self, fd):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class R5FlowTests(SuspendPaneTests):
    def kills(self):
        return [e for e in self.events if e[0] == "kill"]

    def test_an_agent_gone_before_the_signal_exited_on_its_own(self):  # R98
        # The user quit it between the look and the last look: no process.
        with mock.patch.object(suspend.procs, "start_token", return_value=None), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG_TIME, "time", manual=False)
        self.assertIn("exited on its own", why)
        self.assertEqual(self.kills(), [])
        self.assertIsNone(suspend.record("default", "w1:p1"))
        self.assertEqual(store.load_archive()["entries"]["claude:s1"]["reason"], "exited")

    def test_no_automatic_stop_when_nothing_is_in_focus(self):  # R99
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1")], view=False)), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG_TIME, "time", manual=False)
        self.assertIn("can't tell which tab is in view", why)
        self.assertEqual(self.kills(), [])

    def test_herdr_still_listing_it_is_remembered(self):  # R100
        with mock.patch.object(suspend, "wait_released", return_value=False), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True), suspend.NOT_YET)
        self.assertTrue(suspend.record("default", "w1:p1")["herdr_listed"])

    def test_text_typed_meanwhile_stops_it(self):  # R102
        screens = [self.screen, __import__("test_suspend").claude_screen("wait, one more thing")]
        with mock.patch.object(suspend.herdr, "read_screen", side_effect=lambda p, **k: screens.pop(0) if len(screens) > 1 else screens[0]), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("unsent text", why)
        self.assertEqual(self.kills(), [])

    def test_a_short_unsent_reply_counts(self):  # R107
        self.screen = __import__("test_suspend").claude_screen("y")
        with mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertIn("unsent text", suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True))
        self.assertEqual(self.kills(), [])


class R5TimerTests(unittest.TestCase):
    def test_a_transcript_rewritten_to_the_same_size_is_read_again(self):  # R102
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            plain = json.dumps({"type": "user", "pad": "x" * 200}) + "\n"
            with open(path, "w") as f:
                f.write(plain * 3)
            cache = {}
            agents.claude_timers(path, 0, cache, T0)
            call = json.dumps({"type": "assistant", "timestamp": "2027-01-15T08:00:00Z", "message": {"content": [
                {"type": "tool_use", "id": "t", "name": "CronCreate", "input": {}}]}}) + "\n"
            with open(path, "w") as f:
                f.write(call + plain * 3)  # rewritten, now longer and different from the start
            self.assertEqual(agents.claude_timers(path, 0, cache, T0)[1], 1)

    def test_a_transcript_cut_shorter_with_the_same_start_is_read_again(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            first = json.dumps({"type": "user", "pad": "h" * 400}) + "\n"  # the same first 256 bytes
            with open(path, "w") as f:
                f.write(first + (json.dumps({"type": "user", "pad": "x" * 200}) + "\n") * 10)
            cache = {}
            agents.claude_timers(path, 0, cache, T0)
            call = json.dumps({"type": "assistant", "timestamp": "2027-01-15T08:00:00Z", "message": {"content": [
                {"type": "tool_use", "id": "t", "name": "CronCreate", "input": {}}]}}) + "\n"
            with open(path, "w") as f:
                f.write(first + call)  # rewritten shorter
            self.assertEqual(agents.claude_timers(path, 0, cache, T0)[1], 1)

    def test_the_missing_record_doubt_names_remote_control(self):  # R102
        src = open(suspend.__file__).read()
        self.assertIn("or has Remote Control on", src)


# ------------------------------------------- round 5 reviewers' survivors

class FakeScr:
    """A curses window that records what's drawn."""
    def __init__(self, h, w):
        self.h, self.w, self.texts = h, w, []

    def getmaxyx(self):
        return (self.h, self.w)

    def addstr(self, y, x, text, attr=0):
        self.texts.append(text)

    def __getattr__(self, name):
        return lambda *a, **k: None


class R5SurvivorTests(StateDir):
    def test_the_lock_is_exclusive(self):
        import fcntl
        with store.locked():
            with open(os.path.join(store.state_dir(), ".lock"), "r+") as f:
                with self.assertRaises(OSError):
                    fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)

    def test_the_default_state_folder_is_private(self):
        home = os.path.join(self.dir.name, "home")
        env = {k: v for k, v in os.environ.items() if k not in ("HERDR_PLUGIN_STATE_DIR", "XDG_STATE_HOME")}
        env["HOME"] = home
        with mock.patch.dict(os.environ, env, clear=True):
            path = store.state_dir()
        self.assertTrue(path.startswith(home))
        self.assertEqual(os.stat(path).st_mode & 0o077, 0)

    def test_closed_workspaces_age_in_days(self):
        archive = {"entries": {}, "workspaces": {"k": {"key": "k", "closed_at": T0 - 5 * 86400, "tabs": []}}}
        core.prune(archive, dict(config.DEFAULTS, keep_days=30), T0)
        self.assertIn("k", archive["workspaces"])

    def test_an_empty_workspace_isnt_recorded(self):
        archive = {"entries": {}}
        self.assertFalse(core.record_closed_workspace(archive, "default", "w1", {"label": "W", "tabs": []}, T0))
        self.assertFalse(archive.get("workspaces"))

    def test_the_leader_is_the_foreground_groups_leader(self):
        info = {"shell_pid": 10, "foreground_process_group_id": 50, "foreground_processes": [
            {"pid": 70, "name": "tee", "argv": ["tee"]}, {"pid": 50, "name": "pi", "argv": ["pi"]}]}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            f = suspend.look(pane("w1:p1", agent="pi"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "pi", "pi"),
                                                                          70: (50, "tee", "tee")}), T0, {})
        self.assertEqual((f["pid"], f["leader_name"]), (50, "pi"))

    def test_rearm_all_ends_when_nothing_is_left(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        with mock.patch.object(suspend.time, "sleep") as sleep:
            suspend.rearm_all("default")
        sleep.assert_not_called()

    def test_its_own_pane_isnt_elsewhere(self):
        rec = suspended_rec(agent="codex", session_id="019abc")
        view = snap([pane("w1:p1", agent="codex", session="019abc")])  # Herdr still lists it here
        self.assertFalse(suspend._open_elsewhere(rec, "w1:p1", view))
        view = snap([pane("w1:p1", session=None), pane("w1:p2", agent="codex", session="019abc", tab="w1:t2")])
        self.assertTrue(suspend._open_elsewhere(rec, "w1:p1", view))

    def popup(self, n=3, view="sessions"):
        entries = {f"claude:s{i}": {"herdr_session": "default", "workspace_label": "Work" if i < 2 else "Other",
                                    "agent": "claude", "session_id": f"s{i}", "last_active": T0 - i, "closed_at": T0,
                                    "tab_label": f"t{i}"} for i in range(n)}
        store.save_archive({"entries": entries, "workspaces": {"wk": {
            "key": "wk", "herdr_session": "default", "label": "Gone", "closed_at": T0,
            "tabs": [{"label": "auth tab", "agent": "claude", "session_id": "x"}]}}})
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            p = ui.Popup({"workspace_label": "Work"})
            if view == "workspaces":
                p.switch("workspaces")
        return p

    def test_popup_keys(self):
        p = self.popup(25)
        p.filtering, p.filter = True, "x"
        p.on_key("\x1b")
        self.assertEqual(p.filter, "")  # Esc while filtering clears it
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            p.on_key("a")
            self.assertTrue(p.all)
            p.on_key("a")
            self.assertFalse(p.all)  # a toggles
            p.on_key("a")
        p.sel = 0
        p.on_key(ui.curses.KEY_NPAGE)
        self.assertEqual(p.sel, 10)

    def test_the_popup_draws_its_guard_and_its_forget_marks(self):
        p = self.popup(3)
        with mock.patch.object(ui.curses, "ACS_HLINE", 0, create=True), \
                mock.patch.object(ui.curses, "color_pair", return_value=0, create=True):
            small = FakeScr(4, 80)
            p.draw(small)
            self.assertTrue(any("bigger" in t for t in small.texts))
            big = FakeScr(20, 80)
            p.draw(big)
        self.assertTrue(any(t == " ×" for t in big.texts))

    def test_the_workspaces_view_forgets_workspaces_and_filters_by_tab_name(self):
        p = self.popup(3, view="workspaces")
        p.filter = "auth"
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            p.load()
        self.assertEqual([r["key"] for r in p.rows], ["wk"])
        with mock.patch.object(core, "forget_workspace") as fw, mock.patch.object(core, "forget") as fs:
            p.do_forget("wk")
        fw.assert_called_once_with("wk")
        fs.assert_not_called()

    def test_the_popup_prunes_once(self):  # R113
        p = self.popup(3)
        with mock.patch.object(core, "prune", return_value=False) as prune, \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            p.load()
            p.load()
        prune.assert_not_called()  # already pruned when it opened

    def test_the_message_popup_takes_focus(self):
        with mock.patch.object(herdr, "run") as run:
            message.show("T", "B")
        self.assertIn("--focus", run.call_args.args)

    def test_a_question_waits_its_own_time(self):
        reads = []
        with mock.patch.dict(os.environ, {message.ENV: json.dumps({"title": "Q", "ask": {"session": "s", "pane_id": "p",
                                                                                         "why": "d"}})}), \
                mock.patch.object(message.os, "isatty", return_value=True), \
                mock.patch.object(message.termios, "tcgetattr", return_value=[]), \
                mock.patch.object(message.termios, "tcsetattr"), mock.patch.object(message.termios, "tcflush"), \
                mock.patch.object(message.tty, "setraw"), mock.patch.object(message, "KEY_DELAY", 0), \
                mock.patch.object(message, "draw"), \
                mock.patch.object(message, "read_key", side_effect=lambda fd, t: reads.append(t) or b""), \
                mock.patch.object(message.sys, "stdout", io.StringIO()):
            message.main()
        self.assertAlmostEqual(reads[0], message.ASK_WAIT, delta=0.5)

    def test_procs_names_with_a_paren(self):
        d = os.path.join(self.dir.name, "bin")
        os.makedirs(d)
        link = os.path.join(d, "odd) name")
        os.symlink("/bin/sleep", link)
        import subprocess
        child = subprocess.Popen([link, "5"])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        time.sleep(0.2)
        self.assertEqual(procs.Table().procs[child.pid][1], "odd) name")

    def test_macos_names_are_the_programs_name(self):
        def ps(*cols):
            return ["  50     1 /usr/local/bin/claude"] if "comm" in cols else ["  50 claude --resume x"]
        with mock.patch.object(procs, "linux", return_value=False), mock.patch.object(procs, "_ps", side_effect=ps):
            self.assertEqual(procs.Table().procs[50][1], "claude")

    def test_transcript_rules(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                for _ in range(20):
                    f.write(json.dumps({"type": "system", "x": 1}) + "\n")
            self.assertTrue(agents.claude_has_content(path, max_lines=10))  # long: a real conversation
        self.assertTrue(agents._is_rule("────────"))
        self.assertTrue(agents._is_rule("─"))
        self.assertFalse(agents._is_rule("─ not a rule"))
        self.assertIsNone(agents._real_prompt({"type": "user", "isMeta": True, "message": {"content": "caveat"}}))

    def test_the_newest_codex_database(self):
        home = os.environ["CODEX_HOME"]
        for n in (5, 7):
            open(os.path.join(home, f"state_{n}.sqlite"), "w").close()
        self.addCleanup(lambda: [os.unlink(os.path.join(home, f"state_{n}.sqlite")) for n in (5, 7)])
        self.assertTrue(agents._codex_db().endswith("state_7.sqlite"))

    def test_the_debug_log_only_when_asked(self):
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(core, "send_reports"), mock.patch.object(suspend, "spawn_worker", return_value=True), \
                mock.patch.object(store, "debug_log") as dbg:
            core.handle_event("pane.focused", {"data": {}}, env={})
        dbg.assert_not_called()

    def test_a_login_shell_is_a_shell(self):
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            f = suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "-bash", "-bash"), 50: (10, "claude", "claude")}),
                             T0, {})
        self.assertNotIn("can't run", f.get("why", ""))

    def test_screen_copies_per_session_and_a_private_worker_log(self):
        self.assertNotEqual(suspend.screen_path("a", "w1:p1"), suspend.screen_path("b", "w1:p1"))
        with mock.patch.object(suspend.subprocess, "Popen"):
            suspend.spawn_worker([])
        self.assertEqual(os.stat(os.path.join(store.state_dir(), "worker.log")).st_mode & 0o077, 0)

    def test_c1_controls_are_cleaned(self):
        from earmark import text
        self.assertEqual(text.clean("a\x9bb"), "a b")

    def test_the_title_is_cleaned(self):
        rec = {"agent": "claude", "tab_label": "evil\x1b]0;x\x07name", "at": T0}
        out = io.StringIO()
        with mock.patch.object(placeholder.select, "select", side_effect=lambda r, w, x, t: ([r[0]], [], [])), \
                mock.patch.object(placeholder.os, "read", return_value=b"\r"), \
                mock.patch.object(placeholder.os, "get_terminal_size", return_value=os.terminal_size((80, 24))), \
                mock.patch.object(placeholder.signal, "set_wakeup_fd", return_value=-1), \
                mock.patch.object(sys, "stdout", out):
            placeholder.wait_for_key(rec, CFG, "", 0)
        title = out.getvalue().split("\x1b]2;", 1)[1].split("\x07", 1)[0]
        self.assertNotIn("\x1b", title)

    def test_the_notice_shows_both_names(self):
        rec = {"agent": "claude", "tab_label": "auth", "title": "Fix the login", "at": T0}
        cfg = dict(CFG, suspend=dict(CFG["suspend"], show="notice"))
        rows = [agents.plain(r) for r in placeholder.compose(rec, cfg, "", 20, 80, T0)]
        self.assertTrue(any("Fix the login" in r for r in rows) and any("auth" in r for r in rows))


class R5EntryTests(unittest.TestCase):
    def cli(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "earmark_cli", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "earmark.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_the_worker_takes_its_arguments(self):
        cli = self.cli()
        with mock.patch.object(sys, "argv", ["earmark.py", "worker", "--rearm", "--pane", "w1:p1", "--accept", "d",
                                             "--pressed", "12.5"]), \
                mock.patch.object(suspend, "worker") as worker, mock.patch.object(herdr, "session_name", return_value="s"):
            cli.cmd_worker()
        kw = worker.call_args.kwargs
        self.assertEqual((kw["rearm"], kw["accept"], kw["pane_id"], kw["pressed"]), (True, "d", "w1:p1", 12.5))

    def test_a_hook_without_an_event_is_the_startup_hook(self):
        cli = self.cli()
        env = {k: v for k, v in os.environ.items() if k != "HERDR_PLUGIN_EVENT"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(core, "handle_event") as he:
            cli.cmd_hook()
        self.assertEqual(he.call_args.args[0], "startup")

    def test_shift_a_opens_the_workspaces_view(self):
        cli = self.cli()
        with mock.patch.object(herdr, "run") as run:
            cli.cmd_open_workspaces()
        self.assertIn("EARMARK_VIEW=workspaces", run.call_args.args)


class R5OwnSurvivorTests(StateDir):
    def recreated(self, **diff):
        rec = suspended_rec(pane_id="w1:p2", tab_id="w1:t2", tab_label="auth", tab_number=2, workspace_label="Work")
        view = snap([pane("w1:p2", session=None, tab="w1:t2")], workspaces={"w1": diff.get("ws", "Work")})
        view["tabs"]["w1:t2"].update(label=diff.get("label", "auth"), number=diff.get("number", 2))
        return suspend.same_tab("default", rec, pane("w1:p2", session=None, tab="w1:t2"), view)

    def test_each_part_of_a_tabs_identity_counts(self):  # R93
        self.assertTrue(self.recreated())
        self.assertFalse(self.recreated(label="other"))
        self.assertFalse(self.recreated(number=1))
        self.assertFalse(self.recreated(ws="Scratch"))

    def test_the_sleep_baseline_is_read_with_the_call(self):  # R94
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "assistant", "timestamp": "2027-01-15T08:00:00Z", "message": {"content": [
                    {"type": "tool_use", "name": "ScheduleWakeup", "input": {"delaySeconds": 1800}}]}}) + "\n")
            cache = {}
            with mock.patch.object(procs, "suspended_seconds", return_value=42.0):
                agents.claude_timers(path, 0, cache, T0)
        self.assertEqual(cache["wake_slept"], 42.0)

    def test_the_keys_look_knows_the_absences(self):  # R94
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1"}}, "suspended": {},
                                                   "away": [T0 - 600, T0 - 60]}}})
        seen = {}

        def look(p, note, table, t, timers):
            seen.update(timers)
            return found(T0 - 7200, why="stop here")
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "look", side_effect=look), mock.patch.object(core, "settle_now"):
            suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertEqual(seen["_away"], [T0 - 600, T0 - 60])

    def test_auto_skips_a_check_when_nothing_is_in_focus(self):  # R99
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1", "since": time.time() - 7200}},
                                                   "suspended": {}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")], view=False)), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_not_called()

    def test_a_screen_herdr_didnt_show_isnt_an_idle_shell(self):  # R113 (the screen decides since review 7)
        # No baseline yet, and Herdr doesn't answer the screen read: nothing to compare, nothing typed.
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec(base=None)}}}})
        bare = pane("w1:p1", session=None, tab="w1:t1")
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", return_value=snap([bare])), \
                mock.patch.object(suspend, "screen_print", return_value=None), \
                mock.patch.object(herdr, "run") as run:
            for _ in range(3):
                suspend.rearm_pass("default", snap([bare]))
        self.assertEqual(typed(run), [])

    def test_a_wake_up_slept_through_keeps_it_awake_through_look(self):  # r5-safety
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}

        def timers(path, since, cache, now):
            cache.update(wake_from=T0 - 3600, wake_slept=None)
            return T0 - 600, 0  # due 10 min ago by the wall clock
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "started_at", return_value=None), \
                mock.patch.object(procs, "suspended_seconds", return_value=None), \
                mock.patch.object(agents, "claude_activity", return_value=0), \
                mock.patch.object(agents, "claude_registry", return_value={"status": "idle"}), \
                mock.patch.object(agents, "claude_timers", side_effect=timers), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source="/t.jsonl")):
            f = suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}),
                             T0, {"_away": [T0 - 3000, T0 - 1200]})  # the machine slept 30 min during the wait
        self.assertIn("/loop", f["timers"])

    def test_a_listing_without_the_agent_isnt_a_failed_stop(self):  # r5-safety
        listed = dict(pane("w1:p1"), agent=None)  # Herdr shows the session but no agent running
        suspended = {"w1:p1": suspended_rec(state="stopping", at=T0)}
        with mock.patch.object(agents, "claude_running", return_value=True):
            core.settle_suspended(suspended, {}, "default", snap([listed]), T0 + suspend.STOP_STALE + 5,
                                  lambda n: n, flags={})
        self.assertIn("w1:p1", suspended)


class R5OwnFlowTests(SuspendPaneTests):
    def test_the_press_time_decides_in_toast_mode(self):  # R95
        self.screen = "some output\n$ "
        toast = dict(CFG, suspend=dict(CFG["suspend"], when="manual", messages="toast"))
        suspend.remember_ask("default", "w1:p1", "Earmark can't read its prompt to check for unsent text", T0 + 1.0)
        with mock.patch.object(suspend.herdr, "setting", return_value="herdr"), \
                mock.patch.object(suspend.herdr, "notify", return_value=True), \
                mock.patch.object(suspend.message, "show"), \
                mock.patch.object(suspend.time, "time", return_value=T0 + 2.1):
            suspend.manual("default", "w1:p1", toast, pressed=T0 + 0.3)  # pressed before the toast went up
        self.assertEqual([e for e in self.events if e[0] == "kill"], [])

    def test_the_first_read_refuses_a_short_draft(self):  # r5-fit short drafts
        self.screen = __import__("test_suspend").claude_screen("ok")
        with mock.patch.object(suspend.herdr, "read_screen", return_value=self.screen) as read, \
                mock.patch.object(suspend.time, "time", return_value=T0):
            suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertEqual(read.call_count, 1)  # refused before any record or last look


class R5PopupDelayTests(unittest.TestCase):
    def test_keys_in_the_questions_first_moment_dont_answer(self):  # R102
        import termios
        import tty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        tty.setraw(slave, termios.TCSANOW)
        draw = message.draw

        def draw_then_type(*args):
            draw(*args)
            os.write(master, b"y\r")  # at once, as the question appears
        stdin = mock.Mock()
        stdin.fileno.return_value = slave
        with mock.patch.object(message, "draw", side_effect=draw_then_type), \
                mock.patch.dict(os.environ, {message.ENV: json.dumps({"title": "Q", "ask": {
                    "session": "s", "pane_id": "p", "why": "d"}})}), \
                mock.patch.object(message.sys, "stdin", stdin), \
                mock.patch.object(message.sys, "stdout", io.StringIO()), \
                mock.patch.object(message, "ASK_WAIT", 0.2), mock.patch.object(message, "KEY_DELAY", 0.1), \
                mock.patch.object(suspend, "spawn_worker") as spawn, mock.patch.object(suspend, "confirm") as confirm:
            message.main()
        spawn.assert_not_called()
        confirm.assert_not_called()


# ------------------------------------------------------------------ round 6

class R6Tests(StateDir):
    RULE = "─" * 30

    def draft(self, styled):
        return agents.draft_text("\n".join([self.RULE, "❯ " + styled, self.RULE]), "claude")

    def test_typed_text_in_an_extended_colour_is_a_draft(self):  # R114
        for codes in ("38;5;3", "38;5;2", "38;2;10;20;3", "38;2;10;20;2", "48;5;3", "38:5:3", "38:2::1:2:3"):
            self.assertEqual(self.draft(f"\x1b[{codes}mfix the parser\x1b[0m"), "fix the parser", codes)
        self.assertEqual(self.draft("\x1b[2mTry this\x1b[mtyped"), "typed")  # an empty parameter resets
        self.assertEqual(self.draft("\x1b[2;38;5;3mhint\x1b[0m"), "")  # faint in a colour is still a hint

    def test_a_long_transcript_is_read_in_one_look(self):  # R115
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                for _ in range(50):
                    f.write(json.dumps({"type": "user", "pad": "x" * 300}) + "\n")
            timers = {}
            with mock.patch.object(agents, "TIMER_READ", 1000), \
                    mock.patch.object(herdr, "process_info", return_value=info), \
                    mock.patch.object(procs, "start_token", return_value="L"), \
                    mock.patch.object(procs, "environ_var", return_value=""), \
                    mock.patch.object(procs, "started_at", return_value=None), \
                    mock.patch.object(agents, "claude_activity", return_value=0), \
                    mock.patch.object(agents, "claude_registry", return_value={"status": "idle"}), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source=path)):
                f = suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}),
                                 T0, timers)
        self.assertEqual(f["timers"], "")  # not "hasn't read its whole transcript yet"

    def test_the_parent_pid_fallback_expires(self):  # R116
        index, archive = {"sessions": {"default": {"panes": {}, "server_pid": 100, "ppid_unreliable": T0}}}, {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([]), "pane.focused", {}, T0 + 3600, server_pid=101)
            self.assertNotIn("boot", index["sessions"]["default"])  # still off after an hour
            core.apply(index, archive, "default", snap([]), "pane.focused", {}, T0 + 7 * 3600, server_pid=102)
        self.assertEqual(index["sessions"]["default"]["boot"], T0 + 7 * 3600)  # counts again after six

    def test_a_popup_can_open_without_focus(self):  # R118
        with mock.patch.object(herdr, "run") as run:
            message.show("T", "B", focus=False)
        self.assertIn("--no-focus", run.call_args.args)
        with mock.patch.object(herdr, "run") as run:
            message.show("T", "B", ask={"session": "s", "pane_id": "p", "why": "w"}, focus=False)
        self.assertIn("--focus", run.call_args.args)  # a question always takes it

    def test_memory_mode_starts_no_worker_while_memory_is_fine(self):  # R119
        self.settings('[suspend]\nwhen = "memory"\nmemory_below = 20\n')
        for avail, spawned in ((60.0, False), (10.0, True)):
            store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=T0), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(procs, "available_percent", return_value=avail), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True) as spawn:
                core.handle_event("pane.focused", {"data": {}}, env={})
            self.assertEqual(spawn.called, spawned, avail)

    def test_the_placeholder_redraws_only_when_its_text_changes(self):  # R119
        clock = iter([T0 + 60 * k for k in range(10)])
        writes = []
        out = mock.Mock(write=lambda s: writes.append(s), flush=lambda: None)
        selects = iter([([], [], []), ([], [], [])])

        def fake_select(r, w, x, t):
            try:
                return next(selects)
            except StopIteration:
                return ([r[0]], [], [])
        with mock.patch.object(placeholder.select, "select", side_effect=fake_select), \
                mock.patch.object(placeholder.os, "read", return_value=b"\r"), \
                mock.patch.object(placeholder.os, "get_terminal_size", return_value=os.terminal_size((80, 24))), \
                mock.patch.object(placeholder.signal, "set_wakeup_fd", return_value=-1), \
                mock.patch.object(placeholder.time, "time", side_effect=lambda: next(clock, T0 + 600)), \
                mock.patch.object(placeholder, "compose", return_value=["same", "rows"]), \
                mock.patch.object(sys, "stdout", out):
            placeholder.wait_for_key({"agent": "claude", "at": T0}, CFG, "", 0)
        self.assertEqual(len([w for w in writes if w.startswith("\x1b[H\x1b[2J")]), 1)

    def test_the_popup_wraps_by_columns(self):  # R120
        rows = message.wrap_cols("一二三四五六七八 九十", 6)
        self.assertTrue(all(__import__("earmark").text.cols(r) <= 6 for r in rows), rows)
        self.assertEqual(message.wrap_cols("one two three", 7), ["one two", "three"])


class R6SurvivorTests(StateDir):
    def test_pruning_only_at_startup(self):
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(core, "send_reports"), mock.patch.object(suspend, "spawn_worker", return_value=True), \
                mock.patch.object(core, "prune", return_value=False) as prune:
            core.handle_event("pane.focused", {"data": {}}, env={})
            prune.assert_not_called()
            core.handle_event("startup", {"data": {}}, env={})
        prune.assert_called_once()

    def test_renames_and_closed_workspaces_stay_in_their_herdr_session(self):
        index = {"sessions": {"default": {"panes": {}, "workspaces": {"w1": "Old"}}}}
        archive = {"entries": {
            "claude:a": {"herdr_session": "default", "workspace_id": "w1", "workspace_label": "Old", "agent": "claude",
                         "session_id": "a"},
            "claude:b": {"herdr_session": "work", "workspace_id": "w1", "workspace_label": "Old", "agent": "claude",
                         "session_id": "b"}},
            "workspaces": {"k1": {"key": "k1", "herdr_session": "default", "label": "X", "closed_at": T0, "tabs": [{}]},
                           "k2": {"key": "k2", "herdr_session": "work", "label": "Y", "closed_at": T0, "tabs": [{}]}}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([], workspaces={"w1": "New"}), "workspace.renamed", {}, T0)
        self.assertEqual(archive["entries"]["claude:a"]["workspace_label"], "New")
        self.assertEqual(archive["entries"]["claude:b"]["workspace_label"], "Old")
        self.assertEqual([w["key"] for w in core.closed_workspaces(archive, "default")], ["k1"])

    def test_resume_on_view_waits_its_dwell(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        with mock.patch.object(suspend.time, "sleep") as sleep, \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None, focused=False)), \
                mock.patch.object(suspend, "press_enter") as enter:
            suspend.wake_on_view("default", "w1:p1")
        sleep.assert_called_once_with(suspend.WAKE_DWELL)
        enter.assert_not_called()  # passed through: left before the dwell was up

    def test_the_placeholder_shows_the_cursor_again_and_keeps_faint_after_bold(self):
        self.assertIn("\x1b[?25h", placeholder.LEAVE_SCREEN)
        line = placeholder.dimmed("a\x1b[1mb\x1b[22mc")
        self.assertIn("\x1b[22m" + placeholder.DIM + "c", line)

    def test_combining_marks_take_no_column(self):
        from earmark import text
        self.assertEqual(text.char_cols("\u0301"), 0)
        self.assertEqual(text.cols("e\u0301"), 1)

    def test_a_colon_style_inside_a_hint_keeps_it_a_hint(self):  # R114
        rule = "─" * 30
        screen = "\n".join([rule, "❯ \x1b[2;4:3mTry this\x1b[0m", rule])
        self.assertEqual(agents.draft_text(screen, "claude"), "")

    def test_a_half_written_last_line_ends_the_catch_up(self):  # R115
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "user", "pad": "x" * 100}) + "\n" + '{"type": "assistant", "half')
            calls = []
            real = agents.claude_timers

            def counted(*a, **k):
                calls.append(1)
                return real(*a, **k)
            with mock.patch.object(suspend, "READ_BUDGET", 30), \
                    mock.patch.object(agents, "claude_timers", side_effect=counted), \
                    mock.patch.object(herdr, "process_info", return_value=info), \
                    mock.patch.object(procs, "start_token", return_value="L"), \
                    mock.patch.object(procs, "environ_var", return_value=""), \
                    mock.patch.object(procs, "started_at", return_value=None), \
                    mock.patch.object(agents, "claude_activity", return_value=0), \
                    mock.patch.object(agents, "claude_registry", return_value={"status": "idle"}), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source=path)):
                suspend.look(pane("w1:p1"), {}, procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}),
                             T0, {})
        self.assertLessEqual(len(calls), 3)


class R6StopWaitTests(SuspendPaneTests):
    def test_an_agent_a_few_seconds_slow_to_exit_is_waited_for(self):
        now = [T0]

        def clock():
            now[0] += 0.25
            return now[0]
        self.exits = False  # it doesn't exit at once...

        def token(pid):  # ...but five seconds after the signal
            if any(e[0] == "kill" for e in self.events) and now[0] > self.signalled_at + 5:
                self.stopped = True  # its shell is back too
                return None
            return "L"
        orig = self.fake_kill

        def kill(pid, sig):
            self.signalled_at = now[0]
            orig(pid, sig)
        with mock.patch.object(suspend.time, "time", side_effect=clock), \
                mock.patch.object(suspend.procs, "start_token", side_effect=token), \
                mock.patch.object(suspend.os, "kill", side_effect=kill):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertNotIn("didn't stop", why)


# ------------------------------------------------- round 6 (safety fixes)

class R6SafetyTests(StateDir):
    def test_durable_tasks_keep_it_awake(self):  # R125
        proj = os.path.join(self.dir.name, "proj")
        os.makedirs(os.path.join(proj, ".claude"))
        path = os.path.join(proj, ".claude", "scheduled_tasks.json")
        self.assertEqual(agents.durable_tasks(proj), 0)
        with open(path, "w") as f:
            json.dump([{"id": "j1", "cron": "0 9 * * *"}], f)
        self.assertEqual(agents.durable_tasks(proj), 1)
        with open(path, "w") as f:
            f.write("{ not json")
        self.assertIsNone(agents.durable_tasks(proj))  # can't read: counted as some
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with open(path, "w") as f:
            json.dump({"tasks": [{"id": "j1"}]}, f)
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "started_at", return_value=None), \
                mock.patch.object(agents, "claude_activity", return_value=0), \
                mock.patch.object(agents, "claude_registry", return_value={"status": "idle"}), \
                mock.patch.object(agents, "claude_timers", return_value=(0, 0)), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source="/t.jsonl")):
            f = suspend.look(dict(pane("w1:p1"), foreground_cwd=proj), {},
                             procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}), T0, {})
        self.assertIn("outlive", f["timers"])

    def test_the_shells_folder_is_part_of_the_tab(self):  # R126
        rec = suspended_rec(tab_label="", tab_number=1, workspace_label="proj", shell_cwd="/home/u/proj")
        view = snap([dict(pane("w1:p1", session=None, tab="w1:t1"), cwd="/home/u/other")], workspaces={"w1": "proj"})
        view["tabs"]["w1:t1"].update(label="", number=1)
        self.assertFalse(suspend.same_tab("default", rec, view["panes"]["w1:p1"], view))
        view["panes"]["w1:p1"]["cwd"] = "/home/u/proj"
        self.assertTrue(suspend.same_tab("default", rec, view["panes"]["w1:p1"], view))

    def test_a_restart_that_brings_back_few_panes_is_a_new_session(self):  # R126
        index = {"sessions": {"default": {"server_pid": 100, "panes": {
            f"w1:p{i}": {"session_id": f"n{i}", "pane_id": f"w1:p{i}", "agent": "claude", "since": T0 - 900}
            for i in range(2, 6)}, "suspended": {"w1:p1": suspended_rec()}}}}
        archive = {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "startup", {}, T0)
        self.assertEqual(index["sessions"]["default"]["suspended"], {})
        self.assertEqual(archive["entries"]["claude:s1"]["reason"], "closed")

    def test_an_ordinary_restart_keeps_its_suspended_tabs(self):  # R126
        index = {"sessions": {"default": {"server_pid": 100, "panes": {
            "w1:p2": {"session_id": "n2", "pane_id": "w1:p2", "agent": "claude", "since": T0 - 900}},
            "suspended": {"w1:p1": suspended_rec()}}}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, {"entries": {}}, "default", snap([pane("w1:p1", session=None), pane("w1:p2", session="n2",
                                                                                            tab="w1:t2")]),
                       "startup", {}, T0)
        self.assertIn("w1:p1", index["sessions"]["default"]["suspended"])

    def test_an_exit_inside_the_grace_is_archived_after_it(self):  # R129
        index, archive = {"sessions": {}}, {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0 - 600)
            core.apply(index, archive, "default", snap([pane("w1:p1")]), "startup", {}, T0)
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.agent_detected",
                       {"pane_id": "w1:p1", "released": True}, T0 + 10)  # inside the grace: ignored
            self.assertEqual(archive["entries"], {})
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.focused", {},
                       T0 + core.BOOT_GRACE + 5)
        self.assertEqual(archive["entries"]["claude:s1"]["reason"], "exited")

    def test_odd_herdr_replies_are_herdr_errors(self):  # R130
        for reply in (None, {}, {"panes": None}, "text"):
            with mock.patch.object(herdr, "run", return_value=reply):
                with self.assertRaises(herdr.HerdrError):
                    herdr.snapshot()
                with self.assertRaises(herdr.HerdrError):
                    herdr.pane("w1:p1")

    def test_no_focus_no_rearm(self):  # R131
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")], view=False)), \
                mock.patch.object(suspend, "rearm_pass") as rp, mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        rp.assert_not_called()

    def test_option_values_a_shell_would_expand_arent_kept(self):  # R134
        kept, unknown = agents.launch_flags("claude", ["claude", "--model", "=sonnet"])
        self.assertEqual(kept, [])
        self.assertTrue(unknown)

    def test_an_unknown_mode_never_keeps_a_bypass_permission_mode(self):  # R134
        self.assertEqual(agents.claude_resume_flags(["--permission-mode", "bypassPermissions"], ""),
                         ["--allow-dangerously-skip-permissions"])
        self.assertEqual(agents.claude_resume_flags(["--permission-mode=bypassPermissions", "--model", "m"], ""),
                         ["--allow-dangerously-skip-permissions", "--model", "m"])


class R6SafetyFlowTests(SuspendPaneTests):
    def kills(self):
        return [e for e in self.events if e[0] == "kill"]

    def test_an_unstyled_try_draft_is_asked_about(self):  # R124
        self.screen = "\n".join(["x", "─" * 20, '❯ Try "npm run build"', "─" * 20])
        with mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertIn("can't read its prompt", suspend.suspend_pane("default", "w1:p1", CFG_TIME, "time", manual=False))
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertTrue(why.startswith(suspend.CONFIRM))
        self.assertEqual(self.kills(), [])

    def test_the_last_look_sees_a_command_started_since(self):  # R132
        real_table = type(suspend.procs.Table.return_value)  # the fixture mocks the class itself
        busy = real_table({50: (1, "claude", "claude"), 70: (50, "bash", "bash -c make")})
        with mock.patch.object(suspend.procs, "Table", return_value=busy), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("started in it", why)
        self.assertEqual(self.kills(), [])

    def test_the_last_look_hears_claude_say_busy(self):  # R132
        with mock.patch.object(suspend.agents, "claude_registry", return_value={"status": "busy"}), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True)
        self.assertIn("busy", why)
        self.assertEqual(self.kills(), [])

    def test_settings_changed_while_looking_stop_the_check(self):  # R134
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        chosen = [(pane("w1:p1"), {}, found(T0 - 7200))]
        mtimes = iter([1, 2, 2, 2])
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(suspend, "choose", return_value=chosen), \
                mock.patch.object(suspend, "_mtime", side_effect=lambda p: next(mtimes, 2)), \
                mock.patch.object(suspend.config, "load", return_value=dict(CFG_TIME, suspend=dict(
                    CFG_TIME["suspend"], when="manual"))), \
                mock.patch.object(suspend, "suspend_pane") as act, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        act.assert_not_called()


class R6LastSurvivorTests(StateDir):
    def test_an_unreadable_durable_task_file_keeps_it_awake(self):  # R125
        proj = os.path.join(self.dir.name, "proj")
        os.makedirs(os.path.join(proj, ".claude"))
        with open(os.path.join(proj, ".claude", "scheduled_tasks.json"), "w") as f:
            f.write("{ not json")
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "started_at", return_value=None), \
                mock.patch.object(agents, "claude_activity", return_value=0), \
                mock.patch.object(agents, "claude_registry", return_value={"status": "idle"}), \
                mock.patch.object(agents, "claude_timers", return_value=(0, 0)), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, source="/t.jsonl")):
            f = suspend.look(dict(pane("w1:p1"), foreground_cwd=proj), {},
                             procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")}), T0, {})
        self.assertIn("outlive", f["timers"])

    def test_seen_since_the_restart_is_kept_current(self):
        suspended = {"w1:p1": suspended_rec(seen_at=T0 - 100)}
        core.settle_suspended(suspended, {}, "default", snap([pane("w1:p1", session=None)]), T0 + 5, lambda n: n,
                              flags={"boot": T0})
        self.assertEqual(suspended["w1:p1"]["seen_at"], T0 + 5)

    def test_no_tab_names_are_taken_on_during_the_restart_grace(self):  # R93's guard
        suspended = {"w1:p1": suspended_rec(tab_label="auth", tab_number=2, workspace_label="Work")}
        view = snap([pane("w1:p1", session=None, tab="w1:t1")], workspaces={"w1": "Scratch"})
        view["tabs"]["w1:t1"].update(label="new", number=1)
        core.settle_suspended(suspended, {}, "default", view, T0 + 5, lambda n: n, flags={"boot": T0})
        rec = suspended["w1:p1"]
        self.assertEqual((rec["tab_label"], rec["tab_number"], rec["workspace_label"]), ("auth", 2, "Work"))

    def test_arm_records_the_shells_folder(self):  # R126
        from test_suspend import ph_info
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": suspended_rec()}}}})
        infos = [shell_info(), shell_info(), ph_info()]
        bare = dict(pane("w1:p1", session=None), cwd="/home/u/proj")
        with mock.patch.object(herdr, "process_info", side_effect=lambda pid: infos.pop(0) if len(infos) > 1 else infos[0]), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "run"), \
                mock.patch.object(procs, "start_token", return_value="tok"):
            self.assertTrue(suspend.arm("default", "w1:p1", view_ok=True))
        self.assertEqual(suspend.record("default", "w1:p1")["shell_cwd"], "/home/u/proj")

    def test_an_error_reply_is_an_error(self):
        with mock.patch.object(herdr.subprocess, "run", return_value=mock.Mock(
                returncode=0, stdout=b'{"error": {"code": "pane_not_found", "message": "no pane"}}', stderr=b"")):
            with self.assertRaises(herdr.HerdrError):
                herdr.run("tab", "rename", "w1:t1", "x")


class R6LastFlowTests(SuspendPaneTests):
    def test_the_record_keeps_the_claude_folder(self):
        base = self.fake_look
        with mock.patch.object(suspend, "look", side_effect=lambda *a: dict(base(*a), config_dir="/home/u/.claude-alt")), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", MANUAL, "manual", manual=True), "")
        self.assertEqual(suspend.record("default", "w1:p1")["config_dir"], "/home/u/.claude-alt")

    def test_no_focus_at_the_last_look_stops_it(self):
        views = [snap([pane("w1:p1")]), snap([pane("w1:p1")], view=False)]
        with mock.patch.object(suspend.herdr, "snapshot", side_effect=lambda: views.pop(0) if len(views) > 1 else views[0]), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG_TIME, "time", manual=False)
        self.assertIn("view", why)
        self.assertEqual([e for e in self.events if e[0] == "kill"], [])


if __name__ == "__main__":
    unittest.main()
