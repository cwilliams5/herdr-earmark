"""Behaviour tests that run a whole sequence through the real code, rather
than one step with the steps around it mocked: a placeholder started, lost
and brought back; a hook deciding what to start; a popup driven by keys and
clicks; the command line into the worker; a workspace closed and restored.
A bug in how the steps fit together (two fixes undoing each other, a flag
the next step reads differently) only shows up here."""

import json
import os
import pty
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, herdr, message, placeholder, procs, store, suspend, ui  # noqa: E402
from test_suspend import CFG, T0, claude_screen, pane, ph_info, shell_info, snap, typed  # noqa: E402
from test_review1 import StateDir  # noqa: E402

FACTS = {"known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}


def record(**kw):
    rec = {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "workspace_label": "Work",
           "agent": "claude", "session_id": "s1", "state": "suspended", "at": T0 - 100, "cwd": "/proj",
           "resume": ["command", "claude", "--resume", "s1"]}
    rec.update(kw)
    return rec


class FakePane:
    """One pane's shell as Herdr and the process table see it: a bare shell
    until a line is typed, then the placeholder (pid 60) until it's killed.
    `text` is what it shows (typing changes it; Herdr's revision doesn't)."""

    def __init__(self):
        self.text, self.placeholder, self.lines = "[me@host proj]$ ", False, []
        self.alive = set()

    def pane(self, pid=None):
        return dict(pane("w1:p1", session=None, tab="w1:t1"), scroll={"viewport_rows": 24, "offset_from_bottom": 0})

    def screen(self, pid, rows=None, **kw):
        return self.text

    def snapshot(self):
        return snap([self.pane()])

    def info(self, pid=None):
        return ph_info() if self.placeholder else shell_info()

    def run(self, *args, **kw):
        if args[:2] == ("pane", "run"):
            self.lines.append(args[3])
            self.placeholder = True
            self.alive.add(60)
        return {}

    def start_token(self, pid):
        return f"tok{pid}" if pid in self.alive else None

    def kill_placeholder(self):
        """The placeholder dies outside a restart (the OOM killer, a crash);
        its exit puts the shell's screen back, with a new prompt."""
        self.placeholder = False
        self.alive.discard(60)
        self.text += "\n[me@host proj]$ "

    def patches(self, clock):
        return [mock.patch.object(herdr, "pane", side_effect=self.pane),
                mock.patch.object(herdr, "snapshot", side_effect=self.snapshot),
                mock.patch.object(herdr, "process_info", side_effect=self.info),
                mock.patch.object(herdr, "read_screen", side_effect=self.screen),
                mock.patch.object(herdr, "run", side_effect=self.run),
                mock.patch.object(procs, "start_token", side_effect=self.start_token),
                mock.patch.object(suspend.time, "time", side_effect=lambda: clock[0])]


class RearmFlowTests(StateDir):
    """A suspended tab's placeholder, from its first start to its return
    after a loss, through the real arm, untouched and rearm_pass."""
    real_screens = True

    def setUp(self):
        super().setUp()
        self.fake, self.clock = FakePane(), [T0]
        for p in self.fake.patches(self.clock):
            p.start()
            self.addCleanup(p.stop)

    def passes(self, n, gap=60):
        for _ in range(n):
            suspend.rearm_pass("default", self.fake.snapshot())
            self.clock[0] += gap

    def test_a_placeholder_lost_after_its_first_start_comes_back_by_itself(self):  # review 7 R135
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        self.assertTrue(suspend.arm("default", "w1:p1", just_stopped=True))  # right after Earmark's own stop
        self.assertEqual(len(self.fake.lines), 1)
        self.assertNotIn("base", suspend.record("default", "w1:p1"))  # seen up: no baseline left behind
        self.clock[0] += 3600
        self.fake.kill_placeholder()
        self.passes(2)  # first sight of the bare shell, then unchanged a check later
        self.assertEqual(len(self.fake.lines), 2)
        self.clock[0] += 3600
        self.fake.kill_placeholder()  # and again: every loss starts afresh
        self.passes(2)
        self.assertEqual(len(self.fake.lines), 3)

    def test_a_shell_used_after_the_loss_is_left_to_the_key(self):  # review 6 R127
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        self.passes(1)  # first sight
        shell = self.fake.text
        self.fake.text += "ls"  # someone typed into it
        self.passes(3)
        self.fake.text = shell  # and cleared the line again: still theirs
        self.passes(3)
        self.assertEqual(self.fake.lines, [])
        with mock.patch.object(suspend, "say"):
            suspend.manual("default", "w1:p1", {"suspend": {"when": "manual", "messages": "popup"}})
        self.assertEqual(len(self.fake.lines), 1)  # the key always may

    def test_after_a_restart_a_shell_still_starting_is_watched_again(self):  # review 7 R138
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        for text in ("", "[me@host", "[me@host proj]$ "):  # the new server's shell drawing its prompt
            self.fake.text = text
            self.assertFalse(suspend.arm("default", "w1:p1", restart=True))
            self.clock[0] += 1
        self.assertFalse(suspend.arm("default", "w1:p1", restart=True))  # unchanged, but not for long enough yet
        self.clock[0] += suspend.STABLE
        self.assertTrue(suspend.arm("default", "w1:p1", restart=True))
        self.assertEqual(len(self.fake.lines), 1)

    def test_a_shell_used_during_the_claim_isnt_typed_into(self):  # review 7 R138
        shell = self.fake.text
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record(
            base={"screen": suspend.screen_print(self.fake.pane()), "at": T0 - 600})}}}})
        texts = [shell, shell + "make"]  # unchanged at the look, typed into during the claim
        with mock.patch.object(herdr, "read_screen", side_effect=lambda p, **k: texts.pop(0) if texts else shell):
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertEqual(self.fake.lines, [])
        self.assertEqual(suspend.record("default", "w1:p1")["arming"], 0)  # the claim let go

    def test_what_sits_on_the_line_is_cancelled_before_typing(self):  # review 7 R137
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        with mock.patch.object(herdr, "run", side_effect=self.fake.run) as run:
            self.passes(2)
        calls = [c.args for c in run.call_args_list if c.args[:2] in (("pane", "send-keys"), ("pane", "run"))]
        self.assertEqual([c[3:] if c[1] == "send-keys" else "run" for c in calls],
                         [("ctrl+c",), ("ctrl+e", "ctrl+u"), "run"])


class ScreenTests(StateDir):
    """Review 7, found live: Herdr's pane revision moves with the folder and
    the title, not with typing, so `untouched` compares what the screen
    shows; and `pane read --source visible` follows the user's scroll
    position (R150), so screens are read from the bottom."""
    real_screens = True

    def test_a_scrolled_up_pane_is_read_from_the_bottom(self):
        p = dict(pane("w1:p1"), scroll={"viewport_rows": 37, "offset_from_bottom": 150, "max_offset_from_bottom": 300})
        with mock.patch.object(herdr, "read_screen", return_value="x") as read:
            suspend.screen_of(p)
        read.assert_called_once_with("w1:p1", rows=37)

    def test_the_fingerprint_follows_what_is_shown(self):
        texts = {"a": "[me@host proj]$ ", "b": "[me@host proj]$ ls", "c": "[me@host proj]$    \n"}
        prints = {}
        for k, v in texts.items():
            with mock.patch.object(herdr, "read_screen", return_value=v):
                prints[k] = suspend.screen_print(pane("w1:p1"))
        self.assertNotEqual(prints["a"], prints["b"])  # typing shows
        self.assertEqual(prints["a"], prints["c"])  # trailing blanks don't
        with mock.patch.object(herdr, "read_screen", side_effect=herdr.HerdrError("busy")):
            self.assertIsNone(suspend.screen_print(pane("w1:p1")))


class SuspendScreenTests(unittest.TestCase):
    """Both looks of a suspend (the first, and the last before the signal)
    read a scrolled-up pane from the bottom (review 7 R150)."""
    from test_suspend import SuspendPaneTests as _S
    setUp, fake_look, fake_token, fake_pane, fake_kill, fake_info, fake_run = (
        _S.setUp, _S.fake_look, _S.fake_token, _S.fake_pane, _S.fake_kill, _S.fake_info, _S.fake_run)

    def test_both_looks_read_from_the_bottom(self):
        scrolled = dict(pane("w1:p1"), scroll={"viewport_rows": 30, "offset_from_bottom": 99})
        rows_asked = []
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([scrolled])), \
                mock.patch.object(suspend.herdr, "pane", side_effect=lambda pid: dict(self.fake_pane(pid),
                                                                                      scroll=scrolled["scroll"])), \
                mock.patch.object(suspend.herdr, "read_screen",
                                  side_effect=lambda p, rows=None, **k: rows_asked.append(rows) or self.screen), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3600), "")
        self.assertEqual(rows_asked, [30, 30])


class HookStartsFlowTests(StateDir):
    """What a hook starts for a missing placeholder, in each mode."""

    def hook(self, mode, available=80.0, rec=None, t=T0):
        self.settings(f'[suspend]\nwhen = "{mode}"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": rec or record(
            base={"screen": "shell", "at": T0 - 600})}}}})
        p = pane("w1:p1", session=None, tab="w1:t1")
        with mock.patch.object(herdr, "snapshot", return_value=snap([p])), \
                mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=t), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(procs, "available_percent", return_value=available), \
                mock.patch.object(suspend, "spawn_worker", return_value=True) as spawn:
            core.handle_event("pane.focused", {"data": {}}, env={})
        return [c.args[0] for c in spawn.call_args_list]

    def test_every_mode_puts_a_lost_placeholder_back(self):  # review 7 R136
        self.assertEqual(self.hook("manual"), [["--rearm-pass"]])
        self.assertEqual(self.hook("off"), [["--rearm-pass"]])
        self.assertEqual(self.hook("memory", available=80.0), [["--rearm-pass"]])  # memory fine: no check runs
        self.assertEqual(self.hook("memory", available=5.0), [[]])  # a check runs, and re-arms
        self.assertEqual(self.hook("time"), [[]])

    def test_no_pass_for_a_shell_someone_used(self):  # review 7 R135 (a worker every minute for nothing)
        self.assertEqual(self.hook("manual", rec=record(base={"screen": "shell", "at": T0 - 600, "used": True})), [])

    def test_a_slow_stop_finished_by_a_hook_starts_no_restart_rearm(self):  # review 7 R137
        rec = record(state="stopping", at=T0 - suspend.STOP_STALE - 5)
        rec.pop("base", None)
        self.assertEqual(self.hook("manual", rec=rec), [["--rearm-pass"]])
        s = store.load_index()["sessions"]["default"]
        self.assertEqual(s["suspended"]["w1:p1"]["state"], "suspended")
        self.assertNotIn("rearm", s)



class AccountFlowTests(StateDir):
    """Review 7 R139: an agent started with its own account settings
    (`ANTHROPIC_BASE_URL=... claude`) comes back with the shell's when Enter
    types the resume into that shell; the placeholder, which runs in that
    shell, says so first."""

    def test_the_environment_is_read_whole(self):
        import subprocess
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"],
                                 env={"EARMARK_TEST_VAR": "a b=c", "PATH": "/usr/bin:/bin"})
        try:
            for _ in range(100):  # until it has exec'd (a forked child still has our environment)
                env = procs.environ(child.pid) or {}
                if "EARMARK_TEST_VAR" in env:
                    break
                time.sleep(0.02)
        finally:
            child.kill()
            child.wait()
        self.assertEqual(env.get("EARMARK_TEST_VAR"), "a b=c")
        self.assertIsNone(procs.environ(2 ** 22 + 12345))  # no such process
        with mock.patch.object(procs, "linux", return_value=False), \
                mock.patch.object(procs.subprocess, "run", return_value=mock.Mock(
                    returncode=0, stdout=b"claude --x A=1 B=/Users/a/Library/Application Support/x C=")):
            self.assertEqual(procs.environ(1), {"A": "1", "B": "/Users/a/Library/Application Support/x", "C": ""})
        with mock.patch.object(procs, "environ", return_value={"CLAUDE_CONFIG_DIR_OLD": "/old"}):
            self.assertEqual(procs.environ_var(1, "CLAUDE_CONFIG_DIR"), "")  # the exact name, not a prefix

    def test_fingerprints_never_hold_the_value(self):
        fp = agents.account_env({"ANTHROPIC_API_KEY": "sk-secret", "PATH": "/bin", "AWS_PROFILE": "work",
                                 "HTTPS_PROXY": "http://proxy"})
        self.assertEqual(sorted(fp), ["ANTHROPIC_API_KEY", "AWS_PROFILE", "HTTPS_PROXY"])
        self.assertNotIn("sk-secret", repr(fp))
        self.assertEqual(agents.account_changes(fp, {"ANTHROPIC_API_KEY": "sk-secret", "AWS_PROFILE": "work",
                                                     "HTTPS_PROXY": "http://proxy", "PATH": "/usr/bin"}), [])
        self.assertEqual(agents.account_changes(fp, {"ANTHROPIC_API_KEY": "sk-other", "AWS_PROFILE": "work",
                                                     "HTTPS_PROXY": "http://proxy"}), ["ANTHROPIC_API_KEY"])
        self.assertEqual(agents.account_changes(fp, {"ANTHROPIC_API_KEY": "sk-secret", "HTTPS_PROXY": "http://proxy",
                                                     "ANTHROPIC_BASE_URL": "x"}), ["ANTHROPIC_BASE_URL", "AWS_PROFILE"])
        self.assertEqual(agents.account_changes(None, {"ANTHROPIC_API_KEY": "x"}), [])  # the agent's weren't known

    def test_look_keeps_the_agents_settings(self):
        info = {"shell_pid": 10, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"], "cmdline": "claude"}]}
        table = procs.Table({10: (1, "bash", "bash"), 50: (10, "claude", "claude")})
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "environ", return_value={"ANTHROPIC_BASE_URL": "https://work"}), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(procs, "start_token", return_value="tok"), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            found = suspend.look(pane("w1:p1"), {}, table, T0, {})
        self.assertEqual(found["account"], agents.account_env({"ANTHROPIC_BASE_URL": "https://work"}))

    def run_placeholder(self, account, shell_env, keys):
        rec = record(account=account)
        waits, marked = [], []

        class NoTerminal:
            def __init__(self, fd):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def wait(rec_, cfg, screen, fd, message=""):
            waits.append(message)
            return keys.pop(0)
        env = dict({k: v for k, v in os.environ.items() if not agents.account_env({k: ""})}, **shell_env)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(suspend, "record", return_value=rec), \
                mock.patch.object(suspend, "mark_waking", side_effect=lambda *a, **k: marked.append(1) or ""), \
                mock.patch.object(placeholder, "Terminal", NoTerminal), \
                mock.patch.object(placeholder, "wait_for_key", side_effect=wait), \
                mock.patch.object(placeholder, "unmark"), \
                mock.patch.object(placeholder.agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(sys, "stdout"):
            code = placeholder.main("default", "w1:p1")
        return code, waits, marked

    def test_enter_warns_before_resuming_with_another_account(self):
        work = agents.account_env({"ANTHROPIC_BASE_URL": "https://work.example"})
        code, waits, marked = self.run_placeholder(work, {"ANTHROPIC_BASE_URL": "https://personal.example"},
                                                   ["resume", "resume"])
        self.assertEqual(code, 0)
        self.assertEqual(len(waits), 2)
        self.assertIn("ANTHROPIC_BASE_URL", waits[1])  # said before anything resumed...
        self.assertEqual(marked, [1])  # ...and only the second Enter resumed it
        code, waits, marked = self.run_placeholder(work, {"ANTHROPIC_BASE_URL": "https://personal.example"},
                                                   ["resume", "leave"])
        self.assertEqual((marked, code), ([], 1))  # Ctrl+C after the warning: nothing resumed

    def test_the_same_settings_resume_at_once(self):
        work = agents.account_env({"ANTHROPIC_BASE_URL": "https://work.example"})
        code, waits, marked = self.run_placeholder(work, {"ANTHROPIC_BASE_URL": "https://work.example"}, ["resume"])
        self.assertEqual((code, len(waits), marked), (0, 1, [1]))
        code, waits, marked = self.run_placeholder(None, {"ANTHROPIC_BASE_URL": "x"}, ["resume"])  # unknown: no warning
        self.assertEqual((code, len(waits), marked), (0, 1, [1]))

    def test_the_warning_fits_the_placeholder(self):
        cfg = {"title_first": "tab", "suspend": {"show": "frozen"}}
        msg = ("This shell's ANTHROPIC_BASE_URL isn't what the agent was started with: it would come back with the "
               "shell's (another account or endpoint). Enter again resumes it anyway; Ctrl+C leaves it.")
        import re
        for show, screen in (("frozen", "line\n" * 30), ("notice", "")):
            cfg["suspend"]["show"] = show
            rows = placeholder.compose(record(), cfg, screen, 24, 80, T0, msg)
            plain = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", r).strip() for r in rows)
            self.assertIn("Enter again resumes it anyway; Ctrl+C leaves it.", plain, show)
            self.assertEqual(len(rows), 24)


class AccountRecordTests(unittest.TestCase):
    """The worker's one-pane flow (SuspendPaneTests' fakes, not its tests)
    keeps the agent's account fingerprints in the record (review 7 R139)."""
    from test_suspend import SuspendPaneTests as _S
    setUp, fake_token, fake_pane, fake_kill, fake_info, fake_run = (
        _S.setUp, _S.fake_token, _S.fake_pane, _S.fake_kill, _S.fake_info, _S.fake_run)

    def fake_look(self, p, note, table, t, timers):
        from test_suspend import found
        return found(T0 - 7200, group=50, pid=50, chain=[50], tokens={50: "L"}, flags=[], unknown_flags=[],
                     launch=["claude"], config_dir="", account={"ANTHROPIC_BASE_URL": "abc123"})

    def test_the_record_keeps_the_fingerprints(self):
        with mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3600), "")
        self.assertEqual(suspend.record("default", "w1:p1")["account"], {"ANTHROPIC_BASE_URL": "abc123"})


class LastLookTests(unittest.TestCase):
    """Review 7 R140: the last look before the signal reads the prompt again;
    an unreadable one is a doubt there too (the first look already says so)."""
    from test_suspend import SuspendPaneTests as _S
    setUp, fake_look, fake_token, fake_pane, fake_kill, fake_info, fake_run = (
        _S.setUp, _S.fake_look, _S.fake_token, _S.fake_pane, _S.fake_kill, _S.fake_info, _S.fake_run)

    def suspend(self, screens, manual=False, accept=None):
        with mock.patch.object(suspend.herdr, "read_screen", side_effect=lambda p, **k: screens.pop(0)), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            return suspend.suspend_pane("default", "w1:p1", CFG, "manual" if manual else "time", manual=manual,
                                        min_idle=0 if manual else 3600, accept=accept)

    def test_a_prompt_unreadable_at_the_last_look_stops_nothing(self):
        why = self.suspend([claude_screen(), "a screen Earmark can't read", "x"])
        self.assertIn("can't read its prompt now", why)
        self.assertNotIn(("kill", "stopping"), self.events)

    def test_the_doubt_the_user_took_holds_at_the_last_look(self):
        unreadable = "a screen Earmark can't read"
        why = self.suspend([unreadable, unreadable, "x"], manual=True, accept=suspend.UNREADABLE_PROMPT)
        self.assertEqual(why, "")
        self.assertIn(("kill", "stopping"), self.events)


class WriteOrderTests(StateDir):
    """Review 7 R141: the archive is written before the index, so a failed
    archive write (a full disk) never leaves a session in neither file."""

    def test_a_closed_suspended_tab_survives_a_failed_archive_write(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        with mock.patch.object(store, "save_archive", side_effect=OSError("No space left on device")):
            with self.assertRaises(OSError):
                core.settle_now("default", snap([]), T0)
        self.assertIn("w1:p1", store.load_index()["sessions"]["default"]["suspended"])  # still there: filed next time

    def test_a_closed_tab_survives_a_failed_archive_write(self):
        self.settings('[suspend]\nwhen = "manual"\n')
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {
            "agent": "claude", "session_id": "s1", "workspace_id": "w1", "tab_id": "w1:t1", "seen": T0,
            "since": T0}}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=T0 + 5), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(store, "save_archive", side_effect=OSError("No space left on device")):
            with self.assertRaises(OSError):
                core.handle_event("tab.closed", {"data": {}}, env={})
        self.assertIn("w1:p1", store.load_index()["sessions"]["default"]["panes"])


class KeyAnswerTests(StateDir):
    """Review 7 R142: a question that comes long after the press doesn't
    take the keyboard, and questions name the tab."""

    def tell(self, pressed):
        with mock.patch.object(herdr, "pane", return_value={"tab_id": "w1:t1"}), \
                mock.patch.object(herdr, "run", return_value={"tab": {"label": "auth fix"}}), \
                mock.patch.object(herdr, "notify", return_value=False), \
                mock.patch.object(message, "show") as show:
            suspend.tell("default", "w1:p1", suspend.CONFIRM + suspend.UNREADABLE_PROMPT,
                         {"suspend": {"messages": "popup"}}, pressed)
        return show

    def test_a_prompt_question_names_the_tab(self):
        show = self.tell(time.time())
        self.assertEqual(show.call_args.args[0], "Suspend \u201cauth fix\u201d anyway?")
        self.assertIn("ask", show.call_args.kwargs)

    def test_a_late_question_is_said_instead(self):
        show = self.tell(time.time() - suspend.LATE - 5)
        self.assertNotIn("ask", show.call_args.kwargs)  # no question, so nothing to answer by accident...
        self.assertFalse(show.call_args.kwargs.get("focus", True))  # ...and the keyboard stays where it was
        self.assertIn("auth fix", show.call_args.args[0])


class SuiteSandboxTests(unittest.TestCase):
    def test_the_default_claude_folder_is_the_suites_own(self):  # review 8 R159
        import tempfile
        self.assertTrue(agents._claude_dir("").startswith(tempfile.gettempdir()))
        self.assertEqual(os.path.expanduser("~"), os.path.join(_isolate.ROOT, "home"))  # the suite's own, exactly


class UnknownFolderTests(StateDir):
    """Review 7 R143: a Claude session whose folder lookup failed is filed
    (it may live in another folder) and kept by keep_days."""

    def setUp(self):
        super().setUp()
        claude = os.path.join(self.dir.name, "claude")
        os.makedirs(os.path.join(claude, "projects"))  # a default folder Earmark can look into
        home = os.path.join(self.dir.name, "home")
        os.makedirs(os.path.join(home, ".claude", "projects"))  # and ~/.claude, for a Claude folder of ""
        p = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": claude, "HOME": home})
        p.start()
        self.addCleanup(p.stop)

    def test_filed_and_kept(self):
        entries = {}
        note = {"agent": "claude", "session_id": "s1", "workspace_id": "w1", "seen": T0}  # config_dir unknown
        self.assertTrue(core.archive_note(entries, "default", note, T0, "closed"))
        self.assertTrue(entries["claude:s1"]["folder_unknown"])
        archive = {"entries": entries}
        core.prune(archive, dict(config.DEFAULTS), T0 + 86400)
        self.assertIn("claude:s1", archive["entries"])
        core.prune(archive, dict(config.DEFAULTS), T0 + (config.FALLBACK_DAYS + 1) * 86400)
        self.assertNotIn("claude:s1", archive["entries"])

    def test_a_known_default_folder_still_skips_a_session_with_nothing_to_resume(self):
        note = {"agent": "claude", "session_id": "s1", "workspace_id": "w1", "seen": T0, "config_dir": ""}
        self.assertFalse(core.archive_note({}, "default", note, T0, "closed"))


class QuietHookTests(StateDir):
    """Review 7 R144: with suspending off (the shipped default) or manual, a
    tab switch doesn't rewrite index.json; the idle clock is for the
    automatic modes."""

    def switch(self, mode):
        self.settings(f'[suspend]\nwhen = "{mode}"\n')
        panes = [pane("w1:p1", tab="w1:t1"), pane("w1:p2", session="s2", tab="w1:t2")]
        saves = 0
        for t, focus in ((T0, "w1:p1"), (T0 + 30, "w1:p2"), (T0 + 60, "w1:p1"), (T0 + 90, "w1:p2")):
            now = [dict(p, focused=p["pane_id"] == focus) for p in panes]
            with mock.patch.object(herdr, "snapshot", return_value=snap(now)), \
                    mock.patch.object(herdr, "process_info", return_value={}), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=t), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(procs, "available_percent", return_value=80.0), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True), \
                    mock.patch.object(store, "save_index", wraps=store.save_index) as save:
                core.handle_event("pane.focused", {"data": {"pane_id": focus}}, env={})
            saves += save.call_count if t > T0 else 0
        return saves, store.load_index()["sessions"]["default"]["panes"]

    def test_off_and_manual_dont_write_on_a_tab_switch(self):
        for mode in ("off", "manual"):
            saves, notes = self.switch(mode)
            self.assertEqual(saves, 0, mode)
            self.assertNotIn("focused_at", notes["w1:p1"])

    def test_a_status_change_doesnt_write_either(self):
        self.settings('[suspend]\nwhen = "manual"\n')
        saves = 0
        for t, status in ((T0, "idle"), (T0 + 30, "working"), (T0 + 60, "idle")):
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", status=status)])), \
                    mock.patch.object(herdr, "process_info", return_value={}), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=t), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(store, "save_index", wraps=store.save_index) as save:
                core.handle_event("pane.agent_status_changed", {"data": {"pane_id": "w1:p1"}}, env={})
            saves += save.call_count if t > T0 else 0
        self.assertEqual(saves, 0)
        self.assertNotIn("status_at", store.load_index()["sessions"]["default"]["panes"]["w1:p1"])

    def test_time_mode_keeps_the_idle_clock(self):
        saves, notes = self.switch("time")
        self.assertIn("focused_at", notes["w1:p1"])


class PopupFitTests(StateDir):
    """Review 7 R145, R146: questions keep their buttons and their text in
    small popups."""

    def test_the_forget_question_keeps_both_buttons(self):
        popup = ui.Popup({"workspace_label": "Work"})
        popup.view, popup.confirm = "workspaces", "k"
        for w in (60, 72, 80):
            popup.draw_footer(mock.Mock(), 20, w)
            self.assertEqual(sorted(popup.buttons), ["forget", "keep"], w)

    def test_the_message_popup_has_room_for_its_question(self):
        text = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "herdr-plugin.toml")).read()
        pane_ = text[text.index('id = "message"'):]
        self.assertIn('height = "50%"', pane_[:pane_.index("command")])
        # 80x24: a popup of about 48x12, so about 46x10 inside the border.
        rows = message.lines("Suspend \u201cauth fix\u201d anyway?", suspend.UNREADABLE_PROMPT[0].upper()
                             + suspend.UNREADABLE_PROMPT[1:] + "; Claude's own record of this process is missing, "
                             "so Earmark can't tell if it's busy or has Remote Control on.",
                             "y then Enter: suspend it anyway    anything else: keep it running", 46, 10)
        self.assertFalse(any(r.endswith("\u2026") for r in rows[3:]), rows)


class MessageKeyTests(unittest.TestCase):
    """Review 7 R147: a plain message ignores keys in its first moment, like a
    question, so typing that went on after the press doesn't close it unread."""

    def test_keys_in_the_first_moment_are_dropped(self):
        calls = []
        with mock.patch.dict(os.environ, {message.ENV: '{"title": "T", "body": "B"}'}), \
                mock.patch.object(message.os, "isatty", return_value=True), \
                mock.patch.object(message.termios, "tcgetattr", return_value=[]), \
                mock.patch.object(message.termios, "tcsetattr"), mock.patch.object(message.tty, "setraw"), \
                mock.patch.object(message.termios, "tcflush", side_effect=lambda *a: calls.append("flush")), \
                mock.patch.object(message.time, "sleep", side_effect=lambda s: calls.append(("sleep", s))), \
                mock.patch.object(message, "draw", side_effect=lambda *a: calls.append("draw")), \
                mock.patch.object(message, "read_key", side_effect=lambda *a: calls.append("read")), \
                mock.patch.object(sys, "stdout"):
            message.main()
        self.assertEqual(calls[calls.index("draw"):], ["draw", ("sleep", message.KEY_DELAY), "flush", "read"])


class XdgTests(unittest.TestCase):
    """Review 7 R148: `earmark.py check` and `list` run by hand find Herdr's
    plugin folders under XDG_CONFIG_HOME / XDG_STATE_HOME."""

    def test_xdg_folders(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k not in ("HERDR_PLUGIN_CONFIG_DIR", "HERDR_PLUGIN_STATE_DIR")}
            env.update(XDG_CONFIG_HOME=os.path.join(d, "c"), XDG_STATE_HOME=os.path.join(d, "s"))
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(config.config_dir(), os.path.join(d, "c", "herdr", "plugins", "config",
                                                                   "io.github.cwilliams5.earmark"))
                self.assertEqual(store.state_dir(), os.path.join(d, "s", "herdr", "plugins", "io.github.cwilliams5.earmark"))


class TranscriptRewriteTests(unittest.TestCase):
    """Review 7 R149: a rewritten transcript forgets the permission mode read
    from the old one."""

    def test_the_mode_goes_with_the_old_file(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s1.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "permission-mode", "permissionMode": "auto"}) + "\n")
            cache = {}
            agents.claude_timers(path, 0, cache, T0)
            self.assertEqual(cache.get("mode"), "auto")
            with open(path, "w") as f:  # rewritten: another start, no mode
                f.write(json.dumps({"type": "user", "message": {"content": "hi there, a different file"}}) + "\n")
            agents.claude_timers(path, 0, cache, T0)
            self.assertFalse(cache.get("mode"))

if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------- strict review 8

def _flow_fakes():
    from test_suspend import SuspendPaneTests as S
    return S.setUp, S.fake_look, S.fake_token, S.fake_pane, S.fake_kill, S.fake_info, S.fake_run


class PermissionModeAtExitTests(unittest.TestCase):
    """R155 (checked live): Claude writes a Shift+Tab out of auto only as it
    exits; the resume line follows the mode it was really in."""
    setUp_, _look, fake_token, fake_pane, fake_kill_, fake_info, fake_run = _flow_fakes()

    def setUp(self):
        self.setUp_()
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        self.transcript = os.path.join(d, "s1.jsonl")
        self.write({"type": "permission-mode", "permissionMode": "auto"})
        self.at_exit = None  # what Claude writes as it exits

    def write(self, record):
        with open(self.transcript, "a") as f:
            f.write(json.dumps(record) + "\n")

    def fake_look(self, p, note, table, t, timers):
        found = self._look(p, note, table, t, timers)
        found["facts"] = dict(found["facts"], source=self.transcript)
        found["mode"] = "auto"
        return found

    def fake_kill(self, pid, sig):
        self.fake_kill_(pid, sig)
        if self.at_exit:
            self.write({"type": "permission-mode", "permissionMode": self.at_exit})

    def suspend(self):
        with mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3600), "")
        return suspend.record("default", "w1:p1")["resume"]

    def test_the_mode_written_at_exit_wins(self):
        self.at_exit = "default"  # Shift+Tab to manual, written as it exits
        self.assertNotIn("auto", self.suspend())

    def test_still_auto_at_exit_stays_auto(self):
        self.at_exit = "auto"
        self.assertEqual(self.suspend()[-2:], ["--permission-mode", "auto"])

    def test_no_exit_record_and_no_footer_never_widens(self):
        self.assertNotIn("auto", self.suspend())  # the kept screen doesn't show auto on

    def test_no_exit_record_but_the_footer_shows_it(self):
        self.screen = claude_screen() + "\n  ⏵⏵ auto mode on (shift+tab to cycle)"
        self.assertEqual(self.suspend()[-2:], ["--permission-mode", "auto"])

    def test_the_pieces(self):
        self.assertEqual(agents.claude_mode_since(self.transcript, 0), "auto")
        size = os.path.getsize(self.transcript)
        self.assertIsNone(agents.claude_mode_since(self.transcript, size))
        self.write({"type": "permission-mode", "permissionMode": "plan"})
        self.assertEqual(agents.claude_mode_since(self.transcript, size), "plan")
        self.assertEqual(agents.launch_mode(["--dangerously-skip-permissions"]), "bypassPermissions")
        self.assertEqual(agents.launch_mode(["--permission-mode=auto"]), "auto")
        self.assertEqual(agents.mode_to_resume(None, "", ["--permission-mode", "auto"], "no footer"), "default")
        self.assertEqual(agents.mode_to_resume(None, "plan", [], ""), "plan")  # narrower modes need no proof
        self.assertEqual(agents.mode_to_resume("default", "bypassPermissions", [], "bypass permissions on"), "default")


class RestartMidStopTests(StateDir):
    """R156: Herdr lists the session while a stop or a resume is under way,
    so after a restart its own restore may relaunch it: no placeholder typed
    during the grace."""

    def test_a_stopping_record_remembers_herdr_listed_it(self):
        index = {"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record(state="stopping", at=T0)}}}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, {"entries": {}}, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0 + 2)
        self.assertTrue(index["sessions"]["default"]["suspended"]["w1:p1"].get("herdr_listed"))
        store.save_index(index)
        s = index["sessions"]["default"]
        s["boot"], s["boot_grace"] = T0 + 10, 60
        store.save_index(index)
        with mock.patch.object(suspend.time, "time", return_value=T0 + 20):
            self.assertTrue(suspend.herdr_may_relaunch("default", "w1:p1", suspend.record("default", "w1:p1")))

    def test_enter_marks_the_resume_as_listed(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": record()}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(agents, "claude_running", return_value=False):
            self.assertEqual(suspend.mark_waking("default", "w1:p1"), "")
        self.assertTrue(suspend.record("default", "w1:p1").get("herdr_listed"))


class ConfirmAnswerTests(StateDir):
    """R157: after `y`, the answer says how it really went, by the press time."""

    def test_a_suspend_that_happened_is_said_as_such(self):
        with mock.patch.object(suspend, "confirm", return_value=suspend.NOT_YET), \
                mock.patch.object(suspend, "say") as say:
            suspend.worker("default", CFG, pane_id="w1:p1", accept="a doubt", pressed=time.time() - 30)
        title, body = say.call_args.args[1:3]
        self.assertEqual(title, "Suspended")
        self.assertNotIn("kept it running", body)
        self.assertLess(say.call_args.args[3], time.time() - 20)  # the press time: a late answer stays out of the way


class PasteTests(unittest.TestCase):
    """R158: a paste into a placeholder never resumes it."""

    def test_pasted_newlines_arent_enter(self):
        keys, pasting = placeholder.outside_paste(b"\x1b[200~fix it\r\nplease\x1b[201~", False)
        self.assertEqual((keys, pasting), (b"", False))
        self.assertIsNone(placeholder.key_action(keys))
        keys, pasting = placeholder.outside_paste(b"\x1b[200~a long\r", False)  # split across reads
        self.assertEqual((keys, pasting), (b"", True))
        keys, pasting = placeholder.outside_paste(b"paste\x1b[201~\r", True)
        self.assertEqual((keys, pasting), (b"\r", False))  # the Enter typed after it counts
        self.assertEqual(placeholder.key_action(keys), "resume")
        self.assertIn("\x1b[?2004h", placeholder.ENTER_SCREEN)
        self.assertIn("\x1b[?2004l", placeholder.LEAVE_SCREEN)


class ScreenCopyTests(unittest.TestCase):
    """R160: the screen copy is written before anything is stopped; a
    failed write leaves the agent running and no record behind."""
    setUp, fake_look, fake_token, fake_pane, fake_kill, fake_info, fake_run = _flow_fakes()

    def test_a_full_disk_stops_nothing(self):
        real_open = os.open

        def no_space(path, *a, **k):
            if path.endswith(".ansi") or "screens" in path:
                raise OSError(28, "No space left on device")
            return real_open(path, *a, **k)
        with mock.patch.object(suspend.os, "open", side_effect=no_space), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3600)
        self.assertIn("couldn't keep a copy of its screen", why)
        self.assertNotIn(("kill", "stopping"), self.events)
        self.assertIsNone(suspend.record("default", "w1:p1"))


class RecordGuardTests(StateDir):
    def test_a_resume_of_a_record_gone_meanwhile_still_checks_elsewhere(self):  # T1
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        elsewhere = snap([pane("w1:p1", session=None), pane("w1:p7", session="s1", tab="w1:t7")])
        with mock.patch.object(herdr, "snapshot", return_value=elsewhere), \
                mock.patch.object(agents, "claude_running", return_value=True):
            why = suspend.mark_waking("default", "w1:p1", fallback=record())
        self.assertIn("open somewhere else", why)

    def test_a_noted_pane_not_back_yet_after_a_restart_isnt_closed(self):  # T2
        index = {"sessions": {"default": {"panes": {"w1:p1": {"agent": "claude", "session_id": "s1", "seen": T0,
                                                               "since": T0, "workspace_id": "w1"}}}}}
        archive = {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, archive, "default", snap([pane("w1:p2", session="s2")]), "startup", {}, T0 + 100)
        self.assertEqual(archive["entries"], {})  # within the grace Herdr may still be bringing it back
        self.assertIn("w1:p1", index["sessions"]["default"]["panes"])


class TimingTests(StateDir):
    """R161: the dwell, the first moment and the return grace, as amounts."""

    def test_resume_on_view_waits_a_real_moment(self):
        with mock.patch.object(suspend.time, "sleep") as sleep, \
                mock.patch.object(herdr, "pane", return_value={"focused": False}):
            suspend.wake_on_view("default", "w1:p1")
        self.assertGreaterEqual(sleep.call_args.args[0], 0.5)
        self.assertGreaterEqual(message.KEY_DELAY, 0.2)

    def test_coming_back_after_a_night_waits_the_return_grace(self):
        self.settings('[suspend]\nwhen = "time"\n')
        for t in (T0, T0 + suspend.AWAY_GAP + 60):
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=t), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True):
                core.handle_event("pane.focused", {"data": {}}, env={})
        s = store.load_index()["sessions"]["default"]
        self.assertEqual(s["quiet_until"], T0 + suspend.AWAY_GAP + 60 + suspend.RETURN_GRACE)


class CarriedStateTests(StateDir):
    """R161: what one step leaves for the next survives the hooks between."""

    def test_a_failed_stops_back_off_survives_a_hook(self):
        index = {"sessions": {"default": {"panes": {}}}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, {"entries": {}}, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0)
            index["sessions"]["default"]["panes"]["w1:p1"]["backoff_until"] = T0 + suspend.BACKOFF
            core.apply(index, {"entries": {}}, "default", snap([pane("w1:p1")]), "pane.focused", {}, T0 + 60)
        note = index["sessions"]["default"]["panes"]["w1:p1"]
        self.assertEqual(note.get("backoff_until"), T0 + suspend.BACKOFF)

    def test_one_pane_short_after_a_restart_isnt_a_new_session(self):
        panes = {f"w1:p{i}": {"agent": "claude", "session_id": f"s{i}", "seen": T0, "since": T0} for i in (2, 3, 4)}
        index = {"sessions": {"default": {"panes": panes, "suspended": {"w1:p1": record()}}}}
        back = [pane("w1:p1", session=None, tab="w1:t1"), pane("w1:p2", session="s2"), pane("w1:p3", session="s3")]
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, {"entries": {}}, "default", snap(back), "startup", {}, T0 + 100)
        self.assertIn("w1:p1", index["sessions"]["default"]["suspended"])  # 3 of 4 back: the same session

    def test_two_parent_changes_are_still_restarts(self):
        index = {"sessions": {"default": {"panes": {}, "server_pid": 1}}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            core.apply(index, {"entries": {}}, "default", snap([]), "pane.focused", {}, T0, server_pid=2)
            core.apply(index, {"entries": {}}, "default", snap([]), "pane.focused", {}, T0 + 60, server_pid=3)
        s = index["sessions"]["default"]
        self.assertEqual(s["boot"], T0 + 60)
        self.assertFalse(s.get("ppid_unreliable"))

    def test_restore_resumes_only_sessions_that_still_exist(self):
        rec = {"key": "k", "label": "Gone", "tabs": [{"label": "t", "cwd": "/tmp", "agent": "claude",
                                                      "session_id": "s1"}]}
        with mock.patch.object(herdr, "snapshot", return_value=snap([], {})), \
                mock.patch.object(herdr, "run", return_value={"workspace": {"workspace_id": "w5"},
                                                             "tab": {"tab_id": "w5:t1"},
                                                             "root_pane": {"pane_id": "w5:p1"}}), \
                mock.patch.object(herdr, "run_in_pane") as run_in, \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, exists=False)):
            core.restore_workspace(rec, dict(config.DEFAULTS))
        run_in.assert_not_called()

    def test_a_titles_bar_is_kept_for_claude(self):
        self.assertEqual(agents.clean_title("✳ Fix A | B", "claude"), "Fix A | B")


class SmallFixTests(StateDir):
    def test_a_double_click_on_the_x_asks_to_forget(self):  # R163
        entries = {"claude:s1": {"herdr_session": "default", "workspace_label": "Work", "agent": "claude",
                                 "session_id": "s1", "last_active": T0, "closed_at": T0}}
        store.save_archive({"entries": entries})
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            popup = ui.Popup({"workspace_label": "Work"})
            scr = mock.Mock()
            scr.getmaxyx.return_value = (20, 80)
            with mock.patch.object(ui.curses, "getmouse", return_value=(0, 78, 2, 0, ui.curses.BUTTON1_DOUBLE_CLICKED)), \
                    mock.patch.object(popup, "do_open", return_value=True) as do_open:
                self.assertFalse(popup.on_mouse(scr))
        do_open.assert_not_called()
        self.assertEqual(popup.confirm, "claude:s1")

    def test_scheduled_tasks_of_an_unknown_shape_are_a_doubt(self):  # R164
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            path = os.path.join(d, ".claude", "scheduled_tasks.json")
            for data, expected in (({"schedules": [{}]}, None), ({}, 0), ({"tasks": [{}, {}]}, 2), ([{}], 1)):
                with open(path, "w") as f:
                    json.dump(data, f)
                self.assertEqual(agents.durable_tasks(d), expected, data)

    def test_count_mode_looks_only_at_agents_quiet_long_enough(self):  # R165
        self.settings('[suspend]\nwhen = "count"\nkeep_awake = 1\n')
        notes = {f"w1:p{i}": {"session_id": f"s{i}", "since": T0 - 120} for i in (1, 2, 3)}
        store.save_index({"sessions": {"default": {"panes": notes, "suspended": {}}}})
        panes = [pane(f"w1:p{i}", session=f"s{i}") for i in (1, 2, 3)]
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes)), \
                mock.patch.object(suspend.time, "time", return_value=T0), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", config.load())
        look.assert_not_called()

    def test_quiet_hooks_rewrite_little(self):  # R166
        self.settings('[suspend]\nwhen = "off"\n')
        panes = [pane(f"w1:p{i}", session=f"s{i}", tab=f"w1:t{i}") for i in range(1, 11)]
        saves = 0
        for k in range(120):  # an hour of hooks every 30 s, nothing changing
            t = T0 + 30 * k + (k % 7)  # notes first seen at different moments
            with mock.patch.object(herdr, "snapshot", return_value=snap(panes[: 1 + min(k, 9)])), \
                    mock.patch.object(herdr, "process_info", return_value={"foreground_processes": [
                        {"pid": 50, "name": "claude"}]}), \
                    mock.patch.object(procs, "environ_var", return_value=""), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=t), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(store, "save_index", wraps=store.save_index) as save:
                core.handle_event("pane.focused", {"data": {}}, env={})
            saves += save.call_count if k >= 10 else 0
        self.assertLessEqual(saves, 8)  # the session's "seen" every 10 minutes, not a note at a time


class CostAndPasteLoopTests(StateDir):
    def test_time_mode_hooks_dont_rewrite_for_the_clock_alone(self):  # R161 (r8 m04)
        self.settings('[suspend]\nwhen = "time"\n')
        saves = 0
        for k in range(12):  # two minutes of hooks every 10 s, nothing changing
            with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                    mock.patch.object(herdr, "process_info", return_value={"foreground_processes": [
                        {"pid": 50, "name": "claude"}]}), \
                    mock.patch.object(procs, "environ_var", return_value=""), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(core, "now", return_value=T0 + 10 * k), \
                    mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                    mock.patch.object(suspend, "spawn_worker", return_value=True), \
                    mock.patch.object(store, "save_index", wraps=store.save_index) as save:
                core.handle_event("pane.focused", {"data": {}}, env={})
            saves += save.call_count if k else 0
        self.assertLessEqual(saves, 4)  # a check a minute and the clock a minute, not every hook



class PasteLoopTests(unittest.TestCase):  # real time.sleep: the loop must see the paste in a read of its own
    def test_a_paste_into_the_placeholders_loop_never_resumes(self):  # R158, through wait_for_key
        import termios
        import tty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        tty.setraw(slave, termios.TCSANOW)
        import threading
        got = []

        def loop():
            got.append(placeholder.wait_for_key({"agent": "claude", "at": T0, "tab_label": "t"},
                                                {"title_first": "tab", "suspend": {"show": "notice"}}, "", slave))
        with mock.patch.object(sys, "stdout"), \
                mock.patch.object(placeholder.os, "get_terminal_size", return_value=os.terminal_size((80, 24))), \
                mock.patch.object(placeholder.signal, "signal"), \
                mock.patch.object(placeholder.signal, "set_wakeup_fd", return_value=-1):
            runner = threading.Thread(target=loop, daemon=True)
            runner.start()
            time.sleep(0.2)
            os.write(master, b"\x1b[200~fix the tests\r\nplease\r\x1b[201~")  # read on its own
            time.sleep(0.3)
            os.write(master, b"\x03")  # then Ctrl+C: the loop must still be waiting to see it
            runner.join(3)
        self.assertEqual(got, ["leave"])
