"""1.2, PLAN phase M: Earmark's values in Herdr's sidebar (earmark/sidebar.py),
their settings, and the workspace counts the hooks send.

Widths are checked against what the M1 preview showed on Herdr 0.9.5 with a
26-column sidebar: 21 columns for an agent's second line, and a workspace's
name line one column wider than Earmark assumes (it always counts a
scrollbar)."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import config, core, herdr, sidebar, store  # noqa: E402
from test_suspend import pane, snap  # noqa: E402
from test_review1 import StateDir  # noqa: E402

ALL = list(config.COUNT_ITEMS)
FIVE = ["blocked", "working", "done", "suspended", "archived"]
ROW = ["model", "effort", "context"]


def _fnv(data):
    """FNV-1a 64, written out independently of sidebar.py."""
    h = 14695981039346656037
    for b in data:
        h ^= b
        h = (h * 1099511628211) % (1 << 64)
    return h


def values(**kw):
    out = dict.fromkeys(config.COUNT_ITEMS, 0)
    out.update(kw)
    return out


class HerdrFiles(unittest.TestCase):
    """Herdr's config.toml and session.json, written for one test."""

    def setUp(self):
        self.herdr_config = os.environ["HERDR_CONFIG_PATH"]
        self.herdr_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "herdr")
        os.makedirs(os.path.join(self.herdr_dir, "sessions", "named"), exist_ok=True)
        self.addCleanup(self.clear)

    def clear(self):
        for path in (self.herdr_config, os.path.join(self.herdr_dir, "session.json"),
                     sidebar.client_preferences("default"), sidebar.client_preferences("named")):
            if os.path.exists(path):
                os.remove(path)

    def herdr_settings(self, text):
        with open(self.herdr_config, "w") as f:
            f.write(text)

    def dragged(self, width, session="default"):
        """What Herdr 0.9.5's client writes when the sidebar is dragged: its
        preferences file, named after its socket's path (FNV-1a), with the
        width only while dragged (src/client/shell/preferences.rs)."""
        path = sidebar.client_preferences(session)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"sidebar_section_split": 0.5, **({"sidebar_width": width} if width else {})}, f)


class WidthTests(HerdrFiles):
    def test_the_default_width_and_the_preview_measurements(self):
        self.assertEqual(sidebar.sidebar_width(), 26)
        self.assertEqual(sidebar.agent_line_width(26, 1), 21)  # measured: "Opus 5.5 · high · 12%" fits, 22 doesn't
        self.assertEqual(sidebar.space_line_width(26, 0), 21)  # measured 22 without a scrollbar; one assumed
        self.assertEqual(sidebar.agent_line_width(26, 0), 23)
        self.assertEqual(sidebar.space_line_width(26, 1), 19)

    def test_the_configured_width_clamped(self):
        self.herdr_settings("[ui]\nsidebar_width = 30\n")
        self.assertEqual(sidebar.sidebar_width(), 30)
        self.herdr_settings("[ui]\nsidebar_width = 80\n")
        self.assertEqual(sidebar.sidebar_width(), 36)
        self.herdr_settings("[ui]\nsidebar_width = 80\nsidebar_max_width = 50\n")
        self.assertEqual(sidebar.sidebar_width(), 50)
        self.herdr_settings("[ui]\nsidebar_width = 5\n")
        self.assertEqual(sidebar.sidebar_width(), 18)
        self.herdr_settings("[ui]\nsidebar_width = 30\nsidebar_min_width = 40\nsidebar_max_width = 20\n")
        self.assertEqual(sidebar.sidebar_width(), 30)  # bounds that make no sense: Herdr's own

    def test_a_dragged_width_wins_per_session(self):
        self.herdr_settings("[ui]\nsidebar_width = 30\n")
        self.dragged(33)
        self.assertEqual(sidebar.sidebar_width(), 33)
        self.assertEqual(sidebar.sidebar_width("named"), 30)
        self.dragged(24, "named")
        self.assertEqual(sidebar.sidebar_width("named"), 24)
        self.dragged(None)
        self.assertEqual(sidebar.sidebar_width(), 30)  # not dragged: the setting

    def test_the_preferences_file_is_the_clients(self):  # review 9 R171
        # The client's own name for the maintainer's real file: FNV-1a 64 of
        # "<config>/herdr/herdr-client.sock" (Herdr's preferences.rs tests use the same function).
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/home/u/.config", "XDG_STATE_HOME": "/home/u/.local/state"}):
            self.assertEqual(sidebar.client_preferences("default"),
                             "/home/u/.local/state/herdr/client-shell/local-" +
                             format(_fnv(b"/home/u/.config/herdr/herdr-client.sock"), "016x") + ".json")
            self.assertIn("/client-shell/local-", sidebar.client_preferences("named"))
            self.assertNotEqual(sidebar.client_preferences("named"), sidebar.client_preferences("default"))
        self.assertEqual(_fnv(b"/run/herdr/one.sock"), _fnv(b"/run/herdr/one.sock"))
        # session.json's field is always null in Herdr 0.9.5: never read
        with open(os.path.join(self.herdr_dir, "session.json"), "w") as f:
            json.dump({"version": 1, "workspaces": [], "sidebar_width": 33}, f)
        self.assertEqual(sidebar.sidebar_width(), 26)

    def test_odd_files_fall_back(self):
        with open(os.path.join(self.herdr_dir, "session.json"), "w") as f:
            f.write("{nope")
        self.herdr_settings("[ui]\nsidebar_width = true\n")
        self.assertEqual(sidebar.sidebar_width(), 26)

    def test_wide_characters_take_two_columns(self):
        self.assertEqual(sidebar.text_width("Pager"), 5)
        self.assertEqual(sidebar.text_width("日本"), 4)
        self.assertEqual(sidebar.text_width("é"), 1)
        self.assertEqual(sidebar.text_width(sidebar.NOTE_MARK), 1)


class CountTests(unittest.TestCase):
    def test_counts_by_state_done_and_idle_together(self):
        s = snap([pane("w1:p1", status="blocked"), pane("w1:p2", "s2", status="working"),
                  pane("w1:p3", "s3", status="done"), pane("w1:p4", "s4", status="idle"),
                  pane("w1:p5", session=None), pane("w2:p1", "s5", ws="w2", status="working")],
                 {"w1": "Work", "w2": "Other"})
        v = sidebar.count_values(s, "w1", 2, 7, True)
        self.assertEqual(v, {"blocked": 1, "working": 1, "done": 2, "suspended": 2, "archived": 7, "note": 1})

    def test_same_line_drops_from_the_right_never_the_name(self):
        v = values(blocked=1, working=2, done=2, suspended=3, archived=27)
        self.assertEqual(sidebar.fit_counts("Garden", v, FIVE, "same", 26),
                         [("blocked", "1"), ("working", "2"), ("done", "2")])
        self.assertEqual(sidebar.fit_counts("Weather Desk", v, FIVE, "same", 26), [("blocked", "1")])
        self.assertEqual(sidebar.fit_counts("A very long workspace name", v, FIVE, "same", 26), [])
        self.assertEqual(len(sidebar.fit_counts("Garden", v, FIVE, "same", 36)), 5)

    def test_the_budget_is_exact(self):
        # name line 21: icon 1 + space 1 + name, then " · n" per count
        self.assertEqual(sidebar.fit_counts("x" * 15, values(done=1), FIVE, "same", 26), [("done", "1")])
        self.assertEqual(sidebar.fit_counts("x" * 16, values(done=1), FIVE, "same", 26), [])
        self.assertEqual(len(sidebar.fit_counts("", values(done=1, archived=1), FIVE, "new", 26)), 2)
        self.assertEqual(sidebar.fit_counts("", values(done=10 ** 18, archived=1), FIVE, "new", 26),
                         [("done", str(10 ** 18))])  # 19 columns: the line's whole width

    def test_once_one_doesnt_fit_the_rest_go_too(self):
        # "27" (5 columns) doesn't fit 4; "1" would, but it's to its right: the order means priority
        v = values(archived=27, done=1)
        self.assertEqual(sidebar.fit_counts("x" * 15, v, ["archived", "done"], "same", 26), [])
        self.assertEqual(sidebar.fit_counts("x" * 15, v, ["done", "archived"], "same", 26), [("done", "1")])

    def test_a_line_of_their_own_holds_them_all(self):
        v = values(blocked=1, working=2, done=2, suspended=3, archived=27)
        self.assertEqual([t for _, t in sidebar.fit_counts("Weather Desk", v, FIVE, "new", 26)],
                         ["1", "2", "2", "3", "27"])

    def test_zeros_hidden_order_and_the_note_mark(self):
        v = values(working=0, done=3, archived=9, note=1)
        self.assertEqual(sidebar.fit_counts("W", v, ["note", "archived", "done"], "new", 30),
                         [("note", sidebar.NOTE_MARK), ("archived", "9"), ("done", "3")])
        self.assertEqual(sidebar.fit_counts("W", v, [], "same", 30), [])

    def test_tokens_set_and_clear_every_count(self):
        tokens = sidebar.count_tokens([("done", "3")])
        self.assertEqual(tokens["earmark_done"], "3")
        self.assertEqual(sorted(tokens), sorted(sidebar.COUNT_TOKENS))
        self.assertEqual([k for k, v in tokens.items() if v], ["earmark_done"])


class AgentRowTests(unittest.TestCase):
    def test_short_forms(self):
        self.assertEqual([sidebar.short_effort(e) for e in ("low", "medium", "high", "xhigh", "max", "Ultra")],
                         ["l", "m", "h", "xh", "mx", "u"])
        self.assertEqual(sidebar.short_effort("turbo"), "tu")
        self.assertEqual([sidebar.short_model(m) for m in ("Opus 5.5", "Sonnet 5.5", "GPT-6.2-Sol", "grok-4.7",
                                                           "Claude Opus 5.5", "Opus 5.5 (1M context)", "Default",
                                                           "4o-mini")],
                         ["O5.5", "S5.5", "G6.2S", "g4.7", "O5.5", "O5.5", "Defa", "4om"])

    def test_stages_only_as_far_as_needed(self):
        cases = [(("Opus 5.5", "xhigh", 9), ("Opus 5.5", "xhigh", "9%")),       # 21: fits
                 (("Opus 5.5", "xhigh", 96), ("Opus 5.5", "xh", "96%")),       # stage 1
                 (("Sonnet 5.5", "medium", 73), ("Sonnet 5.5", "m", "73%")),
                 (("Sonnet 5.5", "xhigh", 100), ("S5.5", "xh", "100%"))]       # stage 2
        for (m, e, p), want in cases:
            self.assertEqual(sidebar.fit_agent(m, e, p, ROW, 26), want, m)

    def test_later_stages_drop_effort_then_model_never_the_percent(self):
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 50, ROW, 20), ("O5.5", "xh", "50%"))  # 15 columns
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 50, ROW, 18), ("O5.5", None, "50%"))  # 13
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 50, ROW, 15), ("O5.5", None, "50%"))  # 10: exactly
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 50, ROW, 14), (None, None, "50%"))   # 9
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 100, ROW, 5), (None, None, "100%"))  # even too long

    def test_the_show_list(self):
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 9, ["context"], 26), (None, None, "9%"))
        self.assertEqual(sidebar.fit_agent("Opus 5.5", "xhigh", 9, ["model", "effort"], 26), ("Opus 5.5", "xhigh", None))
        self.assertEqual(sidebar.fit_agent("Opus 5.5", None, None, ROW, 26), ("Opus 5.5", None, None))

    def test_one_context_token_by_level(self):
        side = dict(config.SIDEBAR_DEFAULTS)
        for percent, band in ((0, 1), (69, 1), (70, 2), (84, 2), (85, 3), (95, 4), (120, 4)):
            tokens = sidebar.agent_tokens("Opus 5.5", "high", percent, side, 26)
            self.assertEqual([k for k in sidebar.CONTEXT_TOKENS if tokens[k]], [f"earmark_ctx_{band}"], percent)
        self.assertEqual(set(sidebar.agent_tokens("X", "low", None, side, 26)[k] for k in sidebar.CONTEXT_TOKENS),
                         {None})

    def test_values_are_cleaned(self):
        tokens = sidebar.agent_tokens("Opus\x1b[31m 5.5\n", "hi\tgh", 5, dict(config.SIDEBAR_DEFAULTS), 36)
        self.assertEqual(tokens["earmark_model"], "Opus[31m 5.5")
        self.assertEqual(tokens["earmark_effort"], "high")

    def test_percent_of(self):
        self.assertEqual(sidebar.percent_of(9_400, 100_000), 9)
        self.assertEqual(sidebar.percent_of(32390, 475000), 7)
        for bad in ((1, 0), ("x", 5), (None, 5), (-1, 5), (float("nan"), 5)):
            self.assertIsNone(sidebar.percent_of(*bad), bad)


class SendTests(unittest.TestCase):
    def test_whole_sets_only_when_something_changed(self):  # review 9 R182
        self.assertEqual(sidebar.changed({"a": "1", "b": None}, None), {"a": "1"})  # nothing shown yet: no clears
        self.assertEqual(sidebar.changed({"a": "1", "b": None}, {"a": "1", "b": None}), {})
        self.assertEqual(sidebar.changed({"a": "2", "b": None}, {"a": "1", "b": None}), {"a": "2", "b": None})
        self.assertEqual(sidebar.changed({"a": "1", "b": None}, {}), {"a": "1", "b": None})  # not known: whole


class SettingsTests(unittest.TestCase):
    def test_sidebar_values_checked(self):
        good = config.sidebar_settings({"counts": ["done", "note"], "counts_line": "new", "agent_row": ["context"],
                                        "context_levels": [50, 90], "write_herdr_config": True})
        self.assertEqual(good, {"counts": ["done", "note"], "counts_line": "new", "agent_row": ["context"],
                                "context_levels": [50, 90], "write_herdr_config": True})
        for key, bad in (("counts", ["done", "done"]), ("counts", ["nope"]), ("counts", "done"),
                         ("counts_line", "below"), ("agent_row", ["model", "price"]),
                         ("context_levels", [90, 70]), ("context_levels", [70, 70]), ("context_levels", [0]),
                         ("context_levels", [101]), ("context_levels", [10, 20, 30, 40, 50]),
                         ("context_levels", [True]), ("write_herdr_config", "yes")):
            self.assertEqual(config.sidebar_settings({key: bad})[key], config.SIDEBAR_DEFAULTS[key], (key, bad))
            self.assertTrue(config.sidebar_problems({key: bad}), (key, bad))
        self.assertEqual(config.sidebar_settings({"counts": []})["counts"], [])

    def test_colour_specs(self):
        self.assertEqual(config.color_spec("theme:red bold"), ("theme:red", True, False))
        self.assertEqual(config.color_spec("dim"), (None, False, True))
        self.assertEqual(config.color_spec("bold #abc"), ("#abc", True, False))
        for bad in ("red", "#ab", "#abcd", "theme:", "theme:Red", "bold bold", "#abc #def", "", "   ", 5, None,
                    "theme:red italic"):
            self.assertIsNone(config.color_spec(bad), bad)

    def test_context_colours_match_the_levels(self):
        cfg = config.color_settings({"context": ["#111111", "#222222"]})
        self.assertEqual(cfg["context"], ["#111111", "#222222"])
        self.assertEqual(config.fit_context_colors(["#111111", "#222222"], 4),
                         ["#111111", "#222222", "#222222", "#222222"])
        self.assertEqual(config.fit_context_colors(["a", "b", "c"], 2), ["a", "b"])
        self.assertTrue(config.context_mismatch({"colors": {"context": ["#111111"]}}))
        self.assertIsNone(config.context_mismatch({}))
        self.assertEqual(config.color_settings({"context": ["x"]})["context"], config.COLOR_DEFAULTS["context"])

    def test_the_simple_parser_reads_number_lists(self):
        data = config.parse_simple_toml('[sidebar]\ncontext_levels = [70, 85,\n 95]\ncounts = ["done"]\n')
        self.assertEqual(data, {"sidebar": {"context_levels": [70, 85, 95], "counts": ["done"]}})


class LoadTests(StateDir):
    def setUp(self):
        super().setUp()
        self.path = config.config_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))

    def settings(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def test_a_retired_setting_is_never_a_problem(self):
        self.settings("report_count = false\n")
        self.assertNotIn("_broken", config.load())
        self.assertIsNone(config.check())
        self.assertEqual([k for k, _ in config.retired()], ["report_count"])

    def test_levels_and_colours_together(self):
        self.settings('[sidebar]\ncontext_levels = [50]\n[colors]\ncontext = ["#111111", "#222222", "#333333"]\n')
        cfg = config.load()
        self.assertEqual(cfg["colors"]["context"], ["#111111", "#222222"])  # one more than the levels
        self.assertNotIn("_broken", cfg)


class PendingReportTests(StateDir):
    def setUp(self):
        super().setUp()
        self.index = {"sessions": {"default": {"panes": {}, "boot": 5}}}
        self.archive = {"entries": {f"claude:{n}": {"herdr_session": "default", "workspace_label": "Work",
                                                    "agent": "claude", "session_id": n} for n in "abc"}}
        self.cache = {"sessions": {}}

    def reports(self, s, cfg=None):
        return [(w, t) for w, t, _ in core.pending_reports(self.index, self.archive, "default", s, cfg,
                                                            self.cache)]

    def test_counts_per_workspace_with_suspended_tabs(self):
        self.index["sessions"]["default"]["suspended"] = {"w1:p7": {}, "w2:p1": {}}
        s = snap([pane("w1:p1", status="working"), pane("w2:p1", session=None, ws="w2")],
                 {"w1": "Work", "w2": "Other"})
        got = dict(self.reports(s))
        self.assertEqual(got["w1"], {"earmark_working": "1", "earmark_suspended": "1", "earmark_archived": "3"})
        self.assertEqual(got["w2"], {"earmark_suspended": "1"})

    def test_a_new_boot_sends_again_and_gone_workspaces_are_forgotten(self):
        s = snap([], {"w1": "Work"})
        self.assertTrue(self.reports(s))
        self.assertEqual(self.reports(s), [])
        self.index["sessions"]["default"]["boot"] = 9
        self.assertEqual(self.reports(s), [("w1", {"earmark_archived": "3"})])
        self.assertEqual(self.reports(snap([], {"w2": "Other"})), [])
        self.assertEqual(list(self.cache["sessions"]["default"]["spaces"]), ["w2"])

    def test_counts_that_no_longer_fit_are_cleared(self):
        cfg = dict(config.DEFAULTS, sidebar=dict(config.SIDEBAR_DEFAULTS), colors=config.COLOR_DEFAULTS)
        s = snap([pane("w1:p1", status="blocked")], {"w1": "Work"})
        self.assertEqual(self.reports(s, cfg), [("w1", {"earmark_blocked": "1", "earmark_archived": "3"})])
        long = snap([pane("w1:p1", status="blocked")], {"w1": "A workspace name this long"})
        self.assertEqual(self.reports(long, cfg), [("w1", dict.fromkeys(["earmark_" + i for i in config.COUNT_ITEMS]))])

    def test_after_a_popup_change_only_the_new_count_is_sent(self):
        # The popup calls update_counts after a reopen or a forget: it sends
        # what changed, and nothing (no send, no index.json write) otherwise.
        store.save_index(self.index)
        store.save_archive(self.archive)

        def sent(send):
            return [(w, t) for w, t, _ in send.call_args.args[0]]
        with mock.patch.object(herdr, "snapshot", return_value=snap([], {"w1": "Work"})), \
                mock.patch.object(core, "send_reports") as send:
            core.update_counts("default")
            self.assertEqual(sent(send), [("w1", {"earmark_archived": "3"})])
            archive = store.load_archive()
            del archive["entries"]["claude:a"]
            store.save_archive(archive)
            with mock.patch.object(store, "save_index", wraps=store.save_index) as save:
                core.update_counts("default")
                got = dict(sent(send))["w1"]
                self.assertEqual(got["earmark_archived"], "2")
                self.assertEqual(set(got), {"earmark_" + i for i in config.COUNT_ITEMS})  # the whole set
                core.update_counts("default")
                self.assertEqual(sent(send), [])
            save.assert_not_called()

    def test_the_hook_keeps_the_cache_out_of_the_index(self):
        from earmark import agents, suspend
        facts = {"known": True, "exists": True, "has_content": True, "title": "", "last_active": None}
        with mock.patch.object(herdr, "snapshot", return_value=snap([pane("w1:p1", status="idle")])), \
                mock.patch.object(core, "send_reports") as send, \
                mock.patch.object(agents, "session_facts", return_value=facts), \
                mock.patch.object(herdr, "process_info", return_value={}), \
                mock.patch.object(suspend, "spawn_worker", return_value=True):
            core.handle_event("pane.agent_status_changed", {"data": {"pane_id": "w1:p1"}}, env={})
        self.assertEqual([(w, t) for w, t, _ in send.call_args.args[0]], [("w1", {"earmark_done": "1"})])
        self.assertIn("w1", store.load_sidebar()["sessions"]["default"]["spaces"])
        self.assertNotIn("reported", store.load_index()["sessions"]["default"])


if __name__ == "__main__":
    unittest.main()
