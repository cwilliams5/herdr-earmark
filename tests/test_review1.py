"""Tests for strict review 1 (docs/PLAN.md R1-R26): one per finding, and one
per behaviour the reviewers' own mutations showed untested. Run:
python3 -m unittest discover tests

They use made-up snapshots, process tables, transcripts and a fake Herdr
program; nothing touches a running Herdr or a real process."""
import json
import os
import pty
import signal
import tty
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, herdr, placeholder, procs, store, suspend  # noqa: E402
from test_suspend import CFG, T0, claude_screen, found, pane, snap  # noqa: E402

CFG_TIME = dict(CFG, suspend=dict(config.SUSPEND_DEFAULTS, when="time"), resume={})


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class StateDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        p = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": os.path.join(self.dir.name, "state"),
                                         "HERDR_PLUGIN_CONFIG_DIR": os.path.join(self.dir.name, "config")})
        p.start()
        self.addCleanup(p.stop)
        os.makedirs(os.path.join(self.dir.name, "config"), exist_ok=True)
        s = mock.patch.object(suspend.time, "sleep")
        s.start()
        self.addCleanup(s.stop)
        if not getattr(self, "real_screens", False):  # a bare shell nobody touches: its screen stays "shell"
            sp = mock.patch.object(suspend, "screen_print", return_value="shell")
            sp.start()
            self.addCleanup(sp.stop)

    def settings(self, text):
        with open(os.path.join(self.dir.name, "config", "config.toml"), "w") as f:
            f.write(text)


# ---------------------------------------------------------------- R1 focus

class IdleClockTests(unittest.TestCase):
    """R1: the idle clock starts when you leave a tab, not when you arrive."""

    def setUp(self):
        self.index, self.archive = {"sessions": {}}, {"entries": {}}
        f = mock.patch.object(agents, "session_facts", return_value={
            "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0 - 9999})
        f.start()
        self.addCleanup(f.stop)

    def apply(self, panes, t, event="pane.focused", data=None):
        core.apply(self.index, self.archive, "default", snap(panes), event, data or {}, t)

    def test_a_long_look_counts_until_you_leave(self):
        self.apply([pane("w1:p1", focused=True), pane("w1:p2", session="s2")], T0,
                   data={"pane_id": "w1:p1"})
        # An hour later, the first event: you switch to the other tab.
        self.apply([pane("w1:p1"), pane("w1:p2", session="s2", focused=True)], T0 + 3900,
                   data={"pane_id": "w1:p2"})
        note = self.index["sessions"]["default"]["panes"]["w1:p1"]
        self.assertEqual(note["focused_at"], T0 + 3900)
        f = found(note["focused_at"], pane_id="w1:p1")
        self.assertEqual(suspend.choose([(pane("w1:p1"), note, f)], CFG_TIME, T0 + 3930), [])

    def test_the_tab_in_view_is_stamped_when_its_left(self):  # R1; review 4 R71: not on every hook
        self.apply([pane("w1:p1", focused=True)], T0, data={"pane_id": "w1:p1"})
        self.apply([pane("w1:p1", focused=True)], T0 + 600, event="pane.agent_status_changed")
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["focused_at"], T0)  # no write for it
        self.apply([pane("w1:p1"), pane("w1:p2", session="s2", tab="w1:t9", focused=True)], T0 + 900,
                   event="pane.focused", data={"pane_id": "w1:p2"})
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["focused_at"], T0 + 900)


# ------------------------------------------------------- R2/R3 look() facts

class LookTests(unittest.TestCase):
    """look() on real-shaped processes and transcripts (it was mocked in
    every flow test)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.cfgdir = os.path.join(self.dir.name, "claude")
        os.makedirs(os.path.join(self.cfgdir, "projects", "-proj"))
        self.transcript = os.path.join(self.cfgdir, "projects", "-proj", "s1.jsonl")
        self.write([{"type": "user", "message": {"content": "hello"}, "timestamp": iso(T0 - 7200)}])
        os.utime(self.transcript, (T0 - 7200, T0 - 7200))
        os.makedirs(os.path.join(self.cfgdir, "sessions"))
        with open(os.path.join(self.cfgdir, "sessions", "50.json"), "w") as f:  # Claude's own record of pid 50
            json.dump({"pid": 50, "sessionId": "s1", "status": "idle"}, f)
        for target in (mock.patch.object(procs, "start_token", return_value="L"),
                       mock.patch.object(procs, "started_at", return_value=T0 - 86400),
                       mock.patch.object(procs, "environ_var", return_value=self.cfgdir),
                       mock.patch.object(procs, "memory_kb", return_value=300_000)):
            target.start()
            self.addCleanup(target.stop)

    def write(self, records, mode="w"):
        with open(self.transcript, mode) as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def look(self, processes, table, note=None, agent="claude"):
        info = {"shell_pid": 10, "foreground_process_group_id": 50, "foreground_processes": processes}
        with mock.patch.object(herdr, "process_info", return_value=info):
            return suspend.look(pane("w1:p1", agent=agent), note or {}, procs.Table(table), T0, {})

    def base(self, extra=None, argv=None):
        processes = [{"pid": 50, "name": "claude", "argv": argv or ["claude"], "cmdline": "claude"}]
        table = {10: (1, "bash", "bash"), 50: (10, "claude", "claude")}
        for pid, (ppid, name, cmd, in_group) in (extra or {}).items():
            table[pid] = (ppid, name, cmd)
            if in_group:
                processes.append({"pid": pid, "name": name, "argv": cmd.split(), "cmdline": cmd})
        return processes, table

    def test_a_quiet_agent_may_be_suspended(self):
        f = self.look(*self.base())
        self.assertEqual(suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None), "")
        self.assertEqual(f["activity"], T0 - 7200)
        self.assertEqual(f["config_dir"], self.cfgdir)

    def test_a_plain_shell_under_the_agent_is_work(self):
        f = self.look(*self.base({60: (50, "bash", "bash -lc npm test", False)}))
        self.assertIn("command is running", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None))

    def test_an_mcp_server_under_the_agent_isnt(self):
        f = self.look(*self.base({60: (50, "node", "node /mcp/server.js", True)}))
        self.assertEqual(f["busy"], "")

    def test_a_stranger_in_the_agents_group_is_work_and_never_signalled(self):  # R2
        f = self.look(*self.base({70: (1, "python3", "python3 -m http.server", True)}))
        self.assertIn("http.server", f["busy"])
        self.assertEqual(f["chain"], [50])

    def test_a_launcher_is_part_of_the_agent(self):  # R2: Codex's node launcher
        processes = [{"pid": 60, "name": "node", "argv": ["node", "/x/codex.js"], "cmdline": "node codex"},
                     {"pid": 61, "name": "codex", "argv": ["codex"], "cmdline": "codex"}]
        table = {10: (1, "bash", "bash"), 60: (10, "node", "node codex"), 61: (60, "codex", "codex")}
        info = {"shell_pid": 10, "foreground_process_group_id": 60, "foreground_processes": processes}
        with mock.patch.object(herdr, "process_info", return_value=info):
            f = suspend.look(pane("w1:p1", agent="codex"), {}, procs.Table(table), T0, {})
        self.assertEqual((f["busy"], f["chain"]), ("", [61, 60]))

    def test_a_pending_loop_wake_up_keeps_it_awake(self):
        self.write([{"type": "assistant", "timestamp": iso(T0 - 600), "message": {"content": [
            {"type": "tool_use", "name": "ScheduleWakeup", "input": {"delaySeconds": 3600}}]}}], "a")
        f = self.look(*self.base())
        self.assertIn("/loop", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None))

    def test_a_scheduled_task_keeps_it_awake(self):
        self.write([{"type": "assistant", "timestamp": iso(T0 - 3000), "message": {"content": [
            {"type": "tool_use", "name": "CronCreate", "input": {"cron": "*/30 * * * *"}}]}}], "a")
        f = self.look(*self.base())
        self.assertIn("scheduled tasks", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None))

    def test_a_wake_up_long_past_doesnt(self):
        self.write([{"type": "assistant", "timestamp": iso(T0 - 7000), "message": {"content": [
            {"type": "tool_use", "name": "ScheduleWakeup", "input": {"delaySeconds": 60}}]}}], "a")
        self.assertEqual(self.look(*self.base())["timers"], "")

    def test_claudes_own_status_and_remote_control(self):
        sessions = os.path.join(self.cfgdir, "sessions")
        os.makedirs(sessions, exist_ok=True)
        for data, expected in (({"status": "busy"}, "working"), ({"status": "shell"}, "shell"),
                               ({"status": "idle", "bridgeSessionId": "b"}, "Remote Control")):
            with open(os.path.join(sessions, "50.json"), "w") as f:
                json.dump(dict(data, pid=50, sessionId="s1"), f)
            got = self.look(*self.base())
            self.assertIn(expected, suspend.refusal(got, pane("w1:p1"), CFG_TIME, T0, False, None))

    def test_subagents_writing_count_as_activity(self):
        sub = os.path.join(self.cfgdir, "projects", "-proj", "s1", "subagents")
        os.makedirs(sub)
        path = os.path.join(sub, "a.jsonl")
        open(path, "w").close()
        os.utime(path, (T0 - 120, T0 - 120))
        self.assertEqual(self.look(*self.base())["activity"], T0 - 120)

    def test_the_most_recent_of_every_clock_counts(self):
        f = self.look(*self.base(), note={"since": T0 - 9000, "focused_at": T0 - 300, "status_at": T0 - 8000})
        self.assertEqual(f["activity"], T0 - 300)

    def test_a_shell_that_cant_run_the_line_is_refused(self):  # R9
        processes, table = self.base()
        table[10] = (1, "nu", "nu")
        self.assertIn("can't run", self.look(processes, table)["why"])

    def test_unknown_options_keep_it_awake(self):  # R10
        f = self.look(*self.base(argv=["claude", "--some-new-flag", "x"]))
        self.assertIn("can't bring back", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None))
        self.assertEqual(suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, True, None), "")  # the key asks itself

    def test_the_session_folder_from_the_note_wins(self):
        f = self.look(*self.base(), note={"config_dir": "/elsewhere"})
        self.assertEqual(f["config_dir"], "/elsewhere")


# ------------------------------------------------------------ choosing

class ChooseOutsideTheSlackTests(unittest.TestCase):
    def looks(self, *ages):
        return [(pane(f"w1:p{i}", session=f"s{i}"), {}, found(T0 - a * 60, pane_id=f"w1:p{i}", session_id=f"s{i}"))
                for i, a in enumerate(ages)]

    def test_keep_awake_is_exact(self):
        for keep, expected in ((1, ["w1:p3", "w1:p2", "w1:p1"]), (2, ["w1:p3", "w1:p2"]), (3, ["w1:p3"])):
            cfg = dict(CFG, suspend=dict(CFG["suspend"], when="count", keep_awake=keep))
            got = [p["pane_id"] for p, _, _ in suspend.choose(self.looks(30, 40, 50, 70), cfg, T0)]
            self.assertEqual(got, expected, keep)

    def test_time_mode_needs_the_full_idle_time(self):
        got = suspend.choose(self.looks(59, 61), CFG_TIME, T0)
        self.assertEqual([p["pane_id"] for p, _, _ in got], ["w1:p1"])


class UnseenTests(unittest.TestCase):
    """R26: suspend_unseen (Cody's ask)."""

    def test_unseen_results_follow_the_setting(self):
        f = found(T0 - 7200)
        on = dict(CFG_TIME, suspend=dict(CFG_TIME["suspend"], suspend_unseen=True))
        off = dict(CFG_TIME, suspend=dict(CFG_TIME["suspend"], suspend_unseen=False))
        self.assertEqual(suspend.refusal(f, pane("w1:p1", status="done"), on, T0, False, None), "")
        self.assertIn("haven't seen", suspend.refusal(f, pane("w1:p1", status="done"), off, T0, False, None))
        self.assertTrue(suspend.candidate_status("done", on))
        self.assertFalse(suspend.candidate_status("done", off))
        self.assertTrue(config.SUSPEND_DEFAULTS["suspend_unseen"])

    def test_the_placeholder_says_it_wasnt_read(self):
        rec = {"agent": "claude", "tab_label": "auth", "at": T0, "unseen": True}
        rows = [agents.plain(r) for r in placeholder.compose(rec, CFG, claude_screen(), 10, 90, T0 + 120)]
        self.assertIn("not read yet", rows[-2])


# ------------------------------------------------- stop and release halves

class HalvesTests(StateDir):
    """Each half of a two-part condition matters on its own."""

    def test_herdr_lets_go_only_when_both_agent_and_session_are_gone(self):
        half_a = dict(pane("w1:p1"), agent=None)  # the agent gone, the session still listed
        half_b = dict(pane("w1:p1", session=None), agent="claude")
        for view in (half_a, half_b):
            with mock.patch.object(herdr, "pane", return_value=view):
                self.assertFalse(suspend.wait_released("w1:p1", "s1", timeout=1))
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)):
            self.assertTrue(suspend.wait_released("w1:p1", "s1", timeout=1))


class StopWaitTests(StateDir):
    """The stop waits for the shell to be back *and* the agent gone."""

    def run_stop(self, shell_back, agent_gone):
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1"}}}}})
        kills = []
        f = found(T0 - 7200, group=50, pid=50, chain=[50], tokens={50: "L"}, flags=[], unknown_flags=[],
                  launch=["claude"], config_dir="")
        stopped = [False]
        info = lambda p: {"shell_pid": 1, "foreground_process_group_id": 1 if (stopped[0] and shell_back) else 50,
                          "foreground_processes": []}
        token = lambda pid: None if (stopped[0] and agent_gone) else "L"
        clock = iter(range(int(T0), int(T0) + 400))
        with mock.patch.object(suspend, "look", return_value=f), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1")), \
                mock.patch.object(herdr, "read_screen", return_value=claude_screen()), \
                mock.patch.object(herdr, "process_info", side_effect=info), \
                mock.patch.object(herdr, "run", return_value={}), \
                mock.patch.object(procs, "start_token", side_effect=token), \
                mock.patch.object(suspend.os, "kill", side_effect=lambda pid, sig: (kills.append((pid, sig)),
                                                                                     stopped.__setitem__(0, True))), \
                mock.patch.object(suspend.time, "time", side_effect=lambda: float(next(clock))):
            return suspend.suspend_pane("default", "w1:p1", CFG_TIME, "manual", manual=True), kills

    def test_shell_back_but_agent_alive_is_no_stop(self):
        why, kills = self.run_stop(shell_back=True, agent_gone=False)
        self.assertIn("didn't stop", why)
        self.assertEqual(suspend.record("default", "w1:p1")["state"], "stopping")  # signalled: kept (R31)
        self.assertEqual(kills, [(50, signal.SIGTERM)])  # the agent only, never its group, never SIGKILL

    def test_agent_gone_but_shell_not_back_keeps_the_session(self):
        why, _ = self.run_stop(shell_back=False, agent_gone=True)
        self.assertEqual(suspend.record("default", "w1:p1")["state"], "suspended")


# ------------------------------------------------------ arming and rearming

class ArmTests(StateDir):
    def put(self, **kw):
        rec = {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude",
               "session_id": "s1", "state": "suspended", "at": T0, "resume": ["claude", "--resume", "s1"],
               "cwd": "/proj", "base": {"screen": "shell", "at": 0}}  # its shell seen back a while ago, unchanged since
        rec.update(kw)
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": rec}}}})

    def shell(self):
        return {"shell_pid": 1, "foreground_process_group_id": 1, "foreground_processes": []}

    def test_a_placeholder_that_doesnt_start_isnt_retyped_every_check(self):  # R9
        self.put(base={"screen": "shell", "at": 0})  # its shell already seen untouched for a check (R84)
        bare = dict(pane("w1:p1", session=None), revision=3)
        with mock.patch.object(herdr, "process_info", return_value=self.shell()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "run") as run, \
                mock.patch.object(herdr, "snapshot", return_value=snap([bare])):
            suspend.rearm_pass("default", snap([bare]))
            suspend.rearm_pass("default", snap([bare]))
        typed = [c for c in run.call_args_list if c.args[:2] == ("pane", "run")]
        self.assertEqual(len(typed), 1)
        self.assertIn("arm_failed", suspend.record("default", "w1:p1"))

    def test_the_tab_in_view_is_never_typed_into(self):
        self.put(base={"screen": "shell", "at": 0})  # an idle shell otherwise (R84), so only the tab in view holds it back
        p = dict(pane("w1:p1", session=None, tab="w1:t1"), revision=1)
        with mock.patch.object(herdr, "process_info", return_value=self.shell()), \
                mock.patch.object(herdr, "pane", return_value=p), \
                mock.patch.object(herdr, "run") as run:
            suspend.rearm_pass("default", snap([p]), skip_tab="w1:t1")
        run.assert_not_called()

    def test_a_resume_in_progress_is_left_alone(self):
        self.put(state="waking", waking_at=time.time(), base={"screen": "shell", "at": 0})
        bare = dict(pane("w1:p1", session=None), revision=1)
        with mock.patch.object(herdr, "process_info", return_value=self.shell()), \
                mock.patch.object(herdr, "pane", return_value=bare), \
                mock.patch.object(herdr, "snapshot", return_value=snap([bare])), \
                mock.patch.object(herdr, "run") as run:
            suspend.rearm_pass("default", snap([bare]))
        run.assert_not_called()

    def test_the_line_says_where_earmarks_files_are(self):  # R9
        line = suspend.placeholder_command("default", "w1:p1", {"agent": "claude", "resume": ["claude"]})
        self.assertIn(f"--state {store.state_dir()}", line)
        self.assertIn(f"--config {config.config_dir()}", line)

    def test_the_placeholder_takes_the_folders_from_its_line(self):
        self.assertTrue(suspend.is_placeholder({"argv": ["python3", "/x/earmark.py", "suspended", "s", "p",
                                                         "--state", "/a", "--config", "/b"]}, "s", "p"))
        self.assertFalse(suspend.is_placeholder({"argv": ["python3", "/x/earmark.py", "suspended", "s", "p",
                                                          "--other", "/a"]}, "s", "p"))
        import earmark as _  # noqa: F401
        spec = __import__("importlib").util.spec_from_file_location(
            "earmark_main", os.path.join(os.path.dirname(__file__), "..", "earmark.py"))
        main = __import__("importlib").util.module_from_spec(spec)
        spec.loader.exec_module(main)
        with mock.patch.object(sys, "argv", ["earmark.py", "suspended", "s", "p", "--state", "/st", "--config", "/cf"]), \
                mock.patch.object(placeholder, "main", return_value=1) as ph, \
                mock.patch.dict(os.environ, {}):
            with self.assertRaises(SystemExit):
                main.cmd_suspended()
            self.assertEqual((os.environ["HERDR_PLUGIN_STATE_DIR"], os.environ["HERDR_PLUGIN_CONFIG_DIR"]),
                             ("/st", "/cf"))
        ph.assert_called_once_with("s", "p")


# --------------------------------------------------- records never dropped

class NeverDroppedTests(StateDir):
    def test_a_forgotten_herdr_session_archives_its_suspended_tabs(self):  # R5
        index = {"sessions": {"client-x": {"panes": {}, "seen": T0 - 31 * 86400, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "agent": "claude", "session_id": "sx", "workspace_label": "W", "state": "suspended",
            "at": T0 - 31 * 86400}}}}}
        archive = {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value={
                "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}):
            core.apply(index, archive, "default", snap([]), "pane.focused", {}, T0)
        self.assertNotIn("client-x", index["sessions"])
        self.assertEqual(archive["entries"]["claude:sx"]["herdr_session"], "client-x")

    def test_a_stale_registry_file_with_a_reused_pid_isnt_open(self):  # R6
        d = tempfile.mkdtemp(dir=self.dir.name)
        os.makedirs(os.path.join(d, "sessions"))
        with open(os.path.join(d, "sessions", "1.json"), "w") as f:
            json.dump({"pid": os.getpid(), "sessionId": "s1", "startedAt": 1000}, f)  # started 1970
        self.assertFalse(agents.claude_running("s1", d))
        with open(os.path.join(d, "sessions", "1.json"), "w") as f:
            json.dump({"pid": os.getpid(), "sessionId": "s1", "startedAt": procs.started_at(os.getpid()) * 1000}, f)
        self.assertTrue(agents.claude_running("s1", d))

    def test_open_elsewhere_files_it_in_the_archive_rather_than_dropping_it(self):  # R6
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "workspace_label": "W", "state": "suspended",
            "at": T0}}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p2", session="s1")])), \
                mock.patch.object(agents, "claude_running", return_value=True), \
                mock.patch.object(agents, "session_facts", return_value={
                    "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}):
            self.assertIn("somewhere else", suspend.mark_waking("default", "w1:p1"))
        self.assertIn("claude:s1", store.load_archive()["entries"])

    def test_a_stale_listing_elsewhere_doesnt_block_the_resume(self):  # review 5 R96
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "workspace_label": "W", "state": "suspended",
            "at": T0}}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p2", session="s1")])), \
                mock.patch.object(agents, "claude_running", return_value=False):  # Claude says it isn't running
            self.assertEqual(suspend.mark_waking("default", "w1:p1"), "")

    def test_no_answer_from_herdr_is_no_resume(self):  # R7
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "agent": "codex", "session_id": "t1", "state": "suspended", "at": T0}}}}})
        with mock.patch.object(herdr, "snapshot", side_effect=herdr.HerdrError("busy")):
            self.assertEqual(suspend.mark_waking("default", "w1:p1"), suspend.NO_ANSWER)
        self.assertEqual(suspend.record("default", "w1:p1")["state"], "suspended")

    def test_the_placeholder_stays_and_retries_when_herdr_didnt_answer(self):  # R7
        rec = {"agent": "codex", "session_id": "t1", "state": "suspended", "at": T0}
        answers = iter([suspend.NO_ANSWER, ""])

        class NoTerminal:
            def __init__(self, fd):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with mock.patch.object(suspend, "record", return_value=rec), \
                mock.patch.object(suspend, "mark_waking", side_effect=lambda *a, **k: next(answers)), \
                mock.patch.object(placeholder, "Terminal", NoTerminal), \
                mock.patch.object(placeholder, "wait_for_key", return_value="resume") as wait, \
                mock.patch.object(placeholder, "unmark"), \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(sys, "stdout"):
            self.assertEqual(placeholder.main("default", "w1:p1"), 0)
        self.assertEqual(wait.call_count, 2)
        self.assertEqual(wait.call_args_list[1].args[-1], suspend.NO_ANSWER)

    def test_a_users_exit_over_a_stale_record_is_archived(self):  # R15
        index = {"sessions": {"default": {"panes": {"w1:p1": {
            "pane_id": "w1:p1", "session_id": "s1", "agent": "claude", "workspace_id": "w1", "workspace_label": "W",
            "since": T0 + 100}}, "suspended": {"w1:p1": {"pane_id": "w1:p1", "agent": "claude", "session_id": "s1",
                                                         "state": "suspended", "at": T0}}}}}
        archive = {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value={
                "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}), \
                mock.patch.object(core, "_drop_screen"):
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.agent_detected",
                       {"pane_id": "w1:p1", "released": True}, T0 + 200)
        self.assertEqual(archive["entries"]["claude:s1"]["reason"], "exited")
        self.assertEqual(index["sessions"]["default"]["suspended"], {})

    def test_right_after_a_restart_a_missing_pane_isnt_archived_yet(self):  # R21
        index = {"sessions": {"default": {"panes": {}, "boot": T0, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "state": "suspended", "at": T0 - 600}}}}}
        archive = {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value={
                "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}), \
                mock.patch.object(core, "_drop_screen"):
            core.apply(index, archive, "default", snap([]), "pane.focused", {}, T0 + 5)
            self.assertIn("w1:p1", index["sessions"]["default"]["suspended"])
            core.apply(index, archive, "default", snap([]), "pane.focused", {}, T0 + core.BOOT_GRACE + 5)
        self.assertEqual(archive["entries"]["claude:s1"]["reason"], "closed")

    def test_a_tab_back_after_the_restart_and_then_closed_is_archived_at_once(self):  # R21, narrowed
        index = {"sessions": {"default": {"panes": {}, "boot": T0, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "state": "suspended", "at": T0 - 600}}}}}
        archive = {"entries": {}}
        with mock.patch.object(agents, "session_facts", return_value={
                "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}), \
                mock.patch.object(core, "_drop_screen"):
            core.apply(index, archive, "default", snap([pane("w1:p1", session=None)]), "pane.focused", {}, T0 + 3)
            core.apply(index, archive, "default", snap([]), "tab.closed", {}, T0 + 10)
        self.assertEqual(archive["entries"]["claude:s1"]["reason"], "closed")


# ------------------------------------------------------------ the key

class KeyNotificationTests(StateDir):
    def test_messages_say_what_happened(self):  # R22, R8, review 3 R64 (Earmark's own popup)
        for why, title in ((suspend.CONFIRM + "Earmark can't read its prompt", "anyway?"),
                           (suspend.NOT_YET, "Suspended"), ("it's working", "can't suspend")):
            with mock.patch.object(suspend, "suspend_pane", return_value=why), \
                    mock.patch.object(suspend, "record", return_value=None), \
                    mock.patch.object(suspend.message, "show") as show:
                suspend.manual("default", "w1:p1", dict(CFG, suspend=dict(CFG["suspend"], when="manual")))
            self.assertIn(title, show.call_args.args[0], why)
            self.assertEqual(bool(show.call_args.kwargs.get("ask")), why.startswith(suspend.CONFIRM))


# ------------------------------------------------------------- tab marks

class TabMarkSafetyTests(unittest.TestCase):
    def test_a_name_starting_with_a_dash_never_reaches_herdrs_argv(self):  # R14
        with mock.patch.object(herdr, "run") as run:
            suspend.unmark_tab("w1:t1", "💤 -h", "💤")
            suspend.unmark_tab("w1:t1", "💤 --remote=x", "💤")
        run.assert_not_called()
        s = snap([pane("w1:p1", tab="w1:t1")])
        s["tabs"]["w1:t1"]["label"] = "💤 -h"
        self.assertEqual(suspend.stale_marks(s, {}, {"w1:t1": "💤"}), [])  # and isn't retried every hook

    def test_a_tab_without_a_name_isnt_marked(self):  # R14
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1")), \
                mock.patch.object(herdr, "run", return_value={"tab": {"label": ""}}) as run:
            suspend.mark_tab("default", "w1:p1", "💤")
        self.assertNotIn(("tab", "rename"), [c.args[:2] for c in run.call_args_list])


# ---------------------------------------------------- reopen, restore, parser

class ReopenFolderTests(StateDir):
    def test_reopen_brings_the_sessions_claude_folder(self):  # R16
        entry = {"key": "claude:s1", "agent": "claude", "session_id": "s1", "workspace_id": "w1",
                 "workspace_label": "Work", "cwd": "/proj", "config_dir": "/home/me/.claude-alt"}
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(herdr, "new_tab", return_value=("w1:t9", "w1:p9")), \
                mock.patch.object(herdr, "run") as run:
            self.assertIsNone(core.reopen(entry, {"workspace_id": "w1"}, CFG))
        typed = next(c.args[3] for c in run.call_args_list if c.args[:2] == ("pane", "run"))
        self.assertEqual(typed, "CLAUDE_CONFIG_DIR=/home/me/.claude-alt command claude --resume s1")


class ParserTests(unittest.TestCase):
    def test_the_fallback_parser_matches_tomllib_on_non_ascii(self):  # R17
        text = 'tab_mark = "⏸"\nname = "Café \\u00e9\\t\\"q\\""\nlist = ["é", "x\\u00e9"]\n'
        fallback = config.parse_simple_toml(text)
        self.assertEqual(fallback, {"tab_mark": "⏸", "name": 'Café é\t"q"', "list": ["é", "xé"]})
        if config.tomllib:
            self.assertEqual(fallback, config.tomllib.loads(text))


# ----------------------------------------------------------------- timers

class TimerEdgeTests(unittest.TestCase):
    def test_a_one_shot_task_counts_for_a_day_only(self):  # R19
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "assistant", "timestamp": iso(T0), "message": {"content": [
                    {"type": "tool_use", "name": "CronCreate", "input": {"recurring": False}}]}}) + "\n")
            self.assertEqual(agents.claude_timers(path, 0, {}, T0 + 3600)[1], 1)
            self.assertEqual(agents.claude_timers(path, 0, {}, T0 + 25 * 3600)[1], 0)

    def test_an_unknown_start_time_counts_every_timer(self):  # R19
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "assistant", "timestamp": iso(T0 - 600), "message": {"content": [
                    {"type": "tool_use", "name": "ScheduleWakeup", "input": {"delaySeconds": 3600}}]}}) + "\n")
            self.assertGreater(agents.claude_timers(path, 0, {}, T0)[0], T0)


# -------------------------------------------------------------- the hooks

class HookSchedulingTests(StateDir):
    def run_hook(self, event="pane.focused", data=None, panes=None, available=50.0):
        panes = panes if panes is not None else [pane("w1:p1")]
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes)), \
                mock.patch.object(herdr, "process_info", return_value={}), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(agents, "session_facts", return_value={
                    "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}), \
                mock.patch.object(procs, "available_percent", return_value=available), \
                mock.patch.object(suspend, "spawn_worker", return_value=True) as spawn, \
                mock.patch.object(suspend, "wake_on_view") as wake:
            core.handle_event(event, {"data": data or {}}, env={})
        return spawn, wake

    def test_time_mode_checks_at_most_once_a_minute(self):
        self.settings('[suspend]\nwhen = "time"\n')
        with mock.patch.object(core, "now", return_value=T0):
            spawn, _ = self.run_hook()
        spawn.assert_called_once_with([])
        with mock.patch.object(core, "now", return_value=T0 + 30):
            spawn, _ = self.run_hook()
        spawn.assert_not_called()
        with mock.patch.object(core, "now", return_value=T0 + suspend.CHECK_EVERY + 1):
            spawn, _ = self.run_hook()
        spawn.assert_called_once()

    def test_manual_mode_never_checks(self):
        self.settings('[suspend]\nwhen = "manual"\n')
        spawn, _ = self.run_hook()
        spawn.assert_not_called()

    def test_memory_mode_where_it_cant_act_starts_nothing(self):  # R12
        self.settings('[suspend]\nwhen = "memory"\n')
        spawn, _ = self.run_hook(available=None)
        spawn.assert_not_called()

    def test_resume_on_view_presses_for_a_suspended_tab_only(self):
        self.settings('[suspend]\nwhen = "manual"\nresume_on = "view"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p2": {
            "pane_id": "w1:p2", "agent": "claude", "session_id": "s2", "state": "suspended", "at": T0}}}}})
        panes = [pane("w1:p1"), pane("w1:p2", session=None)]
        _, wake = self.run_hook(data={"pane_id": "w1:p2"}, panes=panes)
        wake.assert_called_once_with("default", "w1:p2")
        _, wake = self.run_hook(data={"pane_id": "w1:p1"}, panes=panes)
        wake.assert_not_called()
        self.settings('[suspend]\nwhen = "manual"\nresume_on = "enter"\n')  # not asked for: never
        _, wake = self.run_hook(data={"pane_id": "w1:p2"}, panes=panes)
        wake.assert_not_called()

    def test_a_restart_request_survives_a_worker_that_wont_start(self):  # R20
        self.settings('[suspend]\nwhen = "manual"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "rearm": True, "suspended": {}}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(suspend, "spawn_worker", return_value=False):
            core.handle_event("pane.focused", {"data": {}}, env={})
        self.assertTrue(store.load_index()["sessions"]["default"].get("rearm"))


class MemoryModeTests(StateDir):
    def test_nothing_to_do_means_no_looks(self):  # R12
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="memory", memory_below=20))
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(procs, "available_percent", return_value=80.0), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), \
                mock.patch.object(core, "settle_now"):
            suspend.auto("default", cfg)
        look.assert_not_called()


# ------------------------------------------------------- the placeholder

class EarlyKeyTests(unittest.TestCase):
    def test_a_key_pressed_while_the_placeholder_starts_counts(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        os.write(master, b"\r")  # before the placeholder takes the terminal
        time.sleep(0.05)
        with mock.patch.object(sys, "stdout"), placeholder.Terminal(slave):
            self.assertEqual(placeholder.wait_for_key({"agent": "claude", "tab_label": "t", "at": T0}, CFG, "", slave),
                             "resume")


class WaitForKeyTests(unittest.TestCase):
    """wait_for_key on a real pseudo-terminal (its key mapping was untested)."""

    def press(self, data):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        tty.setraw(slave)  # as placeholder.Terminal does: keys arrive one by one
        os.write(master, data)
        with mock.patch.object(sys, "stdout"):
            return placeholder.wait_for_key({"agent": "claude", "tab_label": "t", "at": T0}, CFG, "", slave)

    def test_keys(self):
        self.assertEqual(self.press(b"\x03"), "leave")
        self.assertEqual(self.press(b"\x1b[I\r"), "resume")  # focus report, then Enter
        self.assertEqual(self.press(b"\x1b[A\x1b[B\x1b[13u"), "resume")  # arrows, then kitty Enter

    def test_key_action(self):
        self.assertEqual(placeholder.key_action(b"\x1b[I"), None)
        self.assertEqual(placeholder.key_action(b"x"), None)
        self.assertEqual(placeholder.key_action(b"\x03\r"), "leave")  # Ctrl+C wins


# --------------------------------------------- herdr.py on a fake Herdr program

FAKE_HERDR = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HERDR_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
def out(result):
    print(json.dumps({"id": "x", "result": result}))
if args[:2] == ["api", "snapshot"]:
    out({"type": "session_snapshot", "snapshot": {
        "panes": [{"pane_id": "w1:p1", "workspace_id": "w1", "tab_id": "w1:t1"}],
        "workspaces": [{"workspace_id": "w1", "label": "Work"}],
        "tabs": [{"tab_id": "w1:t1", "label": "a"}],
        "agents": [], "layouts": [], "focused_pane_id": "w1:p1"}})
elif args[:2] == ["api", "snapshot-broken"]:
    out({"type": "session_snapshot", "snapshot": {"panes": "nope"}})
elif args[:2] == ["pane", "list"]:
    out({"panes": [{"pane_id": "w1:p1", "workspace_id": "w1", "tab_id": "w1:t1"}]})
elif args[:2] == ["workspace", "list"]:
    out({"workspaces": [{"workspace_id": "w1", "label": "Work"}]})
elif args[:2] == ["tab", "list"]:
    out({"tabs": [{"tab_id": "w1:t1", "label": "a"}]})
elif args[:2] == ["pane", "process-info"]:
    out({"process_info": {"shell_pid": 1, "foreground_process_group_id": 1, "foreground_processes": [None, {"pid": 1}]}})
elif args[:2] == ["pane", "read"]:
    sys.stdout.write("line one\r\nline two\r\n")
elif args[:2] == ["tab", "create"]:
    out({"tab": {"tab_id": "w1:t2"}, "root_pane": {"pane_id": "w1:p2"}})
elif args[:2] == ["pane", "get"] and args[2] == "broken":
    print(json.dumps({"id": "x", "error": {"code": "pane_not_found"}}))
elif args[:2] == ["pane", "get"]:
    sys.exit(3)
else:
    out({})
'''


class TransportTests(unittest.TestCase):
    """herdr.py itself, on a fake `herdr` program (it never ran in a test)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        binary = os.path.join(self.dir.name, "herdr")
        with open(binary, "w") as f:
            f.write(FAKE_HERDR)
        os.chmod(binary, stat.S_IRWXU)
        self.log = os.path.join(self.dir.name, "log")
        p = mock.patch.dict(os.environ, {"HERDR_BIN_PATH": binary, "FAKE_HERDR_LOG": self.log})
        p.start()
        self.addCleanup(p.stop)

    def calls(self):
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def test_snapshot_and_replies(self):
        s = herdr.snapshot()
        self.assertEqual((list(s["panes"]), list(s["workspaces"]), list(s["tabs"])), (["w1:p1"], ["w1"], ["w1:t1"]))
        self.assertNotIn("focused_pane_id", s)  # nothing reads it
        self.assertEqual(self.calls(), [["api", "snapshot"]])  # one call, one moment (K1)
        self.assertEqual(herdr.process_info("w1:p1")["foreground_processes"], [{"pid": 1}])  # odd entries dropped
        self.assertEqual(herdr.read_screen("w1:p1"), "line one\nline two\n")  # text, not JSON; CRLF folded
        self.assertEqual(herdr.new_tab("w1", "/nonexistent", "-h"), ("w1:t2", "w1:p2"))
        self.assertNotIn("--label", self.calls()[-1])  # a name starting with "-" never reaches the argv
        with self.assertRaises(herdr.HerdrError):
            herdr.pane("broken")  # an error reply
        with self.assertRaises(herdr.HerdrError):
            herdr.pane("w1:p1")  # a failing exit

    def test_a_snapshot_of_another_shape_is_a_herdr_error(self):
        real = herdr.run
        with mock.patch.object(herdr, "run", lambda *a, **k: real("api", "snapshot-broken")):
            with self.assertRaises(herdr.HerdrError):
                herdr.snapshot()

    def test_the_sidebar_token_puts_the_id_first(self):
        from earmark import sidebar
        sidebar.report("workspace", "w1", {"earmark_done": "2", "earmark_archived": None}, 7)
        call = self.calls()[-1]
        self.assertEqual(call[:4], ["workspace", "report-metadata", "w1", "--source"])
        self.assertIn("earmark_done=2", call)  # one argument: a value can't pass for an option
        self.assertEqual(call[call.index("--clear-token") + 1], "earmark_archived")
        self.assertEqual(call[call.index("--seq") + 1], "7")


class ProcessFactsTests(unittest.TestCase):
    @unittest.skipUnless(procs.linux(), "Linux /proc")
    def test_start_time_and_token_of_a_real_process(self):
        me = os.getpid()
        self.assertIsNotNone(procs.start_token(me))
        self.assertLess(abs(procs.started_at(me) - time.time()), 24 * 3600)
        self.assertEqual(procs.Table().ppid(me), os.getppid())
        self.assertIsNone(procs.start_token(2 ** 22 + 12345))


if __name__ == "__main__":
    unittest.main()
