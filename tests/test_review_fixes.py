"""Tests for the fixes from the pre-release reviews (2026-11-21). Each one
fails on the code before those fixes. Run: python3 -m unittest discover tests"""
import json
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from earmark import agents, config, core, herdr, store  # noqa: E402
from test_core import T0, facts, pane, snap  # noqa: E402


class TempState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": os.path.join(self.tmp.name, "state"),
                                           "HERDR_PLUGIN_CONFIG_DIR": os.path.join(self.tmp.name, "config")})
        env.start()
        self.addCleanup(env.stop)


class ArchivingTests(unittest.TestCase):
    def setUp(self):
        self.index, self.archive = {"sessions": {}}, {"entries": {}}
        p = mock.patch.object(agents, "session_facts", return_value=facts(title="T", last=T0))
        p.start()
        self.addCleanup(p.stop)

    def test_claude_session_driven_by_a_slash_command_has_content(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "projects", "-p"))
            with open(os.path.join(d, "projects", "-p", "g1.jsonl"), "w") as f:
                f.write('{"type":"user","message":{"content":"<command-name>/goal</command-name>"}}\n')
                f.write('{"type":"user","isMeta":true,"message":{"content":"Work on the task"}}\n')
                f.write('{"type":"assistant","message":{"content":[{"type":"text","text":"On it."}]}}\n')
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": d}):
                self.assertTrue(agents._claude_facts("g1")["has_content"])

    def test_rename_and_close_in_the_same_snapshot(self):
        core.apply(self.index, self.archive, "default", snap([pane("w1:p1", session="s1")], {"w1": "A"}),
                   "pane.focused", {}, T0)
        core.apply(self.index, self.archive, "default", snap([], {"w1": "B"}), "pane.closed", {}, T0 + 1)
        self.assertEqual(self.archive["entries"]["claude:s1"]["workspace_label"], "B")

    def test_tab_name_kept_when_the_tab_list_misses_it(self):
        p = pane("w1:p1", tab="w1:t1", session="s1")
        first = snap([p])
        first["tabs"]["w1:t1"]["label"] = "go-public"
        core.apply(self.index, self.archive, "default", first, "pane.focused", {}, T0)
        racing = snap([p])
        racing["tabs"] = {}  # the tab closed between `pane list` and `tab list`
        core.apply(self.index, self.archive, "default", racing, "pane.focused", {}, T0 + 1)
        self.assertEqual(self.index["sessions"]["default"]["panes"]["w1:p1"]["tab_label"], "go-public")

    def test_restart_noticed_from_a_new_server_before_the_startup_hook(self):
        core.apply(self.index, self.archive, "default", snap([pane("w1:p1", session="s1")]),
                   "pane.focused", {}, T0, server_pid=100)
        # The server restarted (pid 200); a restored pane's release beats the startup hook.
        core.apply(self.index, self.archive, "default", snap([pane("w1:p1")]), "pane.agent_detected",
                   {"pane_id": "w1:p1", "released": True}, T0 + 500, server_pid=200)
        self.assertEqual(self.archive["entries"], {})

    def test_unsafe_session_id_is_not_archived(self):
        core.apply(self.index, self.archive, "default", snap([pane("w1:p1", session="--yolo")]), "x", {}, T0)
        self.assertFalse(core.apply(self.index, self.archive, "default", snap([]), "pane.closed", {}, T0 + 1))

    def test_notes_for_a_session_gone_quiet_are_dropped(self):
        core.apply(self.index, self.archive, "old-named", snap([pane("w1:p1", session="s1")]), "x", {}, T0)
        core.apply(self.index, self.archive, "default", snap([]), "x", {}, T0 + 31 * 86400)
        self.assertNotIn("old-named", self.index["sessions"])

    def test_herdr_source_and_file_cache_stay_apart(self):
        entries = {}
        note = {"agent": "claude", "session_id": "s1", "source": "herdr:claude", "workspace_label": "W"}
        with tempfile.NamedTemporaryFile() as f, \
             mock.patch.object(agents, "session_facts", return_value=dict(facts(), source=f.name)):
            core.archive_note(entries, "default", note, T0, "closed")
            self.assertEqual(entries["claude:s1"]["source"], "herdr:claude")
            self.assertEqual(entries["claude:s1"]["file"][0], f.name)


class OrderAndReportTests(unittest.TestCase):
    def test_restore_order_is_the_order_on_screen(self):
        a = pane("w1:p1", tab="w1:t1")
        b = pane("w1:p2", tab="w1:t2")
        s = snap([b, a])  # Herdr lists t2 first: it was dragged in front of t1
        s["tabs"]["w1:t2"].update(workspace_id="w1", number=2, label="notes")
        s["tabs"]["w1:t1"].update(workspace_id="w1", number=1, label="outline")
        self.assertEqual([t["label"] for t in core.tab_layouts(s)["w1"]["tabs"]], ["notes", "outline"])

    def test_sidebar_reports_carry_their_sequence(self):
        index = {"sessions": {"default": {"panes": {}}}}
        reports = core.pending_reports(index, {"entries": {}}, "default",
                                       snap([], {"w1": "A", "w2": "B"}))
        index["sessions"]["default"]["reported"] = {}
        later = core.pending_reports(index, {"entries": {}}, "default", snap([], {"w1": "A"}))
        self.assertTrue(all(len(r) == 3 for r in reports))
        self.assertGreater(later[0][2], reports[0][2])
        with mock.patch.object(herdr, "report_count") as send:
            core.send_reports(reports)
        self.assertEqual(send.call_args_list[0].args, reports[0])


class SafetyTests(unittest.TestCase):
    def test_resume_refuses_unsafe_ids(self):
        for bad in ("--yolo", "x\\';touch /tmp/p;'", "a\nb", " a", ""):
            self.assertIsNone(agents.resume_argv("claude", bad), repr(bad))
        self.assertEqual(agents.resume_argv("pi", "/home/u/.pi/s 1.jsonl")[-1], "/home/u/.pi/s 1.jsonl")
        self.assertEqual(agents.resume_argv("agy", "c1"), ["agy", "--conversation", "c1"])

    def test_tab_names_that_look_like_herdr_flags_are_left_out(self):
        calls = []
        reply = {"tab": {"tab_id": "w1:t9"}, "root_pane": {"pane_id": "w1:p9"}}
        with mock.patch.object(herdr, "run", side_effect=lambda *a: calls.append(a) or reply):
            for label in ("-h", "--session=x", "go-public"):
                herdr.new_tab("w1", None, label)
        self.assertNotIn("--label", calls[0])
        self.assertNotIn("--label", calls[1])
        self.assertIn("go-public", calls[2])

    def test_odd_characters_in_agent_folders(self):
        with tempfile.TemporaryDirectory() as root:
            claude = os.path.join(root, "cl[x]")
            os.makedirs(os.path.join(claude, "projects", "-p"))
            open(os.path.join(claude, "projects", "-p", "s1.jsonl"), "w").close()
            codex = os.path.join(root, "co?#%")
            os.makedirs(codex)
            con = sqlite3.connect(os.path.join(codex, "state_5.sqlite"))
            con.execute("create table threads (id text, rollout_path text, name text, title text, "
                        "first_user_message text, updated_at integer)")
            con.execute("insert into threads values ('c1', '', 'N', '', null, 5)")
            con.commit()
            con.close()
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": claude, "CODEX_HOME": codex}):
                self.assertTrue(agents.claude_transcript("s1"))
                c1 = agents.session_facts("codex", "c1")
        self.assertTrue(c1["known"] and c1["exists"])
        self.assertFalse(c1["has_content"])  # no first message, no title


class PopupTextTests(TempState):
    def test_wide_characters_fit_their_columns(self):
        from earmark import ui
        cut = ui.fit("漢字漢字漢字漢字", 7)
        self.assertLessEqual(ui.cols(cut), 7)
        self.assertTrue(cut.endswith("…"))
        self.assertEqual(ui.clean("a\x1b[31mb\nc\x08"), "a [31mb c ")

    def test_selection_stays_in_range_on_an_empty_list(self):
        from earmark import ui
        with mock.patch.object(herdr, "session_name", return_value="default"):
            p = ui.Popup({"workspace_label": "W"})
        p.sel = -1
        p.load()
        self.assertEqual(p.sel, 0)
        p.on_key("j")
        self.assertEqual(p.sel, 0)


class ConfigTests(TempState):
    def write(self, text):
        os.makedirs(os.environ["HERDR_PLUGIN_CONFIG_DIR"], exist_ok=True)
        with open(config.config_path(), "w") as f:
            f.write(text)

    def test_keep_days_true_is_not_a_number(self):
        self.write("keep_days = true\n")
        self.assertIsNone(config.load()["keep_days"])

    def test_fallback_parser_quotes_multiline_and_bad_lines(self):
        text = ('keep_days = 90  # keep "old" ones\n'
                'title_first = ninety\n'
                '[resume]\nclaude = [\n  "claude",  # the CLI\n  "--resume", "{id}"\n]\n')
        self.write(text)
        with mock.patch.object(config, "tomllib", None):
            cfg = config.load()
            problem = config.check()
        self.assertEqual(cfg["keep_days"], 90)
        self.assertEqual(cfg["resume"]["claude"], ["claude", "--resume", "{id}"])
        self.assertIn("line 2", problem)


class StoreTests(TempState):
    def test_malformed_entries_are_skipped(self):
        with open(os.path.join(store.state_dir(), "archive.json"), "w") as f:
            json.dump({"entries": {"ok": {"herdr_session": "d", "workspace_label": "W", "agent": "claude",
                                          "session_id": "s"}, "bad": {"agent": "claude"}, "worse": 3},
                       "workspaces": {"w": {"label": "x"}}}, f)
        a = store.load_archive()
        self.assertEqual(list(a["entries"]), ["ok"])
        self.assertEqual(a["workspaces"], {})

    def test_damaged_files_never_overwrite_each_other(self):
        for _ in range(2):
            with open(os.path.join(store.state_dir(), "archive.json"), "w") as f:
                f.write("{not json")
            store.load_archive()
        damaged = [n for n in os.listdir(store.state_dir()) if ".damaged" in n]
        self.assertEqual(len(damaged), 2)

    def test_failed_write_leaves_no_temp_file(self):
        with mock.patch.object(json, "dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.save_archive({"entries": {}})
        self.assertEqual([n for n in os.listdir(store.state_dir()) if n.startswith(".archive")], [])

    def test_debug_log_is_private(self):
        store.debug_log({"event": "x"})
        mode = stat.S_IMODE(os.stat(os.path.join(store.state_dir(), "events.jsonl")).st_mode)
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
