"""Unit tests for suspending tabs in place (docs/PLAN.md, phase I) and the
CLAUDE_CONFIG_DIR fix (phase J). Run: python3 -m unittest discover tests

They use made-up snapshots, screens and transcripts, and never touch a
running Herdr or a real process."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, placeholder, procs, store, suspend  # noqa: E402

T0 = 1_800_000_000.0
CFG = dict(config.DEFAULTS, suspend=dict(config.SUSPEND_DEFAULTS, when="time"), resume={})

RULE = "\x1b[2m" + "─" * 40 + "\x1b[0m"


def claude_screen(typed="", hint=True):
    """A Claude Code screen: conversation, the prompt box, a status line."""
    prompt = "❯ " + (typed if typed else ("\x1b[2mTry \"fix lint errors\"\x1b[0m" if hint else ""))
    return "\n".join(["⏺ Done. The tests pass.", "", RULE, prompt, RULE, "  ? for shortcuts   main"])


def pane(pid, session="s1", status="idle", tab=None, ws="w1", focused=False, agent="claude"):
    p = {"pane_id": pid, "workspace_id": ws, "tab_id": tab or f"{ws}:t{pid[-1]}", "cwd": "/proj",
         "foreground_cwd": "/proj", "terminal_title": "✳ Fix the tests", "agent": agent if session else None,
         "agent_status": status if session else None, "focused": focused, "revision": 7}
    if session:
        p["agent_session"] = {"agent": agent, "kind": "id", "source": f"herdr:{agent}", "value": session}
    return p


def snap(panes, workspaces=None, view=True):
    """A Herdr snapshot. Herdr reports the pane in focus; unless a test pane
    is focused (or view=False), one in another workspace is, so the tab in
    view is never the test's (review 5 R99: no focus, no automatic stop)."""
    workspaces = workspaces or {"w1": "Work"}
    if view and not any(p.get("focused") for p in panes):
        panes = list(panes) + [{"pane_id": "w9:p9", "workspace_id": "w9", "tab_id": "w9:t9", "cwd": "/",
                                "foreground_cwd": "/", "agent": None, "agent_status": None, "focused": True}]
    return {"panes": {p["pane_id"]: p for p in panes},
            "workspaces": {w: {"workspace_id": w, "label": label} for w, label in workspaces.items()},
            "tabs": {p["tab_id"]: {"tab_id": p["tab_id"], "label": "tab", "workspace_id": p["workspace_id"]}
                     for p in panes}}


def found(activity, **kw):
    out = {"pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "why": "", "busy": "", "timers": "",
           "registry": {"status": "idle", "remote": False}, "facts": {"known": True, "exists": True, "has_content": True},
           "activity": activity, "memory_kb": 300_000}
    out.update(kw)
    return out


class SettingsTests(unittest.TestCase):
    def test_suspend_settings_are_checked(self):
        good = config.suspend_settings({"when": "count", "keep_awake": 3, "resume_on": "view", "show": "notice",
                                        "idle_minutes": 90, "memory_below": 15})
        self.assertEqual(good, {"when": "count", "keep_awake": 3, "resume_on": "view", "show": "notice",
                                "idle_minutes": 90, "memory_below": 15, "tab_mark": "💤", "suspend_unseen": True,
                                "messages": "popup"})
        self.assertEqual(config.suspend_settings({"tab_mark": "zZ"})["tab_mark"], "zZ")
        self.assertEqual(config.suspend_settings({"tab_mark": ""})["tab_mark"], "")
        self.assertEqual(config.suspend_settings({"tab_mark": "-h"})["tab_mark"], "💤")  # never a flag
        bad = config.suspend_settings({"when": "sometimes", "idle_minutes": 0, "memory_below": 95,
                                       "keep_awake": True, "resume_on": "click", "show": 1})
        self.assertEqual(bad, config.SUSPEND_DEFAULTS)
        self.assertEqual(config.SUSPEND_DEFAULTS["when"], "off")  # shipped off
        problems = config.suspend_problems({"when": "sometimes", "colour": "red"})
        self.assertTrue(any("when" in p for p in problems) and any("colour" in p for p in problems))

    def test_suspend_table_with_and_without_tomllib(self):
        text = '[suspend]\nwhen = "time"  # after an hour\nidle_minutes = 45\nresume_on = "view"\n'
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONFIG_DIR": d}):
            with open(os.path.join(d, "config.toml"), "w") as f:
                f.write(text)
            for toml in (config.tomllib, None):
                with mock.patch.object(config, "tomllib", toml):
                    s = config.load()["suspend"]
                    self.assertEqual((s["when"], s["idle_minutes"], s["resume_on"], s["show"]),
                                     ("time", 45, "view", "frozen"))


class ScreenTests(unittest.TestCase):
    def test_empty_prompt_with_its_hint_is_not_a_draft(self):
        self.assertEqual(agents.draft_text(claude_screen(), "claude"), "")
        self.assertEqual(agents.draft_text(claude_screen(hint=False), "claude"), "")

    def test_typed_text_is_a_draft(self):
        self.assertEqual(agents.draft_text(claude_screen("half a thought"), "claude"), "half a thought")

    def test_a_suggestion_without_its_styling_is_a_doubt(self):  # review 6 R124: it could be typed
        screen = "\n".join(["x", "─" * 20, '❯ Try "refactor the parser"', "─" * 20])
        self.assertIsNone(agents.draft_text(screen, "claude"))

    def test_unknown_screens(self):
        self.assertIsNone(agents.draft_text("just some output\n$ ", "claude"))
        self.assertIsNone(agents.draft_text(claude_screen(), "grok"))

    def test_codex_prompt(self):
        empty = "• Done\n\n› \x1b[2mAsk Codex to do anything\x1b[0m\n  ⏎ send"
        self.assertEqual(agents.draft_text(empty, "codex"), "")
        self.assertEqual(agents.draft_text("• Done\n\n› fix it\n", "codex"), "fix it")
        # review 6 R133: a draft begun with a newline, and one over two lines
        self.assertEqual(agents.draft_text("› \n  rerun the migration\n\n  ⏎ send", "codex"), "rerun the migration")
        self.assertEqual(agents.draft_text("› fix\n  the parser\n  ⏎ send", "codex"), "fix the parser")

    def test_frozen_view_drops_the_prompt_box(self):
        lines = placeholder.frozen_lines(claude_screen("x"), "claude")
        self.assertEqual([agents.plain(line) for line in lines], ["⏺ Done. The tests pass."])


class TimerTests(unittest.TestCase):
    def write(self, path, records, mode="w"):
        with open(path, mode) as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def call(self, name, stamp, **args):
        return {"type": "assistant", "timestamp": stamp,
                "message": {"content": [{"type": "tool_use", "name": name, "input": args}]}}

    def test_wake_ups_and_tasks_since_the_process_started(self):
        since = agents._iso_to_epoch("2026-11-25T10:00:00Z")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            self.write(path, [
                self.call("CronCreate", "2026-11-25T09:00:00Z", cron="*/5 * * * *"),  # an earlier process's
                self.call("ScheduleWakeup", "2026-11-25T10:05:00Z", delaySeconds=1800),
            ])
            cache = {}
            wake, tasks = agents.claude_timers(path, since, cache)
            self.assertEqual((wake, tasks), (agents._iso_to_epoch("2026-11-25T10:05:00Z") + 1800, 0))
            # Read on from where it stopped: the loop ends, two tasks are made
            # and the first is deleted by the id its create answered with
            # (review 4 R81: a delete takes the task it names, no other).
            def made(tool_id, stamp, job):
                create = self.call("CronCreate", stamp)
                create["message"]["content"][0]["id"] = tool_id
                answer = {"type": "user", "timestamp": stamp, "message": {"content": [
                    {"type": "tool_result", "tool_use_id": tool_id, "content": f"Scheduled job {job}"}]}}
                return [create, answer]
            self.write(path, [self.call("ScheduleWakeup", "2026-11-25T10:35:00Z", stop=True),
                              *made("toolu_a", "2026-11-25T10:36:00Z", "job-aaaa1111"),
                              *made("toolu_b", "2026-11-25T10:37:00Z", "job-bbbb2222"),
                              self.call("CronDelete", "2026-11-25T10:38:00Z", id="job-aaaa1111")], mode="a")
            offset = cache["offset"]
            self.assertEqual(agents.claude_timers(path, since, cache), (0, 1))
            self.assertGreater(cache["offset"], offset)
            self.assertEqual(list(cache["created"]), ["toolu_b"])
            # A delete Earmark can't match removes nothing: the agent stays awake.
            self.write(path, [self.call("CronDelete", "2026-11-25T10:39:00Z", id="job-unknown9")], mode="a")
            self.assertEqual(agents.claude_timers(path, since, cache), (0, 1))

    def test_a_half_written_line_waits(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            line = json.dumps(self.call("CronCreate", "2026-11-25T10:00:00Z"))
            with open(path, "w") as f:
                f.write(line[:30])
            cache = {}
            self.assertEqual(agents.claude_timers(path, 0, cache), (0, 0))
            with open(path, "a") as f:
                f.write(line[30:] + "\n")
            self.assertEqual(agents.claude_timers(path, 0, cache), (0, 1))


class ResumeTests(unittest.TestCase):
    def test_launch_flags_are_kept_and_the_prompt_is_not(self):
        argv = ["/x/claude", "--model", "opus", "fix the bug", "--add-dir", "/a", "/b", "-p",
                "--dangerously-skip-permissions", "--continue", "--settings=/s.json"]
        self.assertEqual(agents.launch_flags("claude", argv),
                         (["--model", "opus", "--add-dir", "/a", "/b", "--dangerously-skip-permissions",
                           "--settings=/s.json"], []))
        self.assertEqual(agents.launch_flags("claude", ["node", "/x/cli.js", "--model", "sonnet"]),
                         (["--model", "sonnet"], []))

    def test_resume_keeps_flags_and_the_last_permission_mode(self):
        argv = agents.live_resume_argv("claude", "abc", {}, ["--permission-mode", "plan", "--model", "m"], "auto")
        self.assertEqual(argv, ["command", "claude", "--resume", "abc", "--model", "m", "--permission-mode", "auto"])
        # bypassPermissions only comes back through the flags that allowed it
        argv = agents.live_resume_argv("claude", "abc", {}, [], "bypassPermissions")
        self.assertEqual(argv, ["command", "claude", "--resume", "abc"])

    def test_permission_mode_from_the_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"type": "permission-mode", "permissionMode": "plan"}) + "\n")
                f.write(json.dumps({"type": "permission-mode", "permissionMode": "auto"}) + "\n")
            cache = {}
            agents.claude_timers(path, 0, cache, T0)
            self.assertEqual(cache.get("mode"), "auto")


class ProcessTests(unittest.TestCase):
    def table(self):
        return procs.Table({
            10: (1, "claude", "claude"),
            11: (10, "node", "node /mcp/server.js"),          # an MCP server: not work
            12: (10, "bash", "/usr/bin/bash -c source /h/.claude/shell-snapshots/snap.sh && npm test"),
            13: (12, "node", "node jest"),
            20: (1, "claude", "claude"),
            21: (20, "uvx", "uvx mcp-server-time"),
            30: (1, "codex", "codex"),
            31: (30, "codex-exec", "x shell-snapshots y"),
        })

    def test_shells_mean_work_and_mcp_servers_dont(self):
        t = self.table()
        self.assertIn("bash", t.busy([10]))
        self.assertEqual(t.busy([20]), "")
        self.assertIn("shell-snapshots", t.busy([30]))
        self.assertEqual(sorted(t.descendants(10)), [11, 12, 13])


class RefusalTests(unittest.TestCase):
    def check(self, f=None, status="idle", manual=False, focused_tab=None, note=None, **kw):
        return suspend.refusal(f or found(T0 - 7200, **kw), pane("w1:p1", status=status), CFG, T0,
                               manual, focused_tab, note)

    def test_an_idle_quiet_agent_may_be_suspended(self):
        self.assertEqual(self.check(), "")

    def test_the_parking_rule(self):
        self.assertIn("working", self.check(status="working"))
        self.assertIn("working", self.check(status="working", manual=True))
        self.assertIn("question", self.check(status="blocked", manual=True))
        self.assertIn("question", self.check(status="blocked"))
        self.assertIn("in view", self.check(focused_tab="w1:t1"))
        self.assertIn("command is running", self.check(busy="bash: npm test"))
        self.assertIn("/loop", self.check(timers="it's waiting on a /loop wake-up"))
        self.assertIn("Remote Control", self.check(registry={"status": "idle", "remote": True}))
        self.assertIn("working", self.check(registry={"status": "busy", "remote": False}))
        self.assertIn("nothing saved", self.check(facts={"known": True, "exists": False, "has_content": False}))
        self.assertIn("failed", self.check(note={"backoff_until": T0 + 60}))
        self.assertIn("safe", self.check(session_id="-rf"))

    def test_the_key_allows_what_only_automatic_suspends_avoid(self):
        self.assertEqual(self.check(status="done", manual=True), "")
        self.assertEqual(self.check(status="unknown", manual=True), "")
        self.assertEqual(self.check(focused_tab="w1:t1", manual=True), "")
        self.assertIn("command is running", self.check(manual=True, busy="bash: x"))


class ChooseTests(unittest.TestCase):
    def looks(self, *ages, busy=()):
        out = []
        for i, age in enumerate(ages):
            p = pane(f"w1:p{i}", session=f"s{i}")
            out.append((p, {}, None if i in busy else found(T0 - age * 60, pane_id=p["pane_id"], session_id=f"s{i}")))
        return out

    def test_time_mode_waits_for_idle_minutes(self):
        chosen = suspend.choose(self.looks(30, 61, 300), CFG, T0)
        self.assertEqual([p["pane_id"] for p, _, _ in chosen], ["w1:p2", "w1:p1"])  # oldest first

    def test_count_mode_keeps_the_most_recent_awake(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="count", keep_awake=2))
        # p0 is busy (counts as awake), p1 used 5 min ago (too fresh anyway), p2/p3 quiet
        chosen = suspend.choose(self.looks(0, 5, 20, 40, busy=(0,)), cfg, T0)
        self.assertEqual([p["pane_id"] for p, _, _ in chosen], ["w1:p3", "w1:p2"])

    def test_count_mode_never_takes_an_agent_quiet_for_less_than_ten_minutes(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="count", keep_awake=0))
        self.assertEqual(suspend.choose(self.looks(3, 9), cfg, T0), [])

    def test_memory_mode_stops_once_enough_is_free(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="memory", memory_below=20))
        looks = self.looks(60, 50, 40, 30)
        total = 10_000_000  # kB; each agent frees 300 MB = 3 points
        self.assertEqual(suspend.choose(looks, cfg, T0, available=25.0, total_kb=total), [])
        chosen = suspend.choose(looks, cfg, T0, available=18.0, total_kb=total)
        self.assertEqual([p["pane_id"] for p, _, _ in chosen], ["w1:p0", "w1:p1", "w1:p2"])  # 18+9 >= 25
        self.assertEqual(suspend.choose(looks, cfg, T0, available=None, total_kb=None), [])


class ApplySuspendedTests(unittest.TestCase):
    def setUp(self):
        self.index = {"sessions": {}}
        self.archive = {"entries": {}}
        patcher = mock.patch.object(agents, "session_facts", return_value={
            "known": True, "exists": True, "has_content": True, "title": "Fix", "last_active": T0 - 60})
        self.facts = patcher.start()
        self.addCleanup(patcher.stop)
        drop = mock.patch.object(suspend, "drop_screen")
        drop.start()
        self.addCleanup(drop.stop)
        # Claude's own registry: the sessions Herdr lists live are running
        # (review 5 R96: a listing alone no longer ends a Claude's record).
        running = mock.patch.object(agents, "claude_running", return_value=True)
        self.running = running.start()
        self.addCleanup(running.stop)

    def apply(self, panes, event="pane.focused", data=None, t=T0, workspaces=None, server_pid=None):
        return core.apply(self.index, self.archive, "default", snap(panes, workspaces), event, data or {}, t,
                          server_pid=server_pid)

    def suspend_record(self, pid="w1:p1", session="s1", state="suspended", t=T0, **kw):
        rec = {"pane_id": pid, "tab_id": "w1:t1", "workspace_id": "w1", "workspace_label": "Work",
               "tab_label": "auth", "agent": "claude", "session_id": session, "cwd": "/proj", "title": "Fix",
               "state": state, "at": t}
        rec.update(kw)
        self.index["sessions"]["default"].setdefault("suspended", {})[pid] = rec
        return rec

    def test_an_agent_earmark_stopped_is_not_archived_as_an_exit(self):
        self.apply([pane("w1:p1")])
        self.suspend_record(state="stopping")
        self.apply([pane("w1:p1", session=None)], event="pane.agent_detected",
                   data={"pane_id": "w1:p1", "released": True})
        self.assertEqual(self.archive["entries"], {})
        self.assertNotIn("w1:p1", self.index["sessions"]["default"]["panes"])
        self.assertIn("w1:p1", self.index["sessions"]["default"]["suspended"])

    def test_a_closed_suspended_tab_goes_to_the_archive(self):
        self.apply([pane("w1:p1")])
        self.suspend_record()
        self.index["sessions"]["default"]["panes"].pop("w1:p1")
        self.assertTrue(self.apply([], event="tab.closed"))
        self.assertEqual(self.archive["entries"]["claude:s1"]["reason"], "closed")
        self.assertEqual(self.archive["entries"]["claude:s1"]["tab_label"], "auth")
        self.assertEqual(self.index["sessions"]["default"]["suspended"], {})

    def test_live_again_ends_the_record(self):
        self.apply([pane("w1:p1", session=None)])
        self.suspend_record(state="waking", waking_at=T0)
        self.apply([pane("w1:p1")], t=T0 + 3)  # the placeholder resumed it in place
        self.assertEqual(self.index["sessions"]["default"]["suspended"], {})
        self.assertEqual(self.archive["entries"], {})

    def test_a_stopped_session_still_shown_in_its_pane_is_not_a_resume(self):
        # Herdr may show the session a moment after its agent exited.
        self.apply([pane("w1:p1")])
        self.suspend_record(state="suspended", t=T0)
        self.apply([pane("w1:p1")], t=T0 + 2)
        self.assertIn("w1:p1", self.index["sessions"]["default"]["suspended"])
        # ...but in another pane it's open elsewhere: no longer suspended here.
        self.apply([pane("w1:p1", session=None), pane("w1:p2", session="s1")], t=T0 + 3)
        self.assertEqual(self.index["sessions"]["default"]["suspended"], {})

    def test_a_stop_in_progress_is_left_alone_until_it_is_stale(self):
        self.apply([pane("w1:p1")])
        self.suspend_record(state="stopping", t=T0)
        self.apply([pane("w1:p1")], t=T0 + 5)
        self.assertIn("w1:p1", self.index["sessions"]["default"]["suspended"])
        self.apply([pane("w1:p1")], t=T0 + suspend.STOP_STALE + 1)
        self.assertEqual(self.index["sessions"]["default"]["suspended"], {})

    def test_a_resume_that_never_came_back_goes_to_the_archive(self):
        self.apply([pane("w1:p1", session=None)])
        self.suspend_record(state="waking", waking_at=T0)
        self.apply([pane("w1:p1", session=None)], t=T0 + 10)
        self.assertEqual(self.archive["entries"], {})
        self.apply([pane("w1:p1", session=None)], t=T0 + suspend.RESUME_GRACE + 1)
        self.assertEqual(self.archive["entries"]["claude:s1"]["reason"], "exited")

    def test_a_closed_workspace_remembers_its_suspended_tab(self):
        self.apply([pane("w1:p1", session=None), pane("w1:p2", session="s2")])
        self.suspend_record()
        self.apply([pane("w1:p1", session=None), pane("w1:p2", session="s2")])
        self.apply([], event="workspace.closed", workspaces={"w9": "Other"})
        record = next(iter(self.archive["workspaces"].values()))
        sessions = sorted(tb["session_id"] for tb in record["tabs"] if tb["session_id"])
        self.assertEqual(sessions, ["s1", "s2"])

    def test_a_restart_asks_for_the_placeholders_back(self):
        self.apply([pane("w1:p1", session=None)], server_pid=100)
        self.suspend_record(armed_by_rearm=True)
        self.apply([pane("w1:p1", session=None)], server_pid=200)
        s = self.index["sessions"]["default"]
        self.assertTrue(s.get("rearm"))
        self.assertNotIn("armed_by_rearm", s["suspended"]["w1:p1"])

    def test_notes_keep_focus_and_status_times(self):
        self.apply([pane("w1:p1", status="working")], t=T0)
        self.apply([pane("w1:p1", status="idle")], event="pane.focused", data={"pane_id": "w1:p1"}, t=T0 + 10)
        self.apply([pane("w1:p1", status="idle")], event="tab.renamed", t=T0 + 20)
        note = self.index["sessions"]["default"]["panes"]["w1:p1"]
        self.assertEqual((note["since"], note["focused_at"], note["status"], note["status_at"]),
                         (T0, T0 + 10, "idle", T0 + 10))


class ConfigDirTests(unittest.TestCase):
    """Phase J: Herdr's server (Earmark's hooks) without the shell's
    CLAUDE_CONFIG_DIR made every Claude session look deleted."""

    def test_the_sessions_own_folder_is_used(self):
        with tempfile.TemporaryDirectory() as mine, tempfile.TemporaryDirectory() as other:
            os.makedirs(os.path.join(mine, "projects", "-proj"))
            os.makedirs(os.path.join(other, "projects"))
            with open(os.path.join(mine, "projects", "-proj", "abc.jsonl"), "w") as f:
                f.write(json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": other}):
                self.assertFalse(agents.session_facts("claude", "abc")["exists"])
                self.assertTrue(agents.session_facts("claude", "abc", config_dir=mine)["exists"])
                entries = {}
                note = {"agent": "claude", "session_id": "abc", "workspace_label": "Work", "config_dir": mine}
                self.assertTrue(core.archive_note(entries, "default", note, T0, "closed"))
                self.assertEqual(entries["claude:abc"]["config_dir"], mine)
                archive = {"entries": entries}
                core.prune(archive, config.load(), T0)  # still there: looked up in its own folder
                self.assertIn("claude:abc", archive["entries"])

    def test_new_claude_sessions_get_their_folder_from_their_process(self):
        s = snap([pane("w1:p1")])
        info = {"shell_pid": 1, "foreground_process_group_id": 5,
                "foreground_processes": [{"pid": 5, "name": "claude", "argv": ["claude"]}]}
        with mock.patch.object(core.herdr, "process_info", return_value=info), \
                mock.patch.object(procs, "environ_var", return_value="/home/me/.claude-alt"):
            core.note_config_dirs(s, {"panes": {}})
        self.assertEqual(s["panes"]["w1:p1"]["_config_dir"], "/home/me/.claude-alt")
        # Already known: not looked up again.
        s2 = snap([pane("w1:p1")])
        with mock.patch.object(core.herdr, "process_info") as info_call:
            core.note_config_dirs(s2, {"panes": {"w1:p1": {"session_id": "s1", "config_dir": ""}}})
        info_call.assert_not_called()


class PlaceholderTests(unittest.TestCase):
    def rec(self):
        return {"agent": "claude", "session_id": "s1", "tab_label": "auth", "title": "Fix the tests", "at": T0 - 7200}

    def test_frozen_view_keeps_the_screen_and_says_enter_to_resume(self):
        cfg = dict(CFG)
        rows = placeholder.compose(self.rec(), cfg, claude_screen("x"), 10, 60, T0)
        self.assertEqual(len(rows), 10)
        flat = [agents.plain(r) for r in rows]
        self.assertIn("Press Enter to resume", flat[-2])
        self.assertIn("Suspended 2 hours ago", flat[-2])
        self.assertEqual(flat[-4], "⏺ Done. The tests pass.")  # bottom-anchored, prompt box cut off

    def test_notice_view(self):
        cfg = dict(CFG, suspend=dict(CFG["suspend"], show="notice"))
        flat = [agents.plain(r) for r in placeholder.compose(self.rec(), cfg, claude_screen(), 12, 80, T0)]
        self.assertTrue(any("Press Enter to resume" in r for r in flat))
        self.assertTrue(any(r.strip() == "auth" for r in flat))

    def test_crop_counts_columns_and_drops_other_escapes(self):
        line = "\x1b[31m漢字abc\x1b]0;title\x07def\x1b[2J\x1b[0m"
        cropped = placeholder.crop(line, 6)
        self.assertEqual(agents.plain(cropped), "漢字ab")
        self.assertIn("\x1b[31m", cropped)
        self.assertNotIn("\x1b]0", cropped)
        self.assertNotIn("\x1b[2J", cropped)

    def test_keys(self):
        self.assertTrue(placeholder.ENTER.search(b"\r"))
        self.assertTrue(placeholder.ENTER.search(b"\x1b[13u"))
        self.assertFalse(placeholder.ENTER.search(b"\x1b[I"))  # focus in
        self.assertTrue(placeholder.CTRL_C.search(b"\x03"))


class StateTests(unittest.TestCase):
    """Records on disk: the placeholder's side."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        env = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": self.dir.name})
        env.start()
        self.addCleanup(env.stop)
        facts = mock.patch.object(agents, "session_facts", return_value={
            "known": True, "exists": True, "has_content": True, "title": "Fix", "last_active": T0})
        facts.start()
        self.addCleanup(facts.stop)
        index = {"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "workspace_id": "w1", "workspace_label": "Work", "agent": "claude",
            "session_id": "s1", "state": "suspended", "at": T0, "resume": ["claude", "--resume", "s1"]}}}}}
        store.save_index(index)

    def test_resume_hands_over_the_record(self):
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])):
            self.assertEqual(suspend.mark_waking("default", "w1:p1"), "")
        self.assertEqual(suspend.record("default", "w1:p1")["state"], "waking")

    def test_its_own_pane_showing_the_stopped_session_doesnt_block_resume(self):
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1", session="s1")])):
            self.assertEqual(suspend.mark_waking("default", "w1:p1"), "")

    def test_never_resumed_twice(self):
        elsewhere = snap([pane("w1:p1", session=None), pane("w1:p2", session="s1")])
        with mock.patch.object(suspend.herdr, "snapshot", return_value=elsewhere), \
                mock.patch.object(suspend.agents, "claude_running", return_value=True):  # Claude's own registry
            self.assertIn("somewhere else", suspend.mark_waking("default", "w1:p1"))
        self.assertIsNone(suspend.record("default", "w1:p1"))

    def test_leaving_files_the_session_in_the_archive(self):
        self.assertTrue(suspend.to_archive("default", "w1:p1", "exited"))
        self.assertIn("claude:s1", store.load_archive()["entries"])
        self.assertIsNone(suspend.record("default", "w1:p1"))


class SuspendPaneTests(unittest.TestCase):
    """The worker's one-pane flow, with Herdr and the processes faked."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for target in (mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": self.dir.name}),
                       mock.patch.object(suspend, "look", side_effect=self.fake_look),
                       mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1")])),
                       mock.patch.object(suspend.herdr, "pane", side_effect=self.fake_pane),
                       mock.patch.object(suspend.herdr, "read_screen", side_effect=lambda p, **k: self.screen),
                       mock.patch.object(suspend.procs, "start_token", side_effect=self.fake_token),
                       mock.patch.object(suspend.os, "kill", side_effect=self.fake_kill),
                       mock.patch.object(suspend.herdr, "process_info", side_effect=self.fake_info),
                       mock.patch.object(suspend.herdr, "run", side_effect=self.fake_run),
                       mock.patch.object(suspend.procs, "Table", return_value=suspend.procs.Table({})),
                       mock.patch.object(suspend.time, "sleep")):
            target.start()
            self.addCleanup(target.stop)
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1"}}}}})
        self.screen = claude_screen()
        self.stopped = False
        self.exits = True
        self.placeholder = False
        self.events = []

    def fake_look(self, p, note, table, t, timers):
        return found(T0 - 7200, group=50, pid=50, chain=[50], tokens={50: "L"}, flags=[], unknown_flags=[],
                     launch=["claude"], config_dir="")

    def fake_token(self, pid):
        return None if self.stopped else "L"

    def fake_pane(self, pane_id):
        # Herdr lets go of the agent once it has exited.
        return pane("w1:p1", session=None) if self.stopped else pane("w1:p1")

    def fake_kill(self, pid, sig):
        rec = suspend.record("default", "w1:p1")
        self.events.append(("kill", rec and rec["state"]))  # the record must exist first
        self.stopped = self.exits

    def fake_info(self, pane_id):
        if self.placeholder:
            return {"shell_pid": 1, "foreground_process_group_id": 60, "foreground_processes": [
                {"pid": 60, "name": "python3", "argv": ["/usr/bin/python3", "/x/earmark.py", "suspended", "default", pane_id]}]}
        return {"shell_pid": 1, "foreground_process_group_id": 1 if self.stopped else 50,
                "foreground_processes": [] if self.stopped else [{"pid": 50, "name": "claude", "argv": ["claude"]}]}

    def fake_run(self, *args):
        self.events.append(args[:2])
        if args[:2] == ("pane", "run"):
            self.placeholder = True
            self.typed = args[3]
        if args[:2] == ("tab", "get"):
            return {"tab": {"label": "auth"}}
        if args[:2] == ("tab", "rename"):
            self.renamed = args[3]
        return {}

    def test_record_first_then_stop_then_placeholder(self):
        with mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3600)
        self.assertEqual(why, "")
        self.assertEqual(self.events, [("kill", "stopping"), ("pane", "send-keys"), ("pane", "send-keys"), ("pane", "run"),
                                       ("tab", "get"), ("tab", "rename")])
        self.assertIn("earmark.py suspended default w1:p1 --state ", self.typed)
        self.assertTrue(self.typed.endswith(" && cd /proj && command claude --resume s1"))
        self.assertEqual(self.renamed, "💤 auth")
        rec = suspend.record("default", "w1:p1")
        self.assertEqual((rec["state"], rec["resume"]), ("suspended", ["command", "claude", "--resume", "s1"]))
        with open(rec["screen"]) as f:
            self.assertIn("The tests pass", f.read())

    def test_unsent_text_is_never_lost(self):
        self.screen = claude_screen("half a thought")
        self.assertIn("unsent text", suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True))
        self.assertEqual(self.events, [])

    def test_a_resume_herdr_reported_without_an_event_doesnt_block_the_key(self):
        # The placeholder resumed it ("waking") and no hook ran since.
        store.save_index({"sessions": {"default": {"panes": {"w1:p1": {"session_id": "s1"}}, "suspended": {
            "w1:p1": {"pane_id": "w1:p1", "agent": "claude", "session_id": "s1", "state": "waking",
                      "at": T0 - 30, "waking_at": T0 - 20}}}}})
        with mock.patch.object(suspend.time, "time", return_value=T0), mock.patch.object(core, "now", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertEqual(why, "")

    def test_an_agent_that_wont_stop_is_left_running_and_backed_off(self):
        self.exits = False
        clock = iter(range(int(T0), int(T0) + 100))
        with mock.patch.object(suspend.time, "time", side_effect=lambda: float(next(clock))):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("didn't stop", why)
        # It was signalled, so its record stays ("stopping"): a hook finishes
        # it whether it exits later or turns out to be still running (R31).
        self.assertEqual(suspend.record("default", "w1:p1")["state"], "stopping")
        note = store.load_index()["sessions"]["default"]["panes"]["w1:p1"]
        self.assertGreater(note["backoff_until"], T0)
        self.assertNotIn(("pane", "run"), self.events)



# ---------------------------------------------------------------------------
# One test per finding of the fresh review (2026-11-25), and per mutation that
# the suite didn't catch then.

TYPING = {("pane", "send-keys"), ("pane", "run"), ("pane", "send-text")}


def typed(run_mock):
    """The calls of a mocked herdr.run that type into a pane."""
    return [c.args[:2] for c in run_mock.call_args_list if c.args[:2] in TYPING]


def ph_info(session="default", pane_id="w1:p1"):
    """process-info for a pane whose foreground is its placeholder."""
    return {"shell_pid": 1, "foreground_process_group_id": 60, "foreground_processes": [
        {"pid": 60, "name": "python3", "argv": ["/usr/bin/python3", "/x/earmark.py", "suspended", session, pane_id]}]}


def agent_info():
    return {"shell_pid": 1, "foreground_process_group_id": 50,
            "foreground_processes": [{"pid": 50, "name": "claude", "argv": ["claude"]}]}


def shell_info():
    return {"shell_pid": 1, "foreground_process_group_id": 1, "foreground_processes": [
        {"pid": 1, "name": "bash", "argv": ["bash"]}]}


class TempState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        env = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": self.dir.name,
                                           "HERDR_PLUGIN_CONFIG_DIR": self.dir.name})
        env.start()
        self.addCleanup(env.stop)
        sleep = mock.patch.object(suspend.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        sp = mock.patch.object(suspend, "screen_print", return_value="shell")  # a bare shell nobody touches
        sp.start()
        self.addCleanup(sp.stop)

    def put(self, state="suspended", **kw):
        rec = {"pane_id": "w1:p1", "workspace_id": "w1", "workspace_label": "Work", "agent": "claude",
               "session_id": "s1", "state": state, "at": T0, "resume": ["claude", "--resume", "s1"],
               "base": {"screen": "shell", "at": 0}}  # its shell seen back a while ago, unchanged since
        rec.update(kw)
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": rec}}}})


class EnterOnlyIntoThePlaceholderTests(TempState):
    """Review #1: Enter went into whatever ran in the pane."""

    def test_enter_needs_the_placeholder_in_the_foreground(self):
        self.put()
        for info, expected in ((agent_info(), False), (shell_info(), False), (ph_info(), True)):
            with mock.patch.object(suspend.herdr, "process_info", return_value=info), \
                    mock.patch.object(suspend.herdr, "send_enter") as enter:
                self.assertEqual(suspend.press_enter("default", "w1:p1"), expected)
                self.assertEqual(enter.called, expected)

    def test_view_resume_needs_the_pane_still_in_view(self):
        self.put()
        with mock.patch.object(suspend.herdr, "pane", return_value=pane("w1:p1", session=None, focused=False)), \
                mock.patch.object(suspend.herdr, "process_info", return_value=ph_info()), \
                mock.patch.object(suspend.herdr, "send_enter") as enter:
            suspend.wake_on_view("default", "w1:p1")
        enter.assert_not_called()
        with mock.patch.object(suspend.herdr, "pane", return_value=pane("w1:p1", session=None, focused=True)), \
                mock.patch.object(suspend.herdr, "process_info", return_value=ph_info()), \
                mock.patch.object(suspend.herdr, "send_enter") as enter:
            suspend.wake_on_view("default", "w1:p1")
        enter.assert_called_once()

    def test_the_key_without_a_placeholder_asks_a_worker(self):
        self.put()
        with mock.patch.object(suspend.herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(suspend.herdr, "send_enter") as enter, \
                mock.patch.object(suspend, "spawn_worker") as spawn:
            suspend.key("default", "w1:p1")
        enter.assert_not_called()
        self.assertEqual(spawn.call_args.args[0][:3], ["--pane", "w1:p1", "--pressed"])  # with the press's time

    def test_a_placeholder_is_only_typed_into_a_bare_shell_and_only_once(self):
        self.put()
        released = pane("w1:p1", session=None)
        with mock.patch.object(suspend.herdr, "process_info", return_value=agent_info()), \
                mock.patch.object(suspend.herdr, "pane", return_value=released), \
                mock.patch.object(suspend.herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1"))
        self.assertFalse(typed(run))
        self.put(armed_by_rearm=True)
        with mock.patch.object(suspend.herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(suspend.herdr, "pane", return_value=released), \
                mock.patch.object(suspend.herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1", restart=True))  # review #10: armed after this restart
        self.assertFalse(typed(run))
        self.put(arming=T0 + 10**9)  # review 1 R11: another arm is typing right now
        with mock.patch.object(suspend.herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(suspend.herdr, "pane", return_value=released), \
                mock.patch.object(suspend.herdr, "run") as run:
            self.assertFalse(suspend.arm("default", "w1:p1", force=True))
        self.assertFalse(typed(run))


class SettleMoreTests(ApplySuspendedTests):
    def test_another_session_in_its_pane_archives_the_suspended_one(self):  # review #1
        self.apply([pane("w1:p1", session=None)])
        self.suspend_record(state="suspended")
        self.apply([pane("w1:p1", session="s2")])
        self.assertEqual(self.archive["entries"]["claude:s1"]["reason"], "replaced")
        self.assertEqual(self.index["sessions"]["default"]["suspended"], {})

    def test_another_sessions_exit_is_archived(self):  # review #3
        self.apply([pane("w1:p1", session=None)])
        self.suspend_record(state="suspended")
        self.apply([pane("w1:p1", session="s2")])
        self.suspend_record(state="suspended")  # a stale record for s1 again
        self.apply([pane("w1:p1", session=None)], event="pane.agent_detected",
                   data={"pane_id": "w1:p1", "released": True})
        self.assertEqual(self.archive["entries"]["claude:s2"]["reason"], "exited")

    def test_a_stop_whose_worker_died_is_finished(self):  # review #4
        self.apply([pane("w1:p1", session=None)])
        self.suspend_record(state="stopping", t=T0)
        self.apply([pane("w1:p1", session=None)], t=T0 + suspend.STOP_STALE + 1)
        s = self.index["sessions"]["default"]
        self.assertEqual(s["suspended"]["w1:p1"]["state"], "suspended")
        self.assertFalse(s.get("rearm"))  # no restart: the regular re-arm pass starts its placeholder

    def test_a_long_stale_view_keeps_a_suspended_record(self):  # review #12
        # Herdr can list a stopped agent (even as "claude") for as long as it
        # likes; only the processes tell (the worker's check_pane).
        self.apply([pane("w1:p1", session=None)])
        self.suspend_record(state="suspended", t=T0)
        self.apply([pane("w1:p1")], t=T0 + 600)
        self.assertIn("w1:p1", self.index["sessions"]["default"]["suspended"])

    def test_a_stop_that_never_happened_ends_its_record(self):
        self.apply([pane("w1:p1")])
        self.suspend_record(state="stopping", t=T0)
        self.apply([pane("w1:p1")], t=T0 + suspend.STOP_STALE + 1)
        self.assertEqual(self.index["sessions"]["default"]["suspended"], {})

    def test_one_rearm_per_server(self):  # review #10
        self.apply([pane("w1:p1", session=None)], server_pid=100)
        self.suspend_record()
        self.apply([pane("w1:p1", session=None)], server_pid=200)
        s = self.index["sessions"]["default"]
        s.pop("rearm")
        s["suspended"]["w1:p1"]["armed_by_rearm"] = True
        self.apply([pane("w1:p1", session=None)], event="startup", server_pid=200)
        self.assertNotIn("rearm", s)
        self.assertTrue(s["suspended"]["w1:p1"]["armed_by_rearm"])


class HookSafetyTests(TempState):
    """Review #5: nothing suspend adds to a hook may stop archiving."""

    def run_hook(self, **patches):
        snaps = [snap([pane("w1:p1")]), snap([])]
        with mock.patch.object(core.herdr, "snapshot", side_effect=lambda: snaps.pop(0)), \
                mock.patch.object(agents, "session_facts", return_value={
                    "known": True, "exists": True, "has_content": True, "title": "", "last_active": T0}), \
                mock.patch.object(core.herdr, "process_info", **patches.get("info", {"return_value": None})), \
                mock.patch.object(suspend, "spawn_worker", **patches.get("spawn", {})):
            core.handle_event("startup", None, env={})
            core.handle_event("tab.closed", None, env={})

    def test_an_odd_process_info_reply_doesnt_stop_archiving(self):
        self.run_hook(info={"side_effect": KeyError("process_info")})
        self.assertIn("claude:s1", store.load_archive()["entries"])

    def test_a_worker_that_wont_start_doesnt_stop_archiving(self):
        with open(os.path.join(self.dir.name, "config.toml"), "w") as f:
            f.write('[suspend]\nwhen = "time"\n')
        self.run_hook(info={"return_value": {}}, spawn={"side_effect": RuntimeError("boom")})
        self.assertIn("claude:s1", store.load_archive()["entries"])


class ChooseWithRejectedLooksTests(unittest.TestCase):
    def test_count_mode_with_a_pane_look_turned_down(self):  # review #6
        cfg = dict(CFG, suspend=dict(CFG["suspend"], when="count", keep_awake=1))
        looks = [(pane("w1:p0"), {}, {"pane_id": "w1:p0", "agent": "claude", "session_id": "s0",
                                      "why": "the agent isn't running in the foreground"}),
                 (pane("w1:p1", session="s1"), {}, found(T0 - 3600, pane_id="w1:p1")),
                 (pane("w1:p2", session="s2"), {}, found(T0 - 7200, pane_id="w1:p2", session_id="s2"))]
        chosen = suspend.choose(looks, cfg, T0)  # no KeyError; the turned-down pane counts as awake
        self.assertEqual([p["pane_id"] for p, _, _ in chosen], ["w1:p2", "w1:p1"])


class ResumeFidelityTests(unittest.TestCase):
    def test_switched_out_of_bypass_comes_back_without_it(self):  # review #9
        flags = agents.claude_resume_flags(["--dangerously-skip-permissions", "--model", "m"], "default")
        self.assertEqual(flags, ["--model", "m", "--allow-dangerously-skip-permissions"])
        flags = agents.claude_resume_flags(["--allow-dangerously-skip-permissions"], "bypassPermissions")
        self.assertEqual(flags, ["--allow-dangerously-skip-permissions", "--permission-mode", "bypassPermissions"])
        self.assertEqual(agents.claude_resume_flags(["--model", "m"], "bypassPermissions"), ["--model", "m"])
        self.assertEqual(agents.claude_resume_flags(["--permission-mode", "plan"], ""), ["--permission-mode", "plan"])

    def test_the_resume_gets_the_sessions_claude_folder(self):  # review #7
        rec = {"agent": "claude", "session_id": "s1", "cwd": "/w/my proj", "config_dir": "/home/me/.claude-alt",
               "resume": ["claude", "--resume", "s1"]}
        self.assertEqual(suspend.resume_command(rec),
                         "cd '/w/my proj' && CLAUDE_CONFIG_DIR=/home/me/.claude-alt claude --resume s1")
        # a folder fish would read differently is left out rather than typed
        self.assertEqual(suspend.resume_command(dict(rec, cwd="/w/it's", config_dir="")), "claude --resume s1")

    def test_open_in_a_plain_terminal_counts_as_open(self):  # review #11
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sessions"))
            with open(os.path.join(d, "sessions", f"{os.getpid()}.json"), "w") as f:
                json.dump({"pid": os.getpid(), "sessionId": "s1"}, f)
            self.assertTrue(agents.claude_running("s1", d))
            self.assertFalse(agents.claude_running("s2", d))


class DraftBoxTests(unittest.TestCase):
    def test_the_box_is_the_pair_of_rules_around_the_prompt(self):  # review #13
        screen = "\n".join(["out", RULE, "❯ unsent words", RULE, "status", "─" * 30, "\x1b[2mhint\x1b[0m", "─" * 30])
        self.assertEqual(agents.draft_text(screen, "claude"), "unsent words")
        self.assertIsNone(agents.draft_text("\n".join(["out", "─" * 30, "", "─" * 30]), "claude"))


class LastLookTests(SuspendPaneTests):
    """The re-checks right before the signal (mutations the suite missed)."""

    def test_in_view_at_the_last_moment(self):
        with mock.patch.object(suspend.herdr, "pane", return_value=pane("w1:p1", focused=True)), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False)
        self.assertIn("view", why)
        self.assertEqual(self.events, [])
        self.assertIsNone(suspend.record("default", "w1:p1"))

    def test_a_different_process_at_the_last_moment(self):
        with mock.patch.object(suspend.procs, "start_token", return_value="another process"), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("process changed", why)
        self.assertEqual(self.events, [])

    def test_an_unreadable_prompt_needs_a_yes(self):  # review 1 R8, review 3 R64
        self.screen = "some output\n$ "
        with mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertIn("can't read its prompt", suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False))
            first = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
            self.assertTrue(first.startswith(suspend.CONFIRM))
            again = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
            self.assertTrue(again.startswith(suspend.CONFIRM))  # pressing again never confirms
            self.assertEqual(self.events, [])
            other = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True, accept="something else")
            self.assertTrue(other.startswith(suspend.CONFIRM))  # only the doubt that was shown
            doubt = first[len(suspend.CONFIRM):]
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True, accept=doubt), "")

    def test_active_again_since_the_check(self):
        with mock.patch.object(suspend.time, "time", return_value=T0):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "time", manual=False, min_idle=3 * 3600)
        self.assertIn("active again", why)
        self.assertEqual(self.events, [])

    def test_the_placeholder_waits_for_the_shell(self):
        calls = {"n": 0}
        real = self.fake_info

        def slow_shell(pane_id):  # the agent's gone, but its group holds the pane a while
            calls["n"] += 1
            if self.stopped and calls["n"] < 4:
                return {"shell_pid": 1, "foreground_process_group_id": 50, "foreground_processes": []}
            return real(pane_id)

        with mock.patch.object(suspend.herdr, "process_info", side_effect=slow_shell), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True), "")
        self.assertGreaterEqual(calls["n"], 4)

    def test_a_stop_that_worked_but_never_showed_the_shell_keeps_the_session(self):  # review #2
        def no_info(pane_id):
            if self.stopped:
                raise suspend.herdr.HerdrError("busy")
            return self.fake_info(pane_id)

        clock = iter(range(int(T0), int(T0) + 200))
        with mock.patch.object(suspend.herdr, "process_info", side_effect=no_info), \
                mock.patch.object(suspend.time, "time", side_effect=lambda: float(next(clock))):
            why = suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True)
        self.assertIn("without its placeholder", why)
        self.assertEqual(suspend.record("default", "w1:p1")["state"], "suspended")


class AutoTests(TempState):
    def test_the_tab_in_view_and_busy_agents_are_not_candidates(self):
        panes = [pane("w1:p1", session="s1", tab="w1:t1", focused=True), pane("w1:p2", session="s2", tab="w1:t2"),
                 pane("w1:p3", session="s3", tab="w1:t3", status="working")]
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        looked = []

        def fake_look(p, note, table, t, timers):
            looked.append(p["pane_id"])
            return found(T0 - 7200, pane_id=p["pane_id"], session_id=p["agent_session"]["value"])

        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap(panes)), \
                mock.patch.object(suspend, "look", side_effect=fake_look), \
                mock.patch.object(suspend, "suspend_pane", return_value="") as act, \
                mock.patch.object(suspend.procs, "Table"), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            suspend.auto("default", CFG)
        self.assertEqual(looked, ["w1:p2"])
        self.assertEqual([c.args[1] for c in act.call_args_list], ["w1:p2"])


class OpenOutsideHerdrTests(TempState):
    def test_never_resumed_while_open_in_another_terminal(self):  # review #11
        self.put()
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(suspend.agents, "claude_running", return_value=True):
            self.assertIn("somewhere else", suspend.mark_waking("default", "w1:p1"))
        self.put()
        with mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(suspend.agents, "claude_running", return_value=False):
            self.assertEqual(suspend.mark_waking("default", "w1:p1"), "")


class HerdrLetsGoTests(SuspendPaneTests):
    def test_the_placeholder_waits_for_herdr_to_let_go_of_the_agent(self):
        # Typed too soon, Herdr kept listing the stopped agent and its restore
        # relaunched it (found live, 2026-11-25).
        views = {"n": 0}

        def herdr_pane(pane_id):
            if not self.stopped:
                return pane("w1:p1")
            views["n"] += 1
            return pane("w1:p1") if views["n"] < 4 else pane("w1:p1", session=None)

        with mock.patch.object(suspend.herdr, "pane", side_effect=herdr_pane), \
                mock.patch.object(suspend.time, "time", return_value=T0):
            self.assertEqual(suspend.suspend_pane("default", "w1:p1", CFG, "manual", manual=True), "")
        self.assertGreaterEqual(views["n"], 4)
        self.assertIn(("pane", "run"), self.events)


class HerdrRelaunchTests(TempState):
    def test_an_agent_herdrs_restore_relaunched_ends_its_record(self):
        self.put()
        with mock.patch.object(suspend.herdr, "process_info", return_value=agent_info()), \
                mock.patch.object(suspend.herdr, "run") as run:
            self.assertFalse(suspend.check_pane("default", "w1:p1", suspend.record("default", "w1:p1"), pane("w1:p1")))
        run.assert_not_called()
        self.assertIsNone(suspend.record("default", "w1:p1"))

    def test_while_herdr_lists_the_session_nothing_is_typed(self):  # review 1 R11, review 2 R27
        # Herdr's own restore may be about to relaunch it: a check waits...
        self.put()
        with mock.patch.object(suspend.herdr, "process_info", return_value=shell_info()), \
                mock.patch.object(suspend.herdr, "pane", return_value=pane("w1:p1")), \
                mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(suspend.herdr, "run") as run:
            self.assertFalse(suspend.check_pane("default", "w1:p1", suspend.record("default", "w1:p1"), pane("w1:p1")))
            # ...and so does the key, while Herdr keeps listing it.
            self.assertFalse(suspend.arm("default", "w1:p1", force=True, view_ok=True))
        self.assertFalse(typed(run))
        # Once Herdr lets go during the key's wait, it types.
        views = iter([pane("w1:p1"), pane("w1:p1"), pane("w1:p1", session=None)])
        infos = [shell_info(), shell_info(), ph_info()]
        with mock.patch.object(suspend.herdr, "process_info", side_effect=lambda pid: infos.pop(0) if infos else ph_info()), \
                mock.patch.object(suspend.herdr, "pane", side_effect=lambda pid: next(views, pane("w1:p1", session=None))), \
                mock.patch.object(suspend.herdr, "run") as run:
            self.assertTrue(suspend.arm("default", "w1:p1", force=True, view_ok=True))
        self.assertEqual(typed(run), [("pane", "send-keys"), ("pane", "send-keys"), ("pane", "run")])


# ---------------------------------------------------------------------------
# Found on the maintainer's machine (2026-11-25): an agent exec'd in the placeholder's
# place kept its process group, Herdr lost track of it, and a later suspend
# ran Herdr's own resume line glued to Earmark's placeholder line.

class ResumeThroughTheShellTests(unittest.TestCase):
    def test_the_typed_line_resumes_only_if_the_placeholder_says_so(self):
        rec = {"agent": "claude", "session_id": "s1", "cwd": "/proj", "resume": ["claude", "--resume", "s1"]}
        line = suspend.placeholder_command("default", "w1:p1", rec)
        self.assertTrue(line.startswith(" "))  # out of history where the shell ignores such lines
        self.assertIn("earmark.py suspended default w1:p1 --state ", line)
        self.assertTrue(line.endswith(" && cd /proj && claude --resume s1"))  # the record's own argv

    def test_exit_status_decides(self):
        rec = {"agent": "claude", "session_id": "s1", "state": "suspended", "at": T0}
        for action, why, expected in (("resume", "", 0), ("resume", "this session is open somewhere else", 1),
                                      ("leave", "", 1), ("hangup", "", 1)):
            class NoTerminal:
                def __init__(self, fd):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

            with mock.patch.object(placeholder.suspend, "record", return_value=rec), \
                    mock.patch.object(placeholder.suspend, "mark_waking", return_value=why), \
                    mock.patch.object(placeholder.suspend, "to_archive", return_value=True), \
                    mock.patch.object(placeholder, "unmark"), \
                    mock.patch.object(placeholder, "Terminal", NoTerminal), \
                    mock.patch.object(placeholder, "wait_for_key", return_value=action), \
                    mock.patch.object(placeholder.os, "isatty", return_value=True), \
                    mock.patch.object(sys, "stdout"):
                self.assertEqual(placeholder.main("default", "w1:p1"), expected, (action, why))

    def test_a_vanished_record_doesnt_strand_the_session(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": d}), \
                mock.patch.object(suspend.herdr, "snapshot", return_value=snap([pane("w1:p1", session=None)])), \
                mock.patch.object(suspend.agents, "claude_running", return_value=False):
            store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
            self.assertEqual(suspend.mark_waking("default", "w1:p1",
                                                 fallback={"agent": "claude", "session_id": "s1"}), "")
            self.assertTrue(suspend.mark_waking("default", "w1:p1"))  # no record, nothing to go on


class StrictProcessTests(unittest.TestCase):
    def test_an_agent_whose_arguments_end_like_a_placeholder_isnt_one(self):
        glued = {"name": "claude", "argv": ["claude", "--resume", "s1", "/usr/bin/python3", "/x/earmark.py",
                                            "suspended", "default", "w1:p1"]}
        real = {"name": "python3", "argv": ["/usr/bin/python3", "/x/earmark.py", "suspended", "default", "w1:p1"]}
        self.assertFalse(suspend.is_placeholder(glued, "default", "w1:p1"))
        self.assertTrue(suspend.is_placeholder(real, "default", "w1:p1"))
        self.assertFalse(suspend.is_placeholder(real, "default", "w1:p2"))
        self.assertTrue(suspend.is_placeholder(real))

    def look_with(self, processes):
        info = {"shell_pid": 1, "foreground_process_group_id": 60, "foreground_processes": processes}
        with mock.patch.object(suspend.herdr, "process_info", return_value=info), \
                mock.patch.object(suspend.procs, "start_token", return_value="L"):
            return suspend.look(pane("w1:p1"), {}, procs.Table({}), T0, {})

    def test_only_the_agent_itself_is_ever_stopped(self):
        placeholder_proc = {"pid": 60, "name": "python3",
                            "argv": ["/usr/bin/python3", "/x/earmark.py", "suspended", "default", "w1:p1"]}
        self.assertIn("suspended already", self.look_with([placeholder_proc])["why"])
        self.assertIn("isn't what's running", self.look_with([{"pid": 60, "name": "vim", "argv": ["vim"]}])["why"])


class TabMarkTests(ApplySuspendedTests):
    def test_the_mark_is_never_recorded(self):
        p = pane("w1:p1")
        s = snap([p])
        s["tabs"][p["tab_id"]]["label"] = "💤 auth"
        core.apply(self.index, self.archive, "default", s, "tab.renamed", {}, T0)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["tab_label"], "💤 auth")  # not Earmark's
        self.index["sessions"]["default"]["marked"] = {p["tab_id"]: "💤"}
        core.apply(self.index, self.archive, "default", s, "tab.renamed", {}, T0 + 1)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["tab_label"], "auth")
        self.assertEqual(core.tab_layouts(s, marked={p["tab_id"]: "💤"})["w1"]["tabs"][0]["label"], "auth")

    def test_marks_without_a_suspended_pane_are_stale(self):
        p1, p2 = pane("w1:p1", tab="w1:t1"), pane("w1:p2", tab="w1:t2")
        s = snap([p1, p2])
        s["tabs"]["w1:t1"]["label"] = "💤 auth"
        s["tabs"]["w1:t2"]["label"] = "💤 notes"
        stale = suspend.stale_marks(s, {"w1:p1": {"tab_id": "w1:t1"}}, {"w1:t1": "💤", "w1:t2": "💤"})
        self.assertEqual(stale, [("w1:t2", "💤 notes", "💤")])
        # A tab the user named "💤 ..." themselves is never touched (R39).
        self.assertEqual(suspend.stale_marks(s, {}, {}), [])


class DimmedViewTests(unittest.TestCase):
    def test_the_frozen_screen_is_drawn_faint(self):
        rows = placeholder.compose({"agent": "claude", "tab_label": "auth", "at": T0}, CFG,
                                   claude_screen("x"), 10, 60, T0)
        self.assertTrue(rows[-4].startswith(placeholder.DIM))
        self.assertIn("\x1b[0m" + placeholder.DIM, placeholder.dimmed("a\x1b[0mb"))


class KeyTests(TempState):
    def test_the_key_presses_enter_when_the_placeholder_is_up_record_or_not(self):
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {}}}})
        with mock.patch.object(suspend.herdr, "process_info", return_value=ph_info()), \
                mock.patch.object(suspend.herdr, "send_enter") as enter, \
                mock.patch.object(suspend, "spawn_worker") as spawn:
            suspend.key("default", "w1:p1")
        enter.assert_called_once()
        spawn.assert_not_called()



class NoRealHerdrTests(unittest.TestCase):
    def test_the_suite_cant_reach_a_real_herdr(self):
        # A hook test once sent a sidebar token to the user's real server.
        from earmark import herdr
        with self.assertRaises(herdr.HerdrError):
            herdr.run("workspace", "list")
        with self.assertRaises(herdr.HerdrError):
            herdr.read_screen("w1:p1")


if __name__ == "__main__":
    unittest.main()
