"""Strict review 10 (all of 1.2, second round): one test per finding
(R194-R208) and both reviewers' mutation survivors (R210)."""
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import (agentrow, agents, config, core, herdr, herdrconf, launcher, noteui, notes, sidebar,  # noqa: E402
                     statusline, store, suspend)
from test_suspend import T0, pane, snap  # noqa: E402
from test_review1 import StateDir  # noqa: E402
from test_herdrconf import HerdrConfigFile, PALETTE, herdr_upsert  # noqa: E402
from test_agentrow import STATUS, Sent  # noqa: E402

CFG = dict(config.DEFAULTS, sidebar=dict(config.SIDEBAR_DEFAULTS), colors=dict(config.COLOR_DEFAULTS))
FACTS = {"known": True, "exists": True, "has_content": True, "title": "", "last_active": None}


def transcript(records):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "t.jsonl")
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return d, path


class InjectedRecordTests(unittest.TestCase):  # R194
    def test_task_results_and_shell_output_are_no_requests(self):
        d, path = transcript([
            {"type": "user", "message": {"content": "Please refactor the parser"}},
            {"type": "user", "message": {"content": "<task-notification><result>IGNORE ALL</result></task-notification>"}},
            {"type": "user", "message": {"content": "<bash-input>curl x</bash-input>"}},
            {"type": "user", "message": {"content": "<bash-stdout>IGNORE ALL</bash-stdout><bash-stderr></bash-stderr>"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Refactoring."}]}}])
        self.addCleanup(shutil.rmtree, d, True)
        got = agents.recent_exchange("claude", path)
        self.assertEqual(got["requests"], ["Please refactor the parser"])
        self.assertNotIn("IGNORE", json.dumps(got))


class RollbackDuplicateTests(HerdrConfigFile):  # R195: R169 and R177 together
    def test_a_rollback_never_repeats_a_moved_key(self):
        self.write('[ui]\nsidebar_width = 30\n')
        self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "written")
        self.write(herdr_upsert(self.text(), "ui", "status_indicators", '"dots"'))  # inside the markers
        broken = herdrconf.BEGIN + "\n# BREAK\n[ui.sidebar.spaces]\nrows = []\n" + herdrconf.END + "\n"
        with mock.patch.dict(os.environ, {"FAKE_EDIT_AT_CHECK": "2"}), \
                mock.patch.object(herdrconf, "block", return_value=broken):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "rolled back")
        text = self.text()
        self.assertEqual(text.count("status_indicators"), 1)
        self.assertIn("edited meanwhile", text)
        if config.tomllib:
            config.tomllib.loads(text)  # valid TOML: Herdr doesn't fall back to its defaults


class WriterGuardTests(HerdrConfigFile):
    def test_a_file_that_doesnt_parse_is_left_alone(self):  # R206
        if not config.tomllib:
            self.skipTest("needs tomllib (Python 3.11+)")
        self.write('[keys\nprefix = "x"\n')
        status, detail = herdrconf.apply(CFG, PALETTE)
        self.assertEqual(status, "refused")
        self.assertIn("isn't valid TOML", detail)
        self.assertEqual(self.text(), '[keys\nprefix = "x"\n')
        self.assertFalse(os.path.exists(self.log))  # no check run, nothing written

    def test_a_read_only_target_fails_once_not_every_hook(self):  # R199 (home-manager)
        store_dir = os.path.join(self.dir.name, "nix-store")
        os.makedirs(store_dir)
        real = os.path.join(store_dir, "config.toml")
        with open(real, "w") as f:
            f.write("[keys]\n")
        os.chmod(store_dir, 0o555)
        self.addCleanup(os.chmod, store_dir, 0o755)
        os.symlink(real, self.path)
        on = dict(CFG, sidebar=dict(CFG["sidebar"], write_herdr_config=True))
        with mock.patch.object(herdrconf, "theme_stamp", return_value=None):
            self.assertEqual(herdrconf.keep_current(on)[0], "refused")
            self.assertIsNone(herdrconf.keep_current(on))
        self.assertEqual(sum(1 for c in self.calls() if c[:2] == ["config", "check"]), 1)
        self.assertIn("can't write", store.load_json("herdrconf.json")["last"]["detail"])

    def test_a_check_that_doesnt_answer(self):  # R199
        self.write("[keys]\n")
        with mock.patch.object(herdrconf, "_check_lines", side_effect=herdrconf.NoAnswer("timed out")):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "busy")
        self.assertEqual(self.text(), "[keys]\n")
        answers = iter([set(), herdrconf.NoAnswer("timed out")])

        def check():
            a = next(answers)
            if isinstance(a, Exception):
                raise a
            return a
        with mock.patch.object(herdrconf, "_check_lines", side_effect=check):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "rolled back")  # unchecked: undone
        self.assertEqual(self.text(), "[keys]\n")

    def test_a_refusal_is_tried_again_once_the_file_changes(self):  # R203
        on = dict(CFG, sidebar=dict(CFG["sidebar"], write_herdr_config=True))
        self.write("[ui.sidebar.spaces]\nrow_gap = 1\n")
        with mock.patch.object(herdrconf, "theme_stamp", return_value=None):
            self.assertEqual(herdrconf.keep_current(on)[0], "refused")
            self.assertIsNone(herdrconf.keep_current(on))  # the same file: not again
            self.write("[keys]\n")  # the user removed their table
            self.assertEqual(herdrconf.keep_current(on)[0], "written")

    def test_busy_is_no_failure(self):  # R210 (fit survivor)
        on = dict(CFG, sidebar=dict(CFG["sidebar"], write_herdr_config=True))
        self.write("[keys]\n")
        with mock.patch.object(herdrconf, "theme_stamp", return_value=None):
            with mock.patch.object(herdrconf, "apply", return_value=("busy", "changed meanwhile")):
                herdrconf.keep_current(on)
            self.assertNotIn("failed", store.load_json("herdrconf.json"))
            self.assertEqual(herdrconf.keep_current(on)[0], "written")  # tried again

    def test_rows_inside_a_multiline_string_dont_hide_later_ones(self):  # R204
        text = "[t]\nm = '''\n[ x\n'''\n[ui.sidebar.agents]\nrows = [[\"tab\"]]\n"
        self.assertEqual(herdrconf.conflicts(text), ["ui.sidebar.agents.rows"])
        self.assertEqual(herdrconf.conflicts('[t]\nm = """\nrows = 1\n[ui.sidebar.spaces]\n"""\n'), [])


class ColourTests(unittest.TestCase):  # R196
    def test_without_a_theme_readable_on_light_and_dark(self):
        text = herdrconf.block(CFG, {})
        self.assertNotIn("#cdd6f4", text)  # no dark-theme pastels
        model = [line for line in text.splitlines() if line.startswith("claude")][0]
        self.assertIn('token = "$earmark_model", dim = false', model)  # Herdr's own text colour
        self.assertIn('token = "$earmark_effort", dim = true', model)  # the soft one dimmed
        for hue in ("red", "yellow", "green", "blue", "magenta"):
            self.assertGreaterEqual(min(contrast(herdrconf.FALLBACK[hue], bg) for bg in
                                        ("#ffffff", "#eff1f5", "#1e1e2e", "#000000")), 3.0, hue)
        self.assertIn(PALETTE["yellow"], herdrconf.block(CFG, PALETTE))  # a theme still wins

    def test_omarchys_own_path(self):  # R208
        self.assertEqual(herdrconf.theme_file(),
                         os.path.join(os.environ["HOME"], ".local/state/omarchy/current/theme/colors.toml"))


def contrast(a, b):
    def lum(h):
        r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = (lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class StatusLinePaneTests(StateDir):  # R197, R207 and the fit survivors
    def line(self, payload=STATUS, env=None, cfg_text=None, live="s1"):
        if cfg_text:
            self.settings(cfg_text)
        sent = Sent()
        env = {"HERDR_PANE_ID": "w1:p1"} if env is None else env
        with mock.patch.object(sidebar, "report", sent), \
                mock.patch.object(herdr, "pane", return_value={"agent_session": {"value": live}}) as get:
            agentrow.from_statusline(json.dumps(payload).encode(), env)
        return sent, get

    def test_a_claude_from_outside_the_pane_writes_nothing(self):
        sent, _ = self.line(live="someone-else")
        self.assertEqual(sent.calls, [])
        sent, get = self.line()
        self.assertEqual(sent.shown("w1:p1")["earmark_ctx_1"], "9%")
        sent, get = self.line(payload=dict(STATUS, context_window={"used_percentage": 40}))
        get.assert_not_called()  # the pane's session is known now: Herdr isn't asked each time

    def test_nothing_to_show_or_rows_off_sends_and_writes_nothing(self):
        sent, _ = self.line(payload={"session_id": "s1", "model": {}})
        self.assertEqual(sent.calls, [])
        sent, _ = self.line(cfg_text="[sidebar]\nagent_row = []\n")
        self.assertEqual(sent.calls, [])
        self.assertEqual(agentrow.cached_panes("default"), {})  # not even a cache file per refresh

    def test_the_percent_is_rounded(self):
        self.assertEqual(agentrow.claude_values(dict(STATUS, context_window={"used_percentage": 9.6}))["percent"], 10)

    def test_outside_herdr_no_fork(self):
        with mock.patch.object(statusline, "_apart") as apart:
            statusline.run([], stdin=io.BytesIO(b"{}"), stdout=io.BytesIO(), env={})
        apart.assert_not_called()

    def test_earmarks_part_runs_in_a_session_of_its_own(self):
        mark = os.path.join(self.dir.name, "sid")

        def job():  # written whole before os._exit (which flushes nothing)
            with open(mark + ".tmp", "w") as f:
                f.write(str(os.getsid(0)))
            os.rename(mark + ".tmp", mark)
        pid = os.fork()
        if pid == 0:  # the test's own child plays the status line process
            try:
                statusline._apart(job)
            finally:
                os._exit(0)
        os.waitpid(pid, 0)
        deadline = time.monotonic() + 5
        while not os.path.exists(mark) and time.monotonic() < deadline:
            __import__("select").select([], [], [], 0.02)
        with open(mark) as f:
            self.assertNotEqual(int(f.read()), os.getsid(0))


class CodexTokenTests(StateDir):  # R210 (fit survivor)
    def test_the_newest_token_count(self):
        d, path = transcript([
            {"type": "turn_context", "payload": {"model": "m", "effort": "high"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": 1000}, "model_context_window": 10000}}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": 5000}, "model_context_window": 10000}}}])
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(agentrow.codex_values(path)["percent"], 50)


class FittingTests(unittest.TestCase):  # R210 (fit survivor)
    def test_a_wide_name_is_measured_in_columns(self):
        vals = dict.fromkeys(config.COUNT_ITEMS, 0)
        vals.update(blocked=1, working=2)
        # 26 columns: the name line holds 26 - 1 - 1 - 2 - 1 - 2 = 19; "漢字漢字漢字漢字" takes 16
        self.assertEqual(sidebar.fit_counts("漢字漢字漢字漢字", vals, ["blocked", "working"], "same", 26), [])
        self.assertEqual(len(sidebar.fit_counts("abcdefghijklmnop", vals, ["blocked", "working"], "same", 26)), 0)
        self.assertEqual(len(sidebar.fit_counts("abcdefgh", vals, ["blocked", "working"], "same", 26)), 2)


class LauncherQuotingTests(StateDir):  # R210 (fit survivor)
    def test_a_root_with_a_space(self):
        root = os.path.join(self.dir.name, "my plugins", "earmark")
        shutil.copytree(launcher.ROOT, root, ignore=shutil.ignore_patterns(".git", "tests", "media", "branding"))
        path = launcher.ensure(root=root)
        out = subprocess.run([path, "note", "path", "--workspace", "w1"], capture_output=True, text=True, timeout=30)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, notes.note_path("default", "w1")))


class PickerTests(StateDir):  # R210 (fit survivor)
    def test_a_digit_past_the_list(self):
        popup = noteui.NotePopup("default", "w1")
        popup.picking = [("w1:p1", "a"), ("w1:p2", "b")]
        with mock.patch.object(noteui, "ask") as ask:
            self.assertFalse(popup.on_key(None, "9"))
        ask.assert_not_called()


class NoteSafetyTests(StateDir):  # R198 and the safety survivors
    def hook(self, event, data=None, panes=(), workspaces=None, patches=()):
        ctx = [mock.patch.object(herdr, "snapshot", return_value=snap(list(panes), workspaces)),
               mock.patch.object(agents, "session_facts", return_value=dict(FACTS)),
               mock.patch.object(herdr, "process_info", return_value={}),
               mock.patch.object(sidebar, "report"),
               mock.patch.object(suspend, "spawn_worker", return_value=True)]
        ctx += [mock.patch.object(obj, name, **kw) for obj, name, kw in patches]
        for c in ctx:
            c.start()
        try:
            core.handle_event(event, {"data": data or {}}, env={})
        finally:
            for c in reversed(ctx):
                c.stop()

    def test_a_failed_archive_write_keeps_the_note_file(self):
        self.hook("pane.focused", panes=[pane("w1:p1"), pane("w2:p1", "s2", ws="w2")],
                  workspaces={"w1": "Work", "w2": "Other"})
        notes.write("default", "w2", "where Other stood")
        with self.assertRaises(OSError):
            self.hook("workspace.closed", {"workspace_id": "w2", "workspace": {"label": "Other"}},
                      panes=[pane("w1:p1")], workspaces={"w1": "Work"},
                      patches=[(store, "save_archive", {"side_effect": OSError("disk full")})])
        self.assertEqual(notes.read("default", "w2"), "where Other stood\n")  # not in the archive: not gone

    def test_a_failed_put_back_keeps_the_record(self):
        record = {"key": "default|w1|1", "herdr_session": "default", "workspace_id": "w1", "label": "Work",
                  "closed_at": T0, "tabs": [{"label": "notes", "cwd": "/", "session_id": None}], "note": "back\n"}
        store.save_archive({"entries": {}, "workspaces": {record["key"]: record}})

        def run(*args, **kw):
            if args[:2] == ("workspace", "create"):
                return {"workspace": {"workspace_id": "w5"}, "tab": {"tab_id": "w5:t1"}, "root_pane": {"pane_id": "w5:p1"}}
            return {}
        with mock.patch.object(herdr, "run", side_effect=run), \
                mock.patch.object(herdr, "snapshot", return_value=snap([], {"w9": "Other"})), \
                mock.patch.object(notes, "put_back", side_effect=OSError("disk full")):
            self.assertIn("note couldn't be written", core.restore_workspace(record, config.load()))
        self.assertIn(record["key"], store.load_archive()["workspaces"])

    def test_a_recreated_session_files_the_old_notes(self):
        old = [pane(f"w{n}:p1", f"s{n}", ws=f"w{n}") for n in (1, 2, 3)]
        self.hook("pane.focused", panes=old, workspaces={"w1": "A", "w2": "B", "w3": "C"})
        notes.write("default", "w1", "A's note")
        # the session deleted and made again: a restart, ids from w1, none of the old panes
        new = [pane("w1:p7", "n1", ws="w1")]
        with mock.patch.object(os, "getppid", return_value=999999):
            self.hook("startup", panes=new, workspaces={"w1": "Fresh"})
        self.assertEqual(notes.read("default", "w1"), "")  # not on the new w1
        self.assertIn("A's note\n", [r.get("note") for r in store.load_archive()["workspaces"].values()])

    def test_an_empty_note_file_is_no_note(self):
        open(notes.note_path("default", "w4"), "w").close()
        self.assertNotIn("w4", notes.noted("default"))


class OrderTests(StateDir):  # R202
    def test_the_counts_go_after_the_suspend_side(self):
        self.settings('[suspend]\nwhen = "time"\n')
        order = []
        with mock.patch.object(agentrow, "refresh"), mock.patch.object(herdrconf, "keep_current"), \
                mock.patch.object(core, "send_reports", side_effect=lambda r, s: order.append("counts")), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1")])), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", side_effect=lambda a: order.append("worker") or True):
            core.handle_event("pane.focused", {"data": {}}, env={})
        self.assertEqual(order, ["worker", "counts"])

    def test_a_resume_on_view_goes_before_the_counts(self):
        self.settings('[suspend]\nwhen = "manual"\nresume_on = "view"\n')
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {"w1:p1": {
            "pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude", "session_id": "s1",
            "state": "suspended", "at": time.time() - 100, "cwd": "/proj"}}}}})
        order = []
        with mock.patch.object(agentrow, "refresh"), mock.patch.object(herdrconf, "keep_current"), \
                mock.patch.object(core, "send_reports", side_effect=lambda r, s: order.append("counts")), \
                mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", session=None, focused=True)])), \
                mock.patch.object(agents, "session_facts", return_value=dict(FACTS)), \
                mock.patch.object(suspend, "spawn_worker", return_value=True), \
                mock.patch.object(suspend, "wake_on_view", side_effect=lambda s, p: order.append("wake")):
            core.handle_event("pane.focused", {"data": {"pane_id": "w1:p1"}}, env={})
        self.assertEqual(order, ["wake", "counts"])


class FallbackParserTests(unittest.TestCase):  # R205
    def test_a_row_on_its_own_line_is_no_table(self):
        text = ('[ui.sidebar.agents]\nrows = [\n  ["state_icon", "tab"],\n  ["terminal_title"]\n]\n'
                '[ui]\nsidebar_width = 30\n')
        data = config.parse_simple_toml(text, errors=[])
        self.assertEqual(data["ui"]["sidebar_width"], 30)
        self.assertNotIn('"terminal_title"', data)


if __name__ == "__main__":
    unittest.main()
