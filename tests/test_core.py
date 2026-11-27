"""Unit tests for the archive logic. Run: python3 -m unittest discover tests

They use made-up snapshots and never touch a running Herdr."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, core  # noqa: E402

T0 = 1_800_000_000.0


def pane(pid, ws="w1", tab=None, agent="claude", session=None, title="✳ Fix the tests", cwd="/proj"):
    p = {"pane_id": pid, "workspace_id": ws, "tab_id": tab or f"{ws}:t{pid[-1]}",
         "cwd": cwd, "foreground_cwd": cwd, "terminal_title": title, "agent": agent if session else None}
    if session:
        p["agent_session"] = {"agent": agent, "kind": "id", "source": f"herdr:{agent}", "value": session}
    return p


def snap(panes, workspaces=None):
    workspaces = workspaces or {"w1": "Work"}
    return {
        "panes": {p["pane_id"]: p for p in panes},
        "workspaces": {wid: {"workspace_id": wid, "label": label} for wid, label in workspaces.items()},
        "tabs": {p["tab_id"]: {"tab_id": p["tab_id"], "label": "tab"} for p in panes},
    }


def facts(exists=True, content=True, title="", last=None):
    return {"known": True, "exists": exists, "has_content": content, "title": title, "last_active": last}


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.index = {"sessions": {}}
        self.archive = {"entries": {}}
        patcher = mock.patch.object(agents, "session_facts", return_value=facts(title="Fix the tests", last=T0 - 60))
        self.facts = patcher.start()
        self.addCleanup(patcher.stop)

    def apply(self, panes, event="pane.focused", data=None, t=T0, workspaces=None, session="default"):
        return core.apply(self.index, self.archive, session, snap(panes, workspaces), event, data or {}, t)

    def test_closed_pane_is_archived_under_its_workspace(self):
        self.apply([pane("w1:p1", session="s1")])
        self.assertTrue(self.apply([], event="pane.closed"))
        e = self.archive["entries"]["claude:s1"]
        self.assertEqual((e["herdr_session"], e["workspace_id"], e["workspace_label"]), ("default", "w1", "Work"))
        self.assertEqual(e["title"], "Fix the tests")
        self.assertEqual(e["reason"], "closed")

    def test_closing_a_tab_archives_every_agent_pane_in_it(self):
        self.apply([pane("w1:p1", tab="w1:t1", session="s1"), pane("w1:p2", tab="w1:t1", session="s2"),
                    pane("w1:p3", tab="w1:t2", session="s3")])
        self.apply([pane("w1:p3", tab="w1:t2", session="s3")], event="tab.closed")
        self.assertEqual(sorted(self.archive["entries"]), ["claude:s1", "claude:s2"])

    def test_closing_a_workspace_keeps_its_label(self):
        self.apply([pane("w2:p1", ws="w2", session="s1")], workspaces={"w1": "Work", "w2": "Side"})
        self.apply([], event="workspace.closed", workspaces={"w1": "Work"})
        self.assertEqual(self.archive["entries"]["claude:s1"]["workspace_label"], "Side")

    def test_exit_is_archived(self):
        self.apply([pane("w1:p1", session="s1")])
        self.apply([pane("w1:p1")], event="pane.agent_detected",
                   data={"pane_id": "w1:p1", "released": True}, t=T0 + 5)
        self.assertIn("claude:s1", self.archive["entries"])
        self.assertEqual(self.archive["entries"]["claude:s1"]["reason"], "exited")
        self.assertNotIn("w1:p1", self.index["sessions"]["default"]["panes"])

    def test_release_right_after_a_restart_is_not_an_exit(self):
        self.apply([pane("w1:p1", session="s1")])
        self.apply([pane("w1:p1")], event="startup", t=T0 + 100)
        self.assertFalse(self.apply([pane("w1:p1")], event="pane.agent_detected",
                                    data={"pane_id": "w1:p1", "released": True}, t=T0 + 102))
        self.assertEqual(self.archive["entries"], {})
        self.assertIn("w1:p1", self.index["sessions"]["default"]["panes"])  # kept for the deferred resume
        # Much later, a real /exit of the resumed agent is archived.
        self.apply([pane("w1:p1", session="s1")], t=T0 + 400)
        self.apply([pane("w1:p1")], event="pane.agent_detected",
                   data={"pane_id": "w1:p1", "released": True}, t=T0 + 500)
        self.assertIn("claude:s1", self.archive["entries"])

    def test_restored_pane_closed_without_resuming_is_archived(self):
        self.apply([pane("w1:p1", session="s1")])
        self.apply([pane("w1:p1")], event="startup", t=T0 + 100)
        self.apply([], event="tab.closed", t=T0 + 200)
        self.assertIn("claude:s1", self.archive["entries"])

    def test_new_session_in_the_same_pane_archives_the_old_one(self):
        self.apply([pane("w1:p1", session="s1")])
        self.apply([pane("w1:p1", session="s2")])
        self.assertEqual(list(self.archive["entries"]), ["claude:s1"])
        self.assertEqual(self.archive["entries"]["claude:s1"]["reason"], "replaced")

    def test_live_again_leaves_the_archive(self):
        self.apply([pane("w1:p1", session="s1")])
        self.apply([])
        self.assertIn("claude:s1", self.archive["entries"])
        self.assertTrue(self.apply([pane("w1:p9", session="s1")]))
        self.assertEqual(self.archive["entries"], {})

    def test_session_with_nothing_to_resume_is_skipped(self):
        self.facts.return_value = facts(content=False)
        self.apply([pane("w1:p1", session="s1")])
        self.assertFalse(self.apply([], event="pane.closed"))
        self.assertEqual(self.archive["entries"], {})

    def test_rename_carries_the_archive(self):
        self.apply([pane("w1:p1", session="s1"), pane("w1:p2", session="s2")])
        self.apply([pane("w1:p2", session="s2")])
        self.apply([pane("w1:p2", session="s2")], workspaces={"w1": "Renamed"})
        self.assertEqual(self.archive["entries"]["claude:s1"]["workspace_label"], "Renamed")

    def test_sessions_are_kept_apart(self):
        self.apply([pane("w1:p1", session="s1")], session="default")
        self.apply([pane("w1:p1", session="t1")], session="other")
        self.apply([], session="other")
        self.assertEqual(list(self.archive["entries"]), ["claude:t1"])
        self.assertEqual(self.archive["entries"]["claude:t1"]["herdr_session"], "other")
        self.assertIn("w1:p1", self.index["sessions"]["default"]["panes"])

    def test_generic_title_keeps_the_last_real_one(self):
        self.facts.return_value = facts(title="", last=None)
        self.apply([pane("w1:p1", session="s1", title="✳ Real name")])
        self.apply([pane("w1:p1", session="s1", title="Claude Code")])
        self.apply([])
        self.assertEqual(self.archive["entries"]["claude:s1"]["title"], "Real name")


class PruneAndListTests(unittest.TestCase):
    def entry(self, sid, label="Work", last=T0, agent="claude", session="default"):
        return {"herdr_session": session, "workspace_id": "w1", "workspace_label": label, "tab_label": "",
                "agent": agent, "session_id": sid, "source": None, "cwd": "/p", "title": sid,
                "closed_at": last, "last_active": last, "reason": "closed"}

    def test_prune_by_age_and_by_missing_transcript(self):
        archive = {"entries": {"claude:old": self.entry("old", last=T0 - 40 * 86400),
                               "claude:gone": self.entry("gone"),
                               "claude:ok": self.entry("ok"),
                               "codex:x": self.entry("x", agent="codex", last=T0 - 10 * 86400)}}

        def fake(agent, sid, **kw):
            if agent != "claude":
                return {"known": False, "exists": True, "has_content": True, "title": "", "last_active": None}
            return facts(exists=sid != "gone", last=T0 - 40 * 86400 if sid == "old" else T0)

        with mock.patch.object(agents, "session_facts", side_effect=fake):
            core.prune(archive, {"keep_days": 30}, T0)
        self.assertEqual(sorted(archive["entries"]), ["claude:ok", "codex:x"])

    def test_keep_days_zero_keeps_old_entries(self):
        archive = {"entries": {"codex:x": self.entry("x", agent="codex", last=T0 - 400 * 86400)}}
        with mock.patch.object(agents, "session_facts",
                               return_value={"known": False, "exists": True, "has_content": True,
                                             "title": "", "last_active": None}):
            core.prune(archive, {"keep_days": 0}, T0)
        self.assertIn("codex:x", archive["entries"])

    def test_listing_filters_and_sorts(self):
        archive = {"entries": {"a": self.entry("a", last=T0 - 10), "b": self.entry("b", last=T0),
                               "c": self.entry("c", label="Other"), "d": self.entry("d", session="named")}}
        self.assertEqual([e["session_id"] for e in core.listing(archive, "default", "Work")], ["b", "a"])
        self.assertEqual(len(core.listing(archive, "default")), 3)


class AgentTests(unittest.TestCase):
    def test_resume_commands(self):
        self.assertEqual(agents.resume_argv("claude", "abc"), ["command", "claude", "--resume", "abc"])
        self.assertEqual(agents.resume_argv("copilot", "x"), ["copilot", "--resume=x"])
        self.assertEqual(agents.resume_argv("codex", "c1"), ["command", "codex", "--no-daemon", "resume", "c1"])
        self.assertEqual(agents.resume_argv("letta", "default:ag1"),
                         ["letta", "--conversation", "default", "--agent", "ag1"])
        self.assertIsNone(agents.resume_argv("mystery", "x"))
        self.assertEqual(agents.resume_argv("claude", "abc", {"claude": ["cc", "-r", "{id}"]}), ["cc", "-r", "abc"])

    def test_clean_title(self):
        self.assertEqual(agents.clean_title("✳ Fix the tests"), "Fix the tests")
        self.assertEqual(agents.clean_title("◐ Hyprland titlebar"), "Hyprland titlebar")
        self.assertEqual(agents.clean_title("✳ Claude Code"), "")
        self.assertEqual(agents.clean_title("codex", "codex"), "")

    def test_claude_transcript_facts(self):
        with tempfile.TemporaryDirectory() as d:
            proj = os.path.join(d, "projects", "-p")
            os.makedirs(proj)
            real = os.path.join(proj, "s1.jsonl")
            with open(real, "w") as f:
                f.write('{"type":"user","message":{"content":"<local-command-caveat>x"}}\n')
                f.write('{"type":"user","message":{"content":"Please fix the tests"}}\n')
                f.write('{"type":"ai-title","aiTitle":"Fixing tests"}\n')
            exit_only = os.path.join(proj, "s2.jsonl")
            with open(exit_only, "w") as f:
                f.write('{"type":"user","message":{"content":"<command-name>/exit</command-name>"}}\n')
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": d}):
                f1 = agents.session_facts("claude", "s1")
                f2 = agents.session_facts("claude", "s2")
                f3 = agents.session_facts("claude", "missing")
            self.assertTrue(f1["exists"] and f1["has_content"])
            self.assertEqual(f1["title"], "Fixing tests")
            self.assertTrue(f2["exists"] and not f2["has_content"])
            self.assertFalse(f3["exists"])
            self.assertFalse(agents.session_facts("pi", "x")["known"])


class NameTests(unittest.TestCase):
    def test_default_tab_labels(self):
        for label, number in (("Initial", 1), ("3", 3), ("", None), ("12", None)):
            self.assertTrue(core.is_default_tab_label(label, number), label)
        for label in ("go-public", "Sash", "clip manage"):
            self.assertFalse(core.is_default_tab_label(label, 4), label)

    def test_names_order_and_fallbacks(self):
        e = {"tab_label": "go-public", "tab_number": 15, "pane_label": "", "title": "Omarchy bar widget"}
        self.assertEqual(core.names(e), ("go-public", "Omarchy bar widget"))
        self.assertEqual(core.names(e, "agent"), ("Omarchy bar widget", "go-public"))
        self.assertEqual(core.names(dict(e, tab_label="Initial")), ("Omarchy bar widget", ""))
        self.assertEqual(core.names(dict(e, tab_label="Initial"), "agent"), ("Omarchy bar widget", ""))
        self.assertEqual(core.names(dict(e, pane_label="left"))[0], "left")
        self.assertEqual(core.names(dict(e, title="GO-PUBLIC")), ("go-public", ""))
        self.assertEqual(core.names({"tab_label": "2", "title": ""}), ("(untitled session)", ""))

    def test_archived_entry_keeps_tab_name_and_position(self):
        index, archive = {"sessions": {}}, {"entries": {}}
        p = pane("w1:p1", session="s1")
        s = snap([p])
        s["tabs"][p["tab_id"]].update(label="go-public", number=7)
        with mock.patch.object(agents, "session_facts", return_value=facts(title="Agent title")):
            core.apply(index, archive, "default", s, "pane.focused", {}, T0)
            core.apply(index, archive, "default", snap([]), "tab.closed", {}, T0 + 1)
        e = archive["entries"]["claude:s1"]
        self.assertEqual((e["tab_label"], e["tab_number"], e["title"]), ("go-public", 7, "Agent title"))


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(agents, "session_facts", return_value=facts(title="t", last=T0))
        patcher.start()
        self.addCleanup(patcher.stop)

    def snap_with_tabs(self):
        agent = pane("w2:p1", ws="w2", tab="w2:t1", session="s1", cwd="/banana")
        plain = pane("w2:p2", ws="w2", tab="w2:t2", cwd="/banana/notes")
        other = pane("w1:p1", ws="w1", tab="w1:t1", session="s9")
        sn = snap([agent, plain, other], workspaces={"w1": "Work", "w2": "Banana"})
        sn["tabs"]["w2:t1"].update(workspace_id="w2", label="agent work", number=1)
        sn["tabs"]["w2:t2"].update(workspace_id="w2", label="2", number=2)
        sn["tabs"]["w1:t1"].update(workspace_id="w1", label="Initial", number=1)
        return sn

    def test_tab_layouts_keep_plain_tabs_and_order(self):
        lay = core.tab_layouts(self.snap_with_tabs())["w2"]
        self.assertEqual(lay["label"], "Banana")
        self.assertEqual([(t["number"], t["label"], t["cwd"], t["session_id"]) for t in lay["tabs"]],
                         [(1, "agent work", "/banana", "s1"), (2, "2", "/banana/notes", None)])

    def test_closing_a_workspace_records_it_as_a_unit(self):
        index, archive = {"sessions": {}}, {"entries": {}}
        core.apply(index, archive, "default", self.snap_with_tabs(), "pane.focused", {}, T0)
        only_work = snap([pane("w1:p1", ws="w1", tab="w1:t1", session="s9")], workspaces={"w1": "Work"})
        core.apply(index, archive, "default", only_work, "workspace.closed", {}, T0 + 5)
        closed = core.closed_workspaces(archive, "default")
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["label"], "Banana")
        self.assertEqual(len(closed[0]["tabs"]), 2)
        # Its agent session is also archived on its own, under Banana.
        self.assertEqual(archive["entries"]["claude:s1"]["workspace_label"], "Banana")
        # Closing a tab is not closing a workspace.
        core.apply(index, archive, "default", snap([], workspaces={"w1": "Work"}), "tab.closed", {}, T0 + 9)
        self.assertEqual(len(core.closed_workspaces(archive, "default")), 1)

    def test_closed_workspaces_age_out(self):
        archive = {"entries": {}, "workspaces": {"k": {"herdr_session": "default", "label": "B",
                                                       "closed_at": T0 - 31 * 86400, "tabs": [{}]}}}
        core.prune(archive, {"keep_days": 30}, T0)
        self.assertEqual(archive["workspaces"], {})


class RestoreTests(unittest.TestCase):
    def test_restore_skips_a_session_that_is_already_open(self):
        record = {"key": "k", "label": "Banana", "tabs": [
            {"number": 1, "label": "notes", "cwd": "/tmp", "agent": None, "session_id": None},
            {"number": 2, "label": "agent work", "cwd": "/tmp", "agent": "claude", "session_id": "s1"}]}
        live = snap([pane("w1:p1", session="s1")])
        calls = []
        with mock.patch.object(core.herdr, "snapshot", return_value=live), \
             mock.patch.object(core.herdr, "run", side_effect=lambda *a: calls.append(a) or {
                 "workspace": {"workspace_id": "w9"}, "tab": {"tab_id": "w9:t1"}, "root_pane": {"pane_id": "w9:p1"}}), \
             mock.patch.object(core.herdr, "new_tab", side_effect=lambda *a, **k: calls.append(("new_tab",) + a)), \
             mock.patch.object(core.herdr, "run_in_pane", side_effect=lambda *a: calls.append(("run_in_pane",) + a)), \
             mock.patch.object(core.store, "locked", return_value=mock.MagicMock()), \
             mock.patch.object(core.store, "load_archive", return_value={"entries": {}, "workspaces": {}}), \
             mock.patch.object(core.store, "save_archive"):
            self.assertIsNone(core.restore_workspace(record, {"resume": {}}))
        self.assertFalse(any(c[0] == "run_in_pane" for c in calls), calls)
        self.assertFalse(any(c[0] == "new_tab" for c in calls), calls)  # only "notes", in the new workspace's first tab


class MoreAgentTests(unittest.TestCase):
    def test_codex_facts_from_its_database(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            rollout = os.path.join(d, "rollout.jsonl")
            open(rollout, "w").close()
            con = sqlite3.connect(os.path.join(d, "state_5.sqlite"))
            con.execute("create table threads (id text, rollout_path text, name text, title text, "
                        "first_user_message text, updated_at integer)")
            con.execute("insert into threads values ('c1', ?, 'Confirm OK', 'Reply OK', 'Reply OK', 1795288692)", (rollout,))
            con.execute("insert into threads values ('c2', '/gone.jsonl', '', 'x', 'x', 1)")
            con.commit()
            con.close()
            with mock.patch.dict(os.environ, {"CODEX_HOME": d}):
                f1, f2, f3 = (agents.session_facts("codex", i) for i in ("c1", "c2", "c3"))
        self.assertEqual((f1["exists"], f1["has_content"], f1["title"], f1["last_active"]),
                         (True, True, "Confirm OK", 1795288692.0))
        self.assertFalse(f2["exists"])
        self.assertTrue(f3["known"] and not f3["exists"])

    def test_codex_unknown_schema_is_unknown(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            con = sqlite3.connect(os.path.join(d, "state_9.sqlite"))
            con.execute("create table threads (id text)")
            con.commit()
            con.close()
            with mock.patch.dict(os.environ, {"CODEX_HOME": d}):
                self.assertFalse(agents.session_facts("codex", "c1")["known"])

    def test_grok_facts_from_its_summary(self):
        with tempfile.TemporaryDirectory() as d:
            sdir = os.path.join(d, "sessions", "%2Ftmp", "g1")
            os.makedirs(sdir)
            with open(os.path.join(sdir, "summary.json"), "w") as f:
                json.dump({"session_summary": "Fix the build", "num_messages": "4",
                           "last_active_at": "2026-11-21T19:19:03.852787919Z"}, f)
            os.makedirs(os.path.join(d, "sessions", "%2Ftmp", "g2"))
            with open(os.path.join(d, "sessions", "%2Ftmp", "g2", "summary.json"), "w") as f:
                json.dump({"session_summary": "", "num_messages": "1"}, f)
            with mock.patch.dict(os.environ, {"GROK_HOME": d}):
                g1, g2, g3 = (agents.session_facts("grok", i) for i in ("g1", "g2", "g3"))
        self.assertEqual((g1["title"], g1["has_content"]), ("Fix the build", True))
        self.assertAlmostEqual(g1["last_active"], 1795288743.852788, places=3)
        self.assertFalse(g2["has_content"])
        self.assertFalse(g3["exists"])

    def test_missing_agent_folder_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"GROK_HOME": d, "CLAUDE_CONFIG_DIR": d, "CODEX_HOME": d}):
                for agent in ("grok", "claude", "codex"):
                    self.assertFalse(agents.session_facts(agent, "x")["known"], agent)

    def test_titles_lose_agent_decorations(self):
        self.assertEqual(agents.clean_title("Confirm OK | earmark-live-check", "codex"), "Confirm OK")
        self.assertEqual(agents.clean_title("Fix the build - grok", "grok"), "Fix the build")


class KeepDaysTests(unittest.TestCase):
    def entry(self, agent, last):
        return {"herdr_session": "default", "workspace_id": "w1", "workspace_label": "Work", "agent": agent,
                "session_id": "x", "title": "", "closed_at": last, "last_active": last}

    def test_unset_follows_the_agent_where_known(self):
        archive = {"entries": {"claude:x": self.entry("claude", T0 - 200 * 86400),
                               "pi:x": self.entry("pi", T0 - 31 * 86400),
                               "pi:y": dict(self.entry("pi", T0 - 5 * 86400), session_id="y")}}

        def fake(agent, sid, **kw):
            if agent == "claude":
                return facts(last=T0 - 200 * 86400)  # still there: Claude keeps it
            return {"known": False, "exists": True, "has_content": True, "title": "", "last_active": None}

        with mock.patch.object(agents, "session_facts", side_effect=fake):
            core.prune(archive, {"keep_days": None}, T0)
        self.assertEqual(sorted(archive["entries"]), ["claude:x", "pi:y"])


class ConfigTests(unittest.TestCase):
    def test_simple_toml_parser(self):
        from earmark import config
        data = config.parse_simple_toml(
            '# Earmark\nkeep_days = 90  # three months\nreport_count = false\ntitle_first = "agent"\n\n'
            '[resume]\nclaude = ["claude", "--resume", "{id}"]\n')
        self.assertEqual(data, {"keep_days": 90, "report_count": False, "title_first": "agent",
                                "resume": {"claude": ["claude", "--resume", "{id}"]}})
        with self.assertRaises(ValueError):
            config.parse_simple_toml("keep_days = ninety")

    def test_load_uses_the_fallback_without_tomllib(self):
        from earmark import config
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "config.toml"), "w") as f:
                f.write("keep_days = 7\ntitle_first = \"agent\"\n")
            with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONFIG_DIR": d}), mock.patch.object(config, "tomllib", None):
                cfg = config.load()
        self.assertEqual((cfg["keep_days"], cfg["title_first"]), (7, "agent"))


class CacheTests(unittest.TestCase):
    def test_unchanged_source_is_not_read_again(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s1.jsonl")
            open(src, "w").close()
            archive = {"entries": {"claude:s1": {"herdr_session": "default", "workspace_label": "Work",
                                                 "agent": "claude", "session_id": "s1", "title": "",
                                                 "closed_at": T0, "last_active": T0}}}
            result = dict(facts(title="T", last=T0), source=src)
            with mock.patch.object(agents, "session_facts", return_value=result) as f:
                core.prune(archive, {"keep_days": None}, T0)
                core.prune(archive, {"keep_days": None}, T0)
                self.assertEqual(f.call_count, 1)
                os.utime(src, ns=(1, 1))  # the file changed: read it again
                core.prune(archive, {"keep_days": None}, T0)
                self.assertEqual(f.call_count, 2)


if __name__ == "__main__":
    unittest.main()
