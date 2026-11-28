"""Tests for strict review 2 (docs/PLAN.md R27-R52): one per finding, and one
per mutation the reviewers' own runs showed surviving. Run:
python3 -m unittest discover tests

Made-up snapshots, process tables, transcripts and terminals; nothing
touches a running Herdr or a real process."""
import io
import json
import os
import pty
import signal
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, herdr, placeholder, procs, store, suspend, ui  # noqa: E402
from test_suspend import (CFG, T0, SuspendPaneTests, agent_info, claude_screen, found, ph_info, pane,  # noqa: E402
                          shell_info, snap, typed)
from test_review1 import CFG_TIME, StateDir, iso  # noqa: E402

CFG_SIDEBAR = dict(config.DEFAULTS, sidebar=dict(config.SIDEBAR_DEFAULTS), colors=dict(config.COLOR_DEFAULTS))

FACTS = {"known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}


def put(**kw):
    rec = {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "workspace_label": "Work",
           "agent": "claude", "session_id": "s1", "state": "suspended", "at": T0, "cwd": "/proj",
           "resume": ["command", "claude", "--resume", "s1"],
           "base": {"screen": "shell", "at": 0}}  # its shell seen back a while ago, unchanged since
    rec.update(kw)
    store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": rec}}}})
    return rec


class NoTerminal:
    def __init__(self, fd):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


# ------------------------------------------------------------- the stop

class StopMoreTests(SuspendPaneTests):
    def kill_log(self):
        return [e for e in self.events if e[0] == "kill"]

    def test_the_record_written_by_someone_else_first_wins(self):  # under-lock re-check
        def look_and_race(p, note, table, t, timers):
            put(state="suspended")  # another worker got there between our checks
            return self.fake_look(p, note, table, t, timers)
        with mock.patch.object(suspend, "look", side_effect=look_and_race), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True),
                             "it's already suspended")
        self.assertEqual(self.kill_log(), [])

    def test_a_split_sibling_in_view_at_the_last_moment(self):
        views = [snap([pane("w1:p1", tab="w1:t1")]),
                 snap([pane("w1:p1", tab="w1:t1"), pane("w1:p9", session=None, tab="w1:t1", focused=True)])]
        with mock.patch.object(suspend.herdr, "snapshot", side_effect=lambda: views.pop(0) if len(views) > 1 else views[0]), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False)
        self.assertIn("view", why)
        self.assertEqual(self.kill_log(), [])

    def test_in_view_at_the_look_is_refused_even_if_not_at_the_end(self):
        views = [snap([pane("w1:p1", tab="w1:t1"), pane("w1:p9", session=None, tab="w1:t1", focused=True)]),
                 snap([pane("w1:p1", tab="w1:t1")])]
        with mock.patch.object(suspend.herdr, "snapshot", side_effect=lambda: views.pop(0) if len(views) > 1 else views[0]), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG_TIME, "time", manual=False)
        self.assertIn("view", why)
        self.assertEqual(self.kill_log(), [])

    def test_the_record_never_keeps_the_mark(self):
        s = snap([pane("w1:p1")])
        s["tabs"]["w1:t1"]["label"] = "💤 tab"
        index = store.load_index()
        index["sessions"]["default"]["marked"] = {"w1:t1": "💤"}  # a split beside it is suspended
        store.save_index(index)
        with mock.patch.object(suspend.herdr, "snapshot", return_value=s), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True), "")
        self.assertEqual(suspend.record("default", "w1:p1")["tab_label"], "tab")

    def test_a_line_the_shell_cant_take_stops_nothing(self):  # fit L9
        with mock.patch.object(suspend.config, "config_dir", return_value="/home/a\\b/config"), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("can't be given safely", why)
        self.assertEqual(self.kill_log(), [])
        self.assertIsNone(suspend.record("default", "w1:p1"))

    def test_nothing_signalled_means_no_record_and_a_backoff(self):
        def refuse(pid, sig):
            raise PermissionError("not yours")
        with mock.patch.object(suspend.os, "kill", side_effect=refuse), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("may not stop it", why)
        self.assertIsNone(suspend.record("default", "w1:p1"))
        self.assertGreater(store.load_index()["sessions"]["default"]["panes"]["w1:p1"]["backoff_until"], T0)

    def test_an_automatic_stop_that_times_out_backs_off(self):
        self.exits = False
        clock = iter(range(int(T0), int(T0) + 200))
        with mock.patch.object(suspend.time, "time", side_effect=lambda: float(next(clock))):
            suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False)
        self.assertGreater(store.load_index()["sessions"]["default"]["panes"]["w1:p1"]["backoff_until"], T0)

    def test_the_signal_is_sigterm(self):
        sigs = []
        orig = self.fake_kill
        with mock.patch.object(suspend.os, "kill", side_effect=lambda pid, sig: (sigs.append(sig), orig(pid, sig))), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertEqual(sigs, [signal.SIGTERM])

    def test_a_record_a_hook_ended_meanwhile_gets_no_signal(self):  # R42
        def pane_and_end_it(pane_id):
            store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
            return self.fake_pane(pane_id)
        with mock.patch.object(suspend.herdr, "pane", side_effect=pane_and_end_it), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("record changed", why)
        self.assertEqual(self.kill_log(), [])

    def test_the_key_looks_at_the_status_right_before_the_signal(self):  # R44
        with mock.patch.object(suspend.herdr, "pane", return_value=pane("w1:p1", status="working")), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("busy", why)
        self.assertEqual(self.kill_log(), [])

    def test_unseen_and_the_agents_own_folder_are_recorded(self):
        p = dict(pane("w1:p1", status="done"), foreground_cwd="/fg", cwd="/proj")
        cfg = dict(CFG_TIME, suspend=dict(CFG_TIME["suspend"], suspend_unseen=True))
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([p])), \
                mock.patch.object(suspend.herdr, "pane", side_effect=lambda pid: dict(self.fake_pane(pid), agent_status="done")), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", cfg, "time", manual=False), "")
        rec = suspend.record("default", "w1:p1")
        self.assertEqual((rec["unseen"], rec["cwd"]), (True, "/fg"))


# ---------------------------------------------------------------- refusal

class RefusalMoreTests(unittest.TestCase):
    def test_automatic_modes_need_idle_or_unseen(self):
        self.assertIn("unknown", suspend.refusal(found(T0 - 7200), pane("w1:p1", status="unknown"), CFG_TIME, T0, False, None))

    def test_no_resume_command_no_suspend(self):
        f = found(T0 - 7200, agent="mystery")
        self.assertIn("doesn't know how to resume", suspend.refusal(f, pane("w1:p1", agent="mystery"), CFG_TIME, T0, True, None))

    def test_a_claude_whose_folder_cant_be_read(self):  # R47
        f = found(T0 - 7200, facts={"known": False, "exists": True, "has_content": True})
        self.assertIn("Claude folder", suspend.refusal(f, pane("w1:p1"), CFG_TIME, T0, False, None))

    def test_an_agent_earmark_cant_name_must_lead_its_terminal(self):  # R48
        f = found(T0 - 7200, agent="pi", leader_name="vim")
        self.assertIn("can't tell which process", suspend.refusal(f, pane("w1:p1", agent="pi"), CFG_TIME, T0, True, None))


# ------------------------------------------------------------- look() more

class LookMoreTests(unittest.TestCase):
    def look(self, processes, table, shell=10, agent="claude"):
        info = {"shell_pid": shell, "foreground_process_group_id": processes[0]["pid"], "foreground_processes": processes}
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "start_token", return_value="L"), \
                mock.patch.object(procs, "environ_var", return_value=""), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            return suspend.look(pane("w1:p1", agent=agent), {}, procs.Table(table), T0, {})

    def test_a_nested_shell_is_refused(self):  # R33
        f = self.look([{"pid": 50, "name": "claude", "argv": ["claude"]}],
                      {10: (1, "zsh", "zsh"), 20: (10, "bash", "bash"), 50: (20, "claude", "claude")})
        self.assertIn("nested shell", f["why"])

    def test_a_wrapper_counts_as_an_option_earmark_cant_bring_back(self):  # R36
        procs_ = [{"pid": 40, "name": "aws-vault", "argv": ["aws-vault", "exec", "--", "claude"]},
                  {"pid": 50, "name": "claude", "argv": ["claude"]}]
        f = self.look(procs_, {10: (1, "bash", "bash"), 40: (10, "aws-vault", "aws-vault"), 50: (40, "claude", "claude")})
        self.assertIn("(started through aws-vault)", f["unknown_flags"])

    def test_a_launchers_own_options_arent_the_agents(self):
        self.assertEqual(agents.launch_flags("claude", ["node", "--no-warnings", "/x/cli.js", "--model", "m"]),
                         (["--model", "m"], []))

    def test_node_launching_codex_is_no_wrapper(self):
        procs_ = [{"pid": 60, "name": "node", "argv": ["node", "/x/codex.js"]}, {"pid": 61, "name": "codex", "argv": ["codex"]}]
        f = self.look(procs_, {10: (1, "bash", "bash"), 60: (10, "node", "node"), 61: (60, "codex", "codex")}, agent="codex")
        self.assertEqual(f["unknown_flags"], [])

    def test_shells_deeper_down_and_login_shells_are_work(self):
        t = procs.Table({50: (1, "claude", "claude"), 60: (50, "node", "node"), 61: (60, "bash", "bash -c x")})
        self.assertIn("bash", t.busy([50]))
        t = procs.Table({50: (1, "claude", "claude"), 60: (50, "-bash", "-bash")})
        self.assertIn("bash", t.busy([50]))

    def test_swapped_out_memory_counts(self):
        with mock.patch.object(procs, "_status", return_value=io.StringIO("VmRSS:\t100 kB\nVmSwap:\t50 kB\n")):
            self.assertEqual(procs.memory_kb([1]), 150)


# --------------------------------------------------------------- options

class OptionTests(unittest.TestCase):
    def test_a_value_that_cant_be_typed_safely_isnt_kept(self):  # R30
        kept, unknown = agents.launch_flags("claude", ["claude", "--append-system-prompt", "one\ntwo", "--model", "m"])
        self.assertEqual(kept, ["--model", "m"])
        self.assertEqual(unknown, ["--append-system-prompt=…"])
        for bad in ("a'b", "a\\b", "a\tb", "a\x1bb"):
            self.assertTrue(agents.launch_flags("claude", ["claude", "--model", bad])[1], bad)

    def test_codex_options_go_before_the_session_id(self):
        self.assertEqual(agents.live_resume_argv("codex", "t1", {}, ["-s", "read-only"], ""),
                         ["command", "codex", "--no-daemon", "resume", "-s", "read-only", "t1"])

    def test_resume_goes_round_a_users_alias(self):  # R32
        self.assertEqual(agents.resume_argv("claude", "abc")[:2], ["command", "claude"])
        line = suspend.placeholder_command("default", "w1:p1", put())
        self.assertIn("&& cd /proj && command claude --resume s1", line)

    def test_shell_safety_checks(self):
        self.assertEqual(agents.env_prefix("claude", "/a'b"), "")
        self.assertEqual(agents.env_prefix("claude", "/a\\b"), "")
        self.assertFalse(agents.safe_session_id("ab\\c"))
        self.assertNotIn("cd ", suspend.resume_command({"cwd": "/w/a\\b", "resume": ["claude"]}))

    def test_a_mark_with_a_space_is_refused(self):
        self.assertEqual(config.suspend_settings({"tab_mark": "z z"})["tab_mark"], "💤")


# ------------------------------------------------------------- the screen

class DraftMoreTests(unittest.TestCase):
    RULE = "─" * 30

    def test_the_last_box_counts(self):
        screen = "\n".join(["out", self.RULE, "❯ an old draft", self.RULE, "more", self.RULE, "❯ ", self.RULE])
        self.assertEqual(agents.draft_text(screen, "claude"), "")

    def test_hints_end_where_their_style_ends(self):
        for sgr in ("0", "22"):
            screen = "\n".join([self.RULE, f"❯ \x1b[2mhint\x1b[{sgr}mtyped", self.RULE])
            self.assertEqual(agents.draft_text(screen, "claude"), "typed", sgr)
        screen = "\n".join([self.RULE, "❯ \x1b[3mTry this\x1b[0m", self.RULE])  # italic is a hint too
        self.assertEqual(agents.draft_text(screen, "claude"), "")


# ----------------------------------------------------------------- timers

class TimerMoreTests(unittest.TestCase):
    def write(self, path, records, mode="w"):
        with open(path, mode) as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def call(self, name, stamp, **args):
        return {"type": "assistant", "timestamp": iso(stamp), "message": {"content": [
            {"type": "tool_use", "name": name, "input": args}]}}

    def test_a_stop_ends_the_loop_even_with_a_delay(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            self.write(path, [self.call("ScheduleWakeup", T0 - 60, delaySeconds=600, stop=True)])
            self.assertEqual(agents.claude_timers(path, 0, {}, T0)[0], 0)

    def test_a_new_agent_process_starts_the_count_again(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            self.write(path, [self.call("CronCreate", T0 - 600)])
            cache = {}
            self.assertEqual(agents.claude_timers(path, T0 - 900, cache, T0)[1], 1)
            self.assertEqual(agents.claude_timers(path, T0 - 300, cache, T0)[1], 0)  # restarted after it

    def test_a_rewritten_transcript_is_read_again(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            self.write(path, [{"type": "user", "pad": "x" * 500}] * 10)
            cache = {}
            agents.claude_timers(path, 0, cache, T0)
            self.write(path, [self.call("CronCreate", T0 - 60)])  # shorter now
            self.assertEqual(agents.claude_timers(path, 0, cache, T0)[1], 1)

    def test_a_long_transcript_keeps_the_agent_awake_until_read(self):  # R51
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            self.write(path, [{"type": "user", "pad": "x" * 100}] * 20)
            cache = {}
            with mock.patch.object(agents, "TIMER_READ", 500):
                agents.claude_timers(path, 0, cache, T0)
            self.assertTrue(cache["behind"])

    def test_each_herdr_session_keeps_its_own_offsets(self):  # R50
        self.assertNotEqual(suspend.timers_file("default"), suspend.timers_file("other"))


# ------------------------------------------------------------- choosing

class ChooseMoreTests(unittest.TestCase):
    def test_memory_mode_stops_at_max_per_check(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="memory", memory_below=20))
        looks = [(pane(f"w1:p{i}", session=f"s{i}"), {}, found(T0 - 3600, pane_id=f"w1:p{i}", session_id=f"s{i}",
                                                               memory_kb=1)) for i in range(10)]
        self.assertEqual(len(suspend.choose(looks, cfg, T0, available=5.0, total_kb=10_000_000)), suspend.MAX_PER_CHECK)


# ------------------------------------------------------- arming and rearming

class ArmMoreTests(StateDir):
    def test_only_suspended_or_waking_records_are_armed(self):
        put(state="stopping")
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertFalse(typed(run))

    def test_never_into_the_tab_in_view_unless_asked(self):  # R35
        put()
        p = pane("w1:p1", session=None, focused=True)
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=p), \
                mock.patch.object(herdr, "snapshot", return_value=snap([p])), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertFalse(typed(run))

    def test_no_claim_where_something_else_runs(self):
        put()
        with mock.patch.object(herdr, "process_info", return_value=agent_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(store, "save_index") as save, \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertFalse(typed(run))
        save.assert_not_called()  # a check every minute mustn't rewrite index.json for nothing

    def test_it_looks_again_after_the_claim(self):  # R35
        put()
        infos = [shell_info(), agent_info()]  # the user started something meanwhile
        with mock.patch.object(herdr, "process_info", side_effect=lambda pid: infos.pop(0) if infos else agent_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertFalse(typed(run))
        self.assertEqual(suspend.record("default", "w1:p1")["arming"], 0)

    def test_a_pane_id_now_in_another_tab_archives_the_record(self):  # R37
        put()
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None, tab="w1:t9")), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None, tab="w1:t9")])), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertFalse(typed(run))
        self.assertIsNone(suspend.record("default", "w1:p1"))
        self.assertIn("claude:s1", store.load_archive()["entries"])

    def test_after_a_restart_herdrs_own_restore_goes_first(self):  # R27
        rec = put()
        index = store.load_index()
        index["sessions"]["default"]["boot"] = time.time()
        index["sessions"]["default"]["panes"]["w1:p1"] = {"session_id": "s1"}
        store.save_index(index)
        with mock.patch.object(herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None)), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1", restart=True))
        self.assertFalse(typed(run))
        self.assertTrue(suspend.herdr_may_relaunch("default", "w1:p1", rec))

    def test_rearm_all_once_per_restart_and_more_than_one_pass(self):
        put(armed_by_rearm=True)
        with mock.patch.object(suspend, "check_pane") as check:
            suspend.rearm_all("default")
        check.assert_not_called()
        put()
        answers = iter([False, True])
        clock = iter(range(int(T0), int(T0) + 1000, 5))

        def check(session, pid, rec, p, restart=False):
            ok = next(answers, True)
            if ok:
                suspend._set_state(session, pid, armed_by_rearm=True)
            return ok
        with mock.patch.object(suspend, "check_pane", side_effect=check) as cp, \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(suspend.time, "time", side_effect=lambda: float(next(clock))):
            suspend.rearm_all("default")
        self.assertEqual(cp.call_count, 2)
        self.assertTrue(all(c.kwargs.get("restart") is True for c in cp.call_args_list))  # arm knows it's a restart

    def test_another_session_in_its_pane_archives_the_suspended_one(self):  # R41
        put()
        sessions = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "sessions")
        os.makedirs(sessions, exist_ok=True)
        with open(os.path.join(sessions, "50.json"), "w") as f:
            json.dump({"pid": 50, "sessionId": "s2", "status": "idle"}, f)
        info = {"shell_pid": 1, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        rec = suspend.record("default", "w1:p1")
        self.assertEqual(suspend.resumed_by_herdr(rec, pane("w1:p1"), info), "other")
        with mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)):
            suspend.check_pane("default", "w1:p1", rec, pane("w1:p1"))
        self.assertEqual(store.load_archive()["entries"]["claude:s1"]["reason"], "replaced")
        os.unlink(os.path.join(sessions, "50.json"))


class MarkTests(StateDir):
    def test_a_marked_tab_isnt_marked_twice(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1")), \
                mock.patch.object(herdr, "run", return_value={"tab": {"label": "💤 auth"}}) as run:
            suspend.mark_tab("default", "w1:p1", "💤")
        self.assertNotIn(("tab", "rename"), [c.args[:2] for c in run.call_args_list])


class RegistryTests(StateDir):
    def test_a_dead_pid_in_claudes_registry_isnt_running(self):
        sessions = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "sessions")
        os.makedirs(sessions, exist_ok=True)
        path = os.path.join(sessions, "4242.json")
        with open(path, "w") as f:
            json.dump({"pid": 4242, "sessionId": "s1", "startedAt": T0 * 1000}, f)
        self.addCleanup(os.unlink, path)
        with mock.patch.object(agents.os, "kill", side_effect=ProcessLookupError), \
                mock.patch.object(procs, "started_at", return_value=None):
            self.assertFalse(agents.claude_running("s1"))


class KeyMoreTests(StateDir):
    def test_the_key_notices_an_agent_running_again(self):  # R43
        put()
        info = {"shell_pid": 1, "foreground_process_group_id": 50,
                "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="manual"))
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1")), \
                mock.patch.object(herdr, "process_info", return_value=info), \
                mock.patch.object(suspend, "suspend_pane", return_value="") as act, \
                mock.patch.object(suspend, "arm") as arm, \
                mock.patch.object(herdr, "notify"):
            suspend.manual("default", "w1:p1", cfg)
        arm.assert_not_called()
        act.assert_called_once()
        self.assertIsNone(suspend.record("default", "w1:p1"))

    def test_the_key_on_a_stopping_record_doesnt_arm(self):
        put(state="stopping")
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="manual"))
        with mock.patch.object(suspend, "arm") as arm, \
                mock.patch.object(suspend, "suspend_pane", return_value="it's already suspended"), \
                mock.patch.object(herdr, "notify"):
            suspend.manual("default", "w1:p1", cfg)
        arm.assert_not_called()

    def test_a_broken_config_says_so(self):  # R51
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="manual"), _broken="line 3")
        with mock.patch.object(suspend, "suspend_pane") as act, mock.patch.object(suspend.message, "show") as show:
            suspend.manual("default", "w1:p9", cfg)
        act.assert_not_called()
        self.assertIn("config.toml", show.call_args.args[0])

    def test_y_confirms_through_suspend_pane_with_the_doubt_shown(self):  # review 3 R64
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="manual"))
        with mock.patch.object(suspend.config, "load", return_value=cfg), \
                mock.patch.object(suspend, "suspend_pane", return_value="") as act:
            self.assertEqual(suspend.confirm("default", "w1:p1", "the doubt"), "")
        self.assertEqual(act.call_args.kwargs["accept"], "the doubt")
        off = dict(CFG, suspend=dict(CFG["suspend"], when="off"))
        with mock.patch.object(suspend.config, "load", return_value=off), \
                mock.patch.object(suspend, "suspend_pane") as act:  # suspending off meanwhile
            self.assertIn("off", suspend.confirm("default", "w1:p1", "the doubt"))
        act.assert_not_called()


class ViewResumeTests(StateDir):
    def test_only_a_suspended_record_and_not_twice_in_a_row(self):
        put(state="waking")
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None, focused=True)), \
                mock.patch.object(suspend, "press_enter") as enter:
            suspend.wake_on_view("default", "w1:p1")
        enter.assert_not_called()
        put()
        with mock.patch.object(herdr, "pane", return_value=pane("w1:p1", session=None, focused=True)), \
                mock.patch.object(suspend, "press_enter") as enter:
            suspend.wake_on_view("default", "w1:p1")
            suspend.wake_on_view("default", "w1:p1")
        self.assertEqual(enter.call_count, 1)


# ---------------------------------------------------------------- auto()

class AutoMoreTests(StateDir):
    def test_a_suspended_pane_isnt_looked_at(self):
        put()
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_not_called()

    def test_a_settings_change_mid_check_stops_it(self):
        self.settings('[suspend]\nwhen = "time"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        looks = [(pane(f"w1:p{i}", session=f"s{i}"), {}, found(T0 - 7200, pane_id=f"w1:p{i}")) for i in (1, 2)]
        calls = []

        def act(session, pid, cfg, reason, manual, min_idle=0):
            calls.append(pid)
            self.settings('[suspend]\nwhen = "manual"\n')
            path = config.config_path()
            os.utime(path, (time.time() + 100, time.time() + 100))
            return ""
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(suspend, "choose", return_value=looks), \
                mock.patch.object(suspend, "suspend_pane", side_effect=act), \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        self.assertEqual(calls, ["w1:p1"])

    def test_back_from_a_long_silence_nothing_is_suspended_at_once(self):  # R34
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}, "quiet_until": time.time() + 300}}})
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", CFG_TIME)
        look.assert_not_called()

    def test_a_broken_config_suspends_nothing(self):  # R51
        cfg = dict(CFG_TIME, _broken="bad")
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend, "look") as look, \
                mock.patch.object(suspend, "rearm_pass"), mock.patch.object(core, "settle_now"):
            suspend.auto("default", cfg)
        look.assert_not_called()


# ------------------------------------------------------------- the hooks

class HookMoreTests(StateDir):
    def hook(self, event="pane.focused", data=None, panes=None, t=T0):
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes if panes is not None else [pane("w1:p1")])), \
                mock.patch.object(herdr, "process_info", return_value={}), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(core, "now", return_value=t), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True), \
                mock.patch.object(suspend, "wake_on_view") as wake:
            core.handle_event(event, {"data": data or {}}, env={})
        return wake

    def test_identical_hooks_dont_rewrite_the_index(self):  # R40
        self.hook(t=T0)
        with mock.patch.object(store, "save_index", wraps=store.save_index) as save:
            self.hook(t=T0 + 5)
            self.hook(t=T0 + 10)
        self.assertEqual(save.call_count, 0)

    def test_a_long_silence_starts_the_return_grace(self):  # R34
        self.settings('[suspend]\nwhen = "time"\n')
        self.hook(t=T0)
        self.hook(t=T0 + suspend.AWAY_GAP + 60)
        s = store.load_index()["sessions"]["default"]
        self.assertGreater(s["quiet_until"], T0 + suspend.AWAY_GAP)

    def test_a_waking_tab_gets_no_view_resume(self):
        self.settings('[suspend]\nwhen = "manual"\nresume_on = "view"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p2": {
            "pane_id": "w1:p2", "agent": "claude", "session_id": "s2", "state": "waking", "at": T0}}}}})
        wake = self.hook(data={"pane_id": "w1:p2"}, panes=[pane("w1:p2", session=None)])
        wake.assert_not_called()

    def test_a_broken_config_never_prunes(self):  # R51
        self.settings("this is = = not toml\n")
        store.save_archive({"entries": {"claude:old": {"herdr_session": "default", "workspace_label": "W",
                                                       "agent": "claude", "session_id": "old", "last_active": 0}}})
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS, exists=False)):
            with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                    mock.patch.object(core, "send_reports"), mock.patch.object(suspend, "spawn_worker", return_value=True):
                core.handle_event("startup", {"data": {}}, env={})
        self.assertIn("claude:old", store.load_archive()["entries"])

    def test_only_tabs_earmark_marked_are_unmarked(self):  # R39
        p = pane("w1:p1", session=None)
        s = snap([p])
        s["tabs"][p["tab_id"]]["label"] = "💤 my own name"
        with mock.patch.object(herdr, "snapshot", return_value=s), \
                mock.patch.object(core, "send_reports"), \
                mock.patch.object(suspend, "unmark_tab") as unmark:
            core.handle_event("pane.focused", {"data": {}}, env={})
        unmark.assert_not_called()


# ------------------------------------------------------------ apply() more

class ApplyMoreTests(unittest.TestCase):
    def setUp(self):
        self.index, self.archive = {"sessions": {}}, {"entries": {}}
        f = mock.patch.object(agents, "session_facts", return_value=dict(FACTS))
        f.start()
        self.addCleanup(f.stop)

    def apply(self, panes, t, event="pane.focused", data=None, workspaces=None):
        return core.apply(self.index, self.archive, "default", snap(panes, workspaces), event, data or {}, t)

    def test_a_split_beside_the_pane_in_use_is_on_screen(self):  # R29 (stamped as the tab is left: R71)
        a, b = pane("w1:p1", tab="w1:t1"), pane("w1:p2", session="s2", tab="w1:t1", focused=True)
        self.apply([a, b], T0)
        self.apply([a, b], T0 + 3600, event="pane.agent_status_changed")
        c = pane("w2:p3", session=None, ws="w1", tab="w1:t3", focused=True)
        self.apply([dict(a, focused=False), dict(b, focused=False), c], T0 + 7200)  # leave the tab
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["focused_at"], T0 + 7200)

    def test_other_herdr_sessions_are_kept_while_active(self):
        self.index["sessions"]["other"] = {"panes": {}, "seen": T0 - 3600}
        self.apply([], T0)
        self.assertIn("other", self.index["sessions"])

    def test_the_sessions_own_seen_is_refreshed(self):
        self.apply([], T0)
        self.apply([], T0 + 700)
        self.assertEqual(self.index["sessions"]["default"]["seen"], T0 + 700)

    def test_seen_is_refreshed_every_ten_minutes(self):
        self.apply([pane("w1:p1")], T0)
        self.apply([pane("w1:p1")], T0 + 100)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["seen"], T0)
        self.apply([pane("w1:p1")], T0 + 700)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["seen"], T0 + 700)

    def test_the_claude_folder_reaches_the_archive(self):
        p = dict(pane("w1:p1"), _config_dir="/cfg")
        self.apply([p], T0)
        self.apply([pane("w1:p1")], T0 + 10)  # carried between snapshots
        self.apply([], T0 + 20, event="pane.closed")
        self.assertEqual(self.archive["entries"]["claude:s1"]["config_dir"], "/cfg")

    def test_a_restart_resends_the_sidebar_tokens(self):
        cache = {"sessions": {}}
        s = snap([pane("w1:p1")])
        self.apply([pane("w1:p1")], T0)
        self.assertTrue(core.pending_reports(self.index, self.archive, "default", s, CFG_SIDEBAR, cache))
        self.assertEqual(core.pending_reports(self.index, self.archive, "default", s, CFG_SIDEBAR, cache), [])
        self.apply([pane("w1:p1")], T0 + 5, event="startup")  # tokens didn't survive the restart
        again = core.pending_reports(self.index, self.archive, "default", s, CFG_SIDEBAR, cache)
        self.assertEqual([(w, t) for w, t, _ in again], [("w1", {"earmark_done": "1"})])  # nothing to clear

    def test_tokens_are_sent_only_when_they_change(self):
        cache = {"sessions": {}}
        self.apply([pane("w1:p1")], T0)
        s = snap([pane("w1:p1")])
        self.assertEqual(len(core.pending_reports(self.index, self.archive, "default", s, CFG_SIDEBAR, cache)), 1)
        self.assertEqual(core.pending_reports(self.index, self.archive, "default", s, CFG_SIDEBAR, cache), [])
        working = snap([pane("w1:p1", status="working")])
        self.assertEqual([t for _, t, _ in core.pending_reports(self.index, self.archive, "default", working,
                                                                  CFG_SIDEBAR, cache)],
                         [{"earmark_blocked": None, "earmark_working": "1", "earmark_done": None,
                           "earmark_suspended": None, "earmark_archived": None, "earmark_note": None}])  # whole

    def test_a_workspace_of_plain_tabs_is_remembered(self):
        self.assertTrue(core.record_closed_workspace(self.archive, "default", "w1",
                                                     {"label": "W", "tabs": [{"label": "notes", "session_id": None}]}, T0))

    def test_right_after_a_restart_a_missing_workspace_isnt_closed_yet(self):  # R49
        self.apply([pane("w1:p1", session=None)], T0 - 600)
        self.apply([], T0, event="startup", workspaces={"w9": "Other"})
        self.assertNotIn("workspaces", {k for k, v in self.archive.items() if v})
        self.apply([], T0 + core.BOOT_GRACE + 5, workspaces={"w9": "Other"})
        self.assertEqual(len(self.archive.get("workspaces", {})), 1)

    def test_herdr_saying_it_closed_needs_no_grace(self):  # found by the live check
        self.apply([pane("w1:p1")], T0 - 600)
        self.apply([pane("w1:p1")], T0, event="startup")
        self.apply([], T0 + 5, event="workspace.closed", data={"workspace_id": "w1"}, workspaces={"w9": "Other"})
        self.assertEqual(len(self.archive.get("workspaces", {})), 1)
        self.assertEqual(self.archive["entries"]["claude:s1"]["reason"], "closed")

    def test_prune_drops_a_session_with_nothing_to_resume(self):
        archive = {"entries": {"claude:x": {"herdr_session": "default", "workspace_label": "W", "agent": "claude",
                                            "session_id": "x", "last_active": T0}}}
        with mock.patch.object(agents, "session_facts", return_value=dict(FACTS, has_content=False)):
            core.prune(archive, config.load(), T0)
        self.assertEqual(archive["entries"], {})


class ReopenRestoreTests(StateDir):
    def test_reopen_finds_its_workspace_by_name(self):
        entry = {"key": "claude:s1", "agent": "claude", "session_id": "s1", "workspace_id": "w1",
                 "workspace_label": "Work", "cwd": "/proj"}
        s = snap([], workspaces={"w1": "Other", "w2": "Work"})
        with mock.patch.object(herdr, "snapshot", return_value=s), \
                mock.patch.object(herdr, "new_tab", return_value=("w2:t1", "w2:p1")) as new_tab, \
                mock.patch.object(herdr, "run"):
            core.reopen(entry, {"workspace_id": "w1"}, CFG)
        self.assertEqual(new_tab.call_args.args[0], "w2")

    def test_reopen_never_twice(self):  # R45
        entry = {"key": "claude:s1", "agent": "claude", "session_id": "s1", "workspace_id": "w1",
                 "workspace_label": "Work"}
        with mock.patch.object(agents, "claude_running", return_value=True), \
                mock.patch.object(herdr, "new_tab") as new_tab:
            self.assertIn("open somewhere else", core.reopen(entry, {}, CFG))
        new_tab.assert_not_called()

    def test_restore_brings_a_suspended_tab_back_with_its_options(self):  # R46
        record = {"key": "k", "label": "Elsewhere", "tabs": [{"label": "auth", "cwd": "/proj", "agent": "claude",
                                                          "session_id": "s1", "resume": ["command", "claude", "--resume",
                                                                                         "s1", "--model", "m"]}]}
        created = {"workspace": {"workspace_id": "w5"}, "tab": {"tab_id": "w5:t1"}, "root_pane": {"pane_id": "w5:p1"}}
        with mock.patch.object(herdr, "snapshot", return_value=snap([])), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(agents, "claude_running", return_value=False), \
                mock.patch.object(herdr, "run", side_effect=lambda *a, **k: created if a[:2] == ("workspace", "create") else {}) as run:
            self.assertIsNone(core.restore_workspace(record, CFG))
        line = next(c.args[3] for c in run.call_args_list if c.args[:2] == ("pane", "run"))
        self.assertEqual(line, "command claude --resume s1 --model m")


# ---------------------------------------------------------- the placeholder

class TerminalTests(unittest.TestCase):
    def test_modes_are_reset_and_the_screen_put_back(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        before = termios.tcgetattr(slave)
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            with placeholder.Terminal(slave):
                self.assertNotEqual(termios.tcgetattr(slave), before)  # raw while it waits
        self.assertEqual(termios.tcgetattr(slave), before)
        text = out.getvalue()
        entry, _, leaving = text.partition("\x1b[?1049h")
        for mode in ("\x1b[?1000l", "\x1b[?1003l", "\x1b[?1006l", "\x1b[<99u"):  # what an agent left on
            self.assertIn(mode, entry)
        self.assertIn("\x1b[?2004h", leaving)  # pastes marked while it waits (set aside, never Enter)
        self.assertIn("\x1b[?2004l", leaving.split("\x1b[?2004h", 1)[1])  # and unmarked as it leaves
        self.assertTrue(text.endswith("\x1b[?1049l"))

    def test_it_sleeps_until_the_minute_turns(self):  # R18
        timeouts = []

        def fake_select(r, w, x, timeout):
            timeouts.append(timeout)
            return ([r[0]], [], [])
        with mock.patch.object(placeholder.select, "select", side_effect=fake_select), \
                mock.patch.object(placeholder.time, "time", return_value=60 * 30_000_000 + 10.0), \
                mock.patch.object(placeholder.os, "read", return_value=b"\r"), \
                mock.patch.object(placeholder.os, "get_terminal_size", return_value=os.terminal_size((80, 24))), \
                mock.patch.object(placeholder.signal, "set_wakeup_fd", return_value=-1), \
                mock.patch.object(sys, "stdout"):
            self.assertEqual(placeholder.wait_for_key({"agent": "claude", "at": T0}, CFG, "", 0), "resume")
        self.assertAlmostEqual(timeouts[0], 50.5)  # 10 s past the minute: wake as it turns

    def test_end_of_input_ends_it(self):
        with mock.patch.object(placeholder.select, "select", side_effect=lambda r, w, x, t: ([r[0]], [], [])), \
                mock.patch.object(placeholder.os, "read", return_value=b""), \
                mock.patch.object(placeholder.os, "get_terminal_size", return_value=os.terminal_size((80, 24))), \
                mock.patch.object(placeholder.signal, "set_wakeup_fd", return_value=-1), \
                mock.patch.object(sys, "stdout"):
            self.assertEqual(placeholder.wait_for_key({"agent": "claude", "at": T0}, CFG, "", 0), "hangup")

    def test_a_long_screen_shows_its_bottom(self):
        screen = "\n".join(f"line {i}" for i in range(30))
        rows = [agents.plain(r) for r in placeholder.compose({"agent": "grok", "at": T0}, CFG, screen, 10, 60, T0)]
        self.assertEqual(rows[-4], "line 29")

    def run_main(self, action, why=""):
        rec = {"agent": "claude", "session_id": "s1", "state": "suspended", "at": T0}
        out = io.StringIO()
        with mock.patch.object(suspend, "record", return_value=rec), \
                mock.patch.object(suspend, "mark_waking", return_value=why), \
                mock.patch.object(suspend, "to_archive", return_value=True) as archive, \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(placeholder, "Terminal", NoTerminal), \
                mock.patch.object(placeholder, "wait_for_key", return_value=action), \
                mock.patch.object(placeholder, "unmark") as unmark, \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(sys, "stdout", out):
            code = placeholder.main("default", "w1:p1")
        return code, archive, unmark, out.getvalue()

    def test_ctrl_c_files_it_in_the_archive(self):
        code, archive, _, _ = self.run_main("leave")
        self.assertEqual(code, 1)
        archive.assert_called_once_with("default", "w1:p1", "exited")

    def test_resume_takes_the_mark_off_and_clears_the_title(self):
        with mock.patch.object(placeholder, "discard_input") as discard:  # review 4 R85: queued keys go
            code, _, unmark, out = self.run_main("resume")
        discard.assert_called_once()
        self.assertEqual(code, 0)
        unmark.assert_called_once_with("default", "w1:p1")
        self.assertIn("\x1b]2;\x07", out)

    def test_a_conversation_the_agent_deleted_isnt_offered(self):  # R38 (a known folder: review 5 R97)
        rec = {"agent": "claude", "session_id": "s1", "state": "suspended", "at": T0, "config_dir": ""}
        with mock.patch.object(suspend, "record", return_value=rec), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS, exists=False)), \
                mock.patch.object(suspend, "drop_record") as drop, \
                mock.patch.object(suspend, "mark_waking") as waking, \
                mock.patch.object(placeholder, "Terminal", NoTerminal), \
                mock.patch.object(placeholder, "wait_for_key", return_value="resume") as wait, \
                mock.patch.object(placeholder, "unmark"), \
                mock.patch.object(placeholder.os, "isatty", return_value=True), \
                mock.patch.object(sys, "stdout"):
            self.assertEqual(placeholder.main("default", "w1:p1"), 1)
        drop.assert_called_once()
        waking.assert_not_called()
        self.assertIn("no longer exists", wait.call_args.args[-1])


# -------------------------------------------------------------- the popup

class FakeScreen:
    def getmaxyx(self):
        return (20, 80)


class PopupTests(StateDir):
    def setUp(self):
        super().setUp()
        entries = {f"claude:s{i}": {"herdr_session": "default", "workspace_label": "Work", "agent": "claude",
                                    "session_id": f"s{i}", "last_active": T0 - i, "closed_at": T0} for i in (1, 2)}
        store.save_archive({"entries": entries})
        f = mock.patch.object(agents, "session_facts", return_value=dict(FACTS))
        f.start()
        self.addCleanup(f.stop)
        self.popup = ui.Popup({"workspace_label": "Work"})

    def mouse(self, x, y, button):
        with mock.patch.object(ui.curses, "getmouse", return_value=(0, x, y, 0, button)):
            return self.popup.on_mouse(FakeScreen())

    def test_forget_needs_its_confirm(self):
        self.popup.on_key("d")
        self.assertTrue(self.popup.confirm)
        self.popup.on_key("n")  # anything but y keeps it
        self.assertEqual(len(store.load_archive()["entries"]), 2)
        self.popup.on_key("d")
        self.popup.on_key("y")
        self.assertEqual(len(store.load_archive()["entries"]), 1)

    def test_esc_clears_a_filter_before_it_closes(self):
        self.popup.filter = "x"
        self.assertFalse(self.popup.on_key("\x1b"))
        self.assertEqual(self.popup.filter, "")
        self.assertTrue(self.popup.on_key("\x1b"))

    def test_clicks(self):
        self.mouse(10, 3, ui.curses.BUTTON1_CLICKED)  # a row: selects, doesn't ask
        self.assertEqual((self.popup.sel, self.popup.confirm), (1, None))
        self.mouse(80 - ui.FORGET_COL, 2, ui.curses.BUTTON1_CLICKED)  # its x asks
        self.assertIsNotNone(self.popup.confirm)
        self.popup.confirm = None
        with mock.patch.object(self.popup, "do_open", return_value=True) as do_open:
            self.assertTrue(self.mouse(10, 2, ui.curses.BUTTON1_DOUBLE_CLICKED))
        do_open.assert_called_once()


# ------------------------------------------------------------ settings, Herdr

class SettingsMoreTests(StateDir):
    def test_a_broken_or_mistyped_config_is_flagged(self):  # R51
        self.settings("not = = toml\n")
        self.assertTrue(config.load().get("_broken"))
        self.settings('[suspend]\nwhen = "tme"\n')
        self.assertIn("when", config.load()["_broken"])
        self.settings('[suspend]\nwhen = "time"\n')
        self.assertNotIn("_broken", config.load())


class TransportMoreTests(unittest.TestCase):
    def test_the_frozen_view_is_the_bottom_screen(self):  # review 7 R150: not the scrolled-to part
        with mock.patch.object(herdr.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=b"x\r\n")) as run:
            herdr.read_screen("w1:p1", rows=40)
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("--source") + 1:argv.index("--source") + 4], ["recent", "--lines", "40"])
        with mock.patch.object(herdr.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=b"x\r\n")) as run:
            herdr.read_screen("w1:p1")  # a Herdr that doesn't say the pane's height: still from the bottom
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("--source") + 1:argv.index("--source") + 4],
                         ["recent", "--lines", str(herdr.RECENT_LINES)])
        self.assertNotIn("visible", argv)


if __name__ == "__main__":
    unittest.main()
