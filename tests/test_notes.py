"""1.2, PLAN phase L: workspace notes (earmark/notes.py, earmark/noteui.py),
their move with closed workspaces, the sidebar mark and the popup's logic."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agents, config, core, herdr, notes, noteui, store  # noqa: E402
from test_suspend import pane, snap  # noqa: E402
from test_review1 import StateDir  # noqa: E402

T0 = 1_800_000_000.0


class StoreTests(StateDir):
    def test_write_read_version_and_empty_removes(self):
        self.assertEqual(notes.read("default", "w1"), "")
        notes.write("default", "w1", "Next: the review")
        self.assertEqual(notes.read("default", "w1"), "Next: the review\n")
        self.assertEqual(notes.noted("default"), {"w1"})
        with self.assertRaises(ValueError):  # an empty write is more often a mistake
            notes.write("default", "w1", "  \n")
        notes.write("default", "w1", "  \n", clear=True)
        self.assertFalse(os.path.exists(notes.note_path("default", "w1")))
        self.assertEqual(notes.noted("default"), set())

    def test_a_write_based_on_an_old_version_is_refused(self):
        notes.write("default", "w1", "one\n")
        v = notes.version("one\n")
        notes.write("default", "w1", "two\n", expect=v)
        with self.assertRaises(notes.Conflict):
            notes.write("default", "w1", "three\n", expect=v)
        self.assertEqual(notes.read("default", "w1"), "two\n")

    def test_sessions_and_odd_ids_stay_apart(self):
        notes.write("default", "w1", "a")
        notes.write("named", "w1", "b")
        notes.write("default", "../x", "c")
        self.assertEqual((notes.read("default", "w1"), notes.read("named", "w1")), ("a\n", "b\n"))
        self.assertTrue(os.path.dirname(notes.note_path("default", "../x")).endswith(os.path.join("notes", "default")))

    def test_too_long(self):
        with self.assertRaises(ValueError):
            notes.write("default", "w1", "x" * (notes.LIMIT + 1))

    def test_retire_only_the_text_that_was_saved(self):
        notes.write("default", "w1", "kept\n")
        notes.retire("default", "w1", "something else\n")
        self.assertEqual(notes.read("default", "w1"), "kept\n")
        notes.retire("default", "w1", "kept\n")
        self.assertEqual(notes.read("default", "w1"), "")

    def test_put_back_below_a_note_already_there(self):
        notes.put_back("default", "w2", "old note\n")
        self.assertEqual(notes.read("default", "w2"), "old note\n")
        notes.write("default", "w3", "live note\n")
        notes.put_back("default", "w3", "old note\n")
        self.assertEqual(notes.read("default", "w3"), "live note\n\n---\n\nold note\n")
        notes.put_back("default", "w3", "")
        self.assertIn("live note", notes.read("default", "w3"))


class CliTests(StateDir):
    def cli(self, *argv, stdin="", env=None):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env if env is not None else {"HERDR_WORKSPACE_ID": "w1"}), \
                mock.patch.object(notes, "_label", return_value="Earmark"):
            code = notes.cli(list(argv), stdin=io.StringIO(stdin), out=out)
        return code, out.getvalue()

    def test_show_json_write_with_the_version(self):
        self.assertEqual(self.cli("write", stdin="# Earmark\nNext: L4\n"), (0, ""))
        code, out = self.cli("show", "--json")
        data = json.loads(out)
        self.assertEqual((code, data["label"], data["workspace"], data["text"]), (0, "Earmark", "w1", "# Earmark\nNext: L4\n"))
        self.assertEqual(self.cli("write", "--expect", data["version"], stdin="Done.\n")[0], 0)
        self.assertEqual(self.cli("write", "--expect", data["version"], stdin="Again.\n")[0], 3)  # it changed
        self.assertEqual(self.cli("show"), (0, "Done.\n"))

    def test_outside_herdr_and_options(self):
        self.assertEqual(self.cli("show", env={})[0], 2)
        self.assertEqual(self.cli("write", "--workspace", "w7", "--session", "x", stdin="hi", env={})[0], 0)
        self.assertEqual(notes.read("x", "w7"), "hi\n")
        self.assertTrue(self.cli("path")[1].strip().endswith("w1.md"))
        self.assertEqual(self.cli("nonsense")[0], 2)


class TabsTests(StateDir):
    """`note show --json`'s tabs: what the /herdr-note skill learns the
    other tabs from."""

    def test_names_states_and_suspended_tabs(self):
        live = snap([pane("w1:p1", status="working", tab="w1:t1"), pane("w1:p2", "s2", status="blocked", tab="w1:t2"),
                     pane("w1:p3", session=None, tab="w1:t3"), pane("w1:p4", session=None, tab="w1:t3"),
                     pane("w2:p1", "s9", ws="w2", tab="w2:t1")], {"w1": "Work", "w2": "Other"})
        live["tabs"]["w1:t1"]["label"] = "Refactor"
        live["tabs"]["w1:t2"].update(label="2", number=2)
        live["tabs"]["w1:t3"]["label"] = "Card backs"
        store.save_index({"sessions": {"default": {"panes": {}, "suspended": {
            "w1:p4": {"agent": "claude", "session_id": "s4", "title": "Card backs"}}}}})
        with mock.patch.object(herdr, "snapshot", return_value=live), \
                mock.patch.object(agents, "claude_transcript", side_effect=lambda sid, d=None: f"/t/{sid}.jsonl"), \
                mock.patch.object(agents, "recent_exchange",
                                  side_effect=lambda a, p: {"requests": [f"asked {p}"], "replies": [], "tools": []}):
            tabs = notes.workspace_tabs("default", "w1", here="w1:t1")
        self.assertEqual([t["tab"] for t in tabs], ["Refactor", None, "Card backs"])
        self.assertEqual([t["here"] for t in tabs], [True, False, False])
        self.assertEqual([(a["state"], a["requests"]) for t in tabs for a in t["agents"]],
                         [("working", ["asked /t/s1.jsonl"]), ("needs the user", ["asked /t/s2.jsonl"]),
                          ("suspended", ["asked /t/s4.jsonl"])])
        self.assertNotIn("transcript", tabs[0]["agents"][0])  # no file to open unless the user opted in
        self.settings("[notes]\nread_transcripts = true\n")
        with mock.patch.object(herdr, "snapshot", return_value=live), \
                mock.patch.object(agents, "claude_transcript", side_effect=lambda sid, d=None: f"/t/{sid}.jsonl"):
            tabs = notes.workspace_tabs("default", "w1", here="w1:t1")
        self.assertEqual(tabs[0]["agents"][0]["transcript"], "/t/s1.jsonl")
        self.assertEqual(tabs[0]["agents"][0]["title"], "Fix the tests")

    def test_herdr_not_answering_still_shows_the_note(self):
        notes.write("default", "w1", "kept")
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HERDR_WORKSPACE_ID": "w1"}), \
                mock.patch.object(notes, "_label", return_value=""), \
                mock.patch.object(herdr, "snapshot", side_effect=herdr.HerdrError("down")):
            self.assertEqual(notes.cli(["show", "--json"], out=out), 0)
        data = json.loads(out.getvalue())
        self.assertEqual((data["text"], data["tabs"]), ("kept\n", None))


class MoveWithTheWorkspaceTests(StateDir):
    def test_closing_keeps_the_note_with_the_workspace_and_the_file_goes_after(self):
        notes.write("default", "w1", "where it stands\n")
        archive = {"entries": {}}
        self.assertTrue(core.record_closed_workspace(archive, "default", "w1",
                                                     {"label": "Work", "tabs": [{"label": "a"}]}, T0))
        rec = next(iter(archive["workspaces"].values()))
        self.assertEqual(rec["note"], "where it stands\n")
        self.assertEqual(notes.read("default", "w1"), "where it stands\n")  # not before the archive is saved
        core.retire_notes(archive, "default", T0)
        self.assertEqual(notes.read("default", "w1"), "")  # a new workspace reusing w1 starts empty

    def test_only_this_closes_notes_are_retired(self):
        # an older close of w1 (Herdr reused the id) whose note reads the same as the new w1's
        archive = {"entries": {}, "workspaces": {"default|w1|1": {
            "herdr_session": "default", "workspace_id": "w1", "label": "Old", "closed_at": T0 - 100,
            "tabs": [], "note": "same\n"}}}
        notes.write("default", "w1", "same\n")
        core.retire_notes(archive, "default", T0)
        self.assertEqual(notes.read("default", "w1"), "same\n")

    def test_a_closed_workspace_without_a_note_has_none(self):
        archive = {"entries": {}}
        core.record_closed_workspace(archive, "default", "w1", {"label": "Work", "tabs": [{"label": "a"}]}, T0)
        self.assertNotIn("note", next(iter(archive["workspaces"].values())))

    def test_restoring_brings_the_note_back(self):
        record = {"key": "default|w1|1", "herdr_session": "default", "workspace_id": "w1", "label": "Work",
                  "closed_at": T0, "tabs": [{"label": "notes", "cwd": "/", "session_id": None}], "note": "back\n"}
        store.save_archive({"entries": {}, "workspaces": {record["key"]: record}})

        def run(*args, **kw):
            if args[:2] == ("workspace", "create"):
                return {"workspace": {"workspace_id": "w5"}, "tab": {"tab_id": "w5:t1"}, "root_pane": {"pane_id": "w5:p1"}}
            return {}
        with mock.patch.object(herdr, "run", side_effect=run), \
                mock.patch.object(herdr, "snapshot", return_value=snap([], {"w9": "Other"})):  # no live "Work"
            self.assertIsNone(core.restore_workspace(record, config.load()))
        self.assertEqual(notes.read("default", "w5"), "back\n")
        self.assertEqual(store.load_archive()["workspaces"], {})

    def test_the_sidebar_mark(self):
        notes.write("default", "w1", "x")
        index = {"sessions": {"default": {"panes": {}, "boot": 1}}}
        cfg = dict(config.DEFAULTS, sidebar=dict(config.SIDEBAR_DEFAULTS, counts=["note", "done"]),
                   colors=config.COLOR_DEFAULTS)
        reports = core.pending_reports(index, {"entries": {}}, "default", snap([], {"w1": "Work", "w2": "Other"}),
                                       cfg, {"sessions": {}})
        self.assertEqual([(w, t) for w, t, _ in reports], [("w1", {"earmark_note": "✎"})])


class RenderTests(unittest.TestCase):
    def test_markdown_lightly(self):
        lines = noteui.render("# Earmark\n- [ ] L4\n- [x] K1\n* item\n```\ncode\n```\nplain", 40)
        self.assertEqual(lines, [("Earmark", "bold"), ("☐ L4", "plain"), ("☑ K1", "plain"), ("• item", "plain"),
                                 ("code", "dim"), ("plain", "plain")])

    def test_wrapping_at_spaces(self):
        self.assertEqual(noteui.wrap("aaa bbb ccc", 7), ["aaa bbb", "ccc"])
        self.assertEqual(noteui.wrap("a" * 10, 4), ["aaaa", "aaaa", "aa"])
        self.assertEqual(noteui.wrap("日本語です", 4), ["日本", "語で", "す"])
        self.assertEqual(noteui.render("x\x1b[31m", 10), [("x [31m", "plain")])  # escapes never reach the screen


class AskClaudeTests(StateDir):
    def setUp(self):
        super().setUp()
        skill = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "skills", "herdr-note")
        os.makedirs(skill, exist_ok=True)
        with open(os.path.join(skill, "SKILL.md"), "w") as f:
            f.write("x")
        self.addCleanup(lambda: os.path.exists(os.path.join(skill, "SKILL.md")) and os.remove(os.path.join(skill, "SKILL.md")))

    def candidates(self, panes, drafts):
        with mock.patch.object(herdr, "snapshot", return_value=snap(panes)), \
                mock.patch.object(herdr, "read_screen", side_effect=lambda pid, rows=None: pid), \
                mock.patch.object(agents, "draft_text", side_effect=lambda screen, a: drafts.get(screen, "")):
            return noteui.candidates("default", "w1")

    def test_only_idle_claudes_with_an_empty_prompt(self):
        ready, why = self.candidates(
            [pane("w1:p1", status="idle"), pane("w1:p2", "s2", status="working"), pane("w1:p3", "s3", status="done"),
             pane("w1:p4", "s4", status="idle"), pane("w1:p5", "s5", status="idle"),
             pane("w1:p6", "s6", status="blocked"), pane("w2:p1", "s7", ws="w2", status="idle"),
             pane("w1:p7", "s8", status="idle", agent="codex")],
            {"w1:p4": "half a sentence", "w1:p5": None})
        self.assertEqual([p for p, _ in ready], ["w1:p1", "w1:p3"])
        self.assertEqual(len(why), 4)  # busy, unsent text, can't read, waiting on you

    def test_without_the_skill_nobody_is_asked(self):
        skill = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "skills", "herdr-note", "SKILL.md")
        os.rename(skill, skill + ".away")
        self.addCleanup(os.rename, skill + ".away", skill)
        ready, why = self.candidates([pane("w1:p1", status="idle")], {})
        self.assertEqual(ready, [])
        self.assertIn("skill", why[0])

    def test_the_request_goes_through_herdrs_agent_prompt(self):
        with mock.patch.object(herdr, "run") as run:
            noteui.ask("w1:p3")
        run.assert_called_once_with("agent", "prompt", "w1:p3", "/herdr-note")

    def test_one_is_asked_at_once_several_are_offered(self):
        popup = noteui.NotePopup("default", "w1", "Work")
        with mock.patch.object(noteui, "candidates", return_value=([("w1:p1", "Dev")], [])), \
                mock.patch.object(noteui, "ask") as ask:
            popup.on_key(None, "u")
        ask.assert_called_once_with("w1:p1")
        self.assertIn("Dev", popup.message)
        with mock.patch.object(noteui, "candidates", return_value=([("w1:p1", "Dev"), ("w1:p2", "Docs")], [])), \
                mock.patch.object(noteui, "ask") as ask:
            popup.on_key(None, "u")
            ask.assert_not_called()
            popup.on_key(None, "2")
        ask.assert_called_once_with("w1:p2")
        with mock.patch.object(noteui, "candidates", return_value=([], ["Dev: busy"])):
            popup.on_key(None, "u")
        self.assertIn("busy", popup.message)


class EditTests(StateDir):
    def editor(self, script):
        """A stand-in editor, the only one the popup can find (a real nvim
        must never start from the suite, whatever a mutant does to VISUAL)."""
        path = os.path.join(self.dir.name, "ed")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + script)
        os.chmod(path, 0o755)
        for p in (mock.patch.dict(os.environ, {"VISUAL": path, "EDITOR": path}),
                  mock.patch.object(noteui.shutil, "which", side_effect=lambda n: n if n == path else None),
                  mock.patch.object(noteui.curses, "endwin")):
            p.start()
            self.addCleanup(p.stop)
        return path

    def test_the_editor_round_trip_and_an_emptied_note(self):
        popup = noteui.NotePopup("default", "w1")
        self.editor("printf '# Plan\\nNext: N1\\n' > \"$1\"\n")
        scr = mock.Mock()
        popup.on_key(scr, "e")
        self.assertEqual(popup.note, "# Plan\nNext: N1\n")
        self.editor("printf '  \\n' > \"$1\"\n")
        popup.on_key(scr, "e")
        self.assertFalse(os.path.exists(notes.note_path("default", "w1")))

    def test_the_editor_gets_a_copy_and_a_write_meanwhile_is_kept(self):  # review 10 R201
        notes.write("default", "w1", "old")
        real = notes.note_path("default", "w1")
        seen = os.path.join(self.dir.name, "seen")
        self.editor(f"echo \"$1\" > {seen}\nprintf 'mine\\n' > \"$1\"\n"
                    f"printf 'claude wrote this\\n' > {real}\n")  # a Claude saves while the editor is open
        popup = noteui.NotePopup("default", "w1")
        popup.on_key(mock.Mock(), "e")
        with open(seen) as f:
            self.assertNotEqual(f.read().strip(), real)
        self.assertEqual(notes.read("default", "w1"), "claude wrote this\n\n---\n\nmine\n")
        self.assertIn("changed while you edited", popup.message)
        self.assertEqual([n for n in os.listdir(os.path.dirname(real)) if n.startswith(".edit-")], [])

    def test_editor_fallbacks(self):
        with mock.patch.dict(os.environ, {"VISUAL": "", "EDITOR": "/nonexistent/editor"}), \
                mock.patch.object(noteui.shutil, "which", side_effect=lambda n: "/bin/vi" if n == "vi" else None):
            self.assertEqual(noteui.editor_argv(), ["vi"])
        with mock.patch.dict(os.environ, {"VISUAL": "code --wait"}), \
                mock.patch.object(noteui.shutil, "which", return_value="/usr/bin/code"):
            self.assertEqual(noteui.editor_argv(), ["code", "--wait"])


if __name__ == "__main__":
    unittest.main()
