"""1.2, PLAN M6 and M7: Earmark's rows in Herdr's config.toml
(earmark/herdrconf.py): the block, the guarded writer, theme colours."""
import json
import os
import stat
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import config, herdrconf  # noqa: E402
from test_review1 import StateDir  # noqa: E402

CFG = dict(config.DEFAULTS, sidebar=dict(config.SIDEBAR_DEFAULTS), colors=dict(config.COLOR_DEFAULTS))
PALETTE = {"red": "#f25e86", "yellow": "#f2c063", "green": "#b2d977", "blue": "#78dce8", "magenta": "#aba0f2",
           "accent": "#78dce8", "foreground": "#f0f2f5", "dark_foreground": "#b3bdcc"}

# A stand-in for `herdr`: `config check` reports the lines in $FAKE_ISSUES
# (plus "new problem" when the config holds BREAK), `session list --json` one
# running session, `server reload-config` fine; every call is logged.
FAKE_HERDR = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
if args[:2] == ["config", "check"]:
    edit = os.environ.get("FAKE_EDIT_AT_CHECK")  # someone saves the file during check number N
    if edit:
        n_file = os.environ["FAKE_LOG"] + ".checks"
        n = int(open(n_file).read()) + 1 if os.path.exists(n_file) else 1
        open(n_file, "w").write(str(n))
        if n == int(edit):
            with open(os.environ["HERDR_CONFIG_PATH"], "a") as f:
                f.write('[theme]\nname = "edited meanwhile"\n')
    issues = [l for l in os.environ.get("FAKE_ISSUES", "").split("|") if l]
    text = open(os.environ["HERDR_CONFIG_PATH"]).read() if os.path.exists(os.environ["HERDR_CONFIG_PATH"]) else ""
    if "BREAK" in text:
        issues.append("new problem")
    print("config: issues found" if issues else "config: ok")
    for l in issues:
        print(l)
    sys.exit(1 if issues else 0)
if args[:3] == ["session", "list", "--json"]:
    print(json.dumps({"sessions": [{"default": True, "name": "default", "running": True},
                                   {"default": False, "name": "two", "running": True},
                                   {"default": False, "name": "off", "running": False}]}))
'''


def cfg(**sidebar):
    return dict(CFG, sidebar=dict(CFG["sidebar"], **sidebar))


def herdr_upsert(content, section, key, value):
    """Herdr 0.9.5's own settings writer (src/config/io.rs upsert_section_raw),
    line for line: a new key goes right before the next table header."""
    header, assignment = f"[{section}]", f"{key} = {value}"
    lines, result, i, found, inserted = content.split("\n"), [], 0, False, False
    if lines and lines[-1] == "":
        lines.pop()
    while i < len(lines):
        line = lines[i]
        if line.strip() == header:
            found = True
            result.append(line)
            i += 1
            while i < len(lines):
                cur = lines[i].strip()
                if cur.startswith("[") and cur.endswith("]"):
                    if not inserted:
                        result.append(assignment)
                        inserted = True
                    break
                if cur.startswith(f"{key} ") or cur.startswith(f"{key}="):
                    result.append(assignment)
                    inserted = True
                else:
                    result.append(lines[i])
                i += 1
            continue
        result.append(line)
        i += 1
    if not found:
        if result and result[-1].strip():
            result.append("")
        result += [header, assignment]
    elif not inserted:
        result.append(assignment)
    return "\n".join(result) + "\n"


class BlockTests(unittest.TestCase):
    def test_colours_resolve_from_the_theme_then_fixed_defaults(self):
        self.assertEqual(herdrconf.resolve("theme:red bold", PALETTE), ("#f25e86", True, False))
        self.assertEqual(herdrconf.resolve("theme:orange", PALETTE), (herdrconf.FALLBACK["orange"], False, False))
        self.assertEqual(herdrconf.resolve("theme:nosuch", {}), (None, False, False))
        self.assertEqual(herdrconf.resolve("#123456 dim", PALETTE), ("#123456", False, True))

    def test_counts_on_the_names_line_or_their_own(self):
        same = herdrconf.block(CFG, PALETTE)
        self.assertIn('["state_icon", "workspace", { token = "$earmark_blocked", fg = "#f25e86", bold = true', same)
        self.assertIn('{ token = "$earmark_archived", dim = true }', same)
        new = herdrconf.block(cfg(counts_line="new"), PALETTE)
        self.assertIn('  ["state_icon", "workspace"],\n  [{ token = "$earmark_blocked"', new)

    def test_agent_rows_one_colour_per_level(self):
        text = herdrconf.block(cfg(context_levels=[50]), PALETTE)
        self.assertIn("$earmark_ctx_2", text)
        self.assertNotIn("$earmark_ctx_3", text)
        for agent in ("claude", "codex", "grok"):
            self.assertIn(f'{agent} = [["state_icon", "machine", "workspace", "tab"], [{{ token = "$earmark_model"', text)
        self.assertIn('{ token = "$earmark_effort", fg = "#b3bdcc", dim = false }', text)

    def test_what_isnt_shown_isnt_written(self):
        self.assertNotIn("ui.sidebar.spaces", herdrconf.block(cfg(counts=[]), PALETTE))
        self.assertNotIn("rows_by_agent", herdrconf.block(cfg(agent_row=[]), PALETTE))
        self.assertEqual(herdrconf.block(cfg(counts=[], agent_row=[]), PALETTE), "")

    @unittest.skipUnless(config.tomllib, "tomllib")
    def test_the_block_is_toml(self):
        data = config.tomllib.loads(herdrconf.block(CFG, PALETTE))
        self.assertEqual(len(data["ui"]["sidebar"]["spaces"]["rows"]), 2)
        self.assertEqual(sorted(data["ui"]["sidebar"]["agents"]["rows_by_agent"]), ["claude", "codex", "grok"])


class ComposeTests(unittest.TestCase):
    def test_append_replace_remove(self):
        b1, b2 = herdrconf.block(CFG, PALETTE), herdrconf.block(cfg(counts_line="new"), PALETTE)
        self.assertEqual(herdrconf.compose("", b1), b1)
        self.assertEqual(herdrconf.compose("a = 1", b1), "a = 1\n\n" + b1)
        self.assertEqual(herdrconf.compose("a = 1\n", b1), "a = 1\n\n" + b1)
        with_block = "[keys]\nx = 1\n\n" + b1 + "[ui]\ny = 2\n"
        self.assertEqual(herdrconf.compose(with_block, b2), "[keys]\nx = 1\n\n" + b2 + "[ui]\ny = 2\n")
        self.assertEqual(herdrconf.compose(with_block, ""), "[keys]\nx = 1\n\n[ui]\ny = 2\n")
        self.assertEqual(herdrconf.compose("a = 1\n", ""), "a = 1\n")

    def test_broken_markers_are_refused(self):
        b = herdrconf.block(CFG, PALETTE)
        for text in (b + b, herdrconf.BEGIN + "\n", herdrconf.END + "\n" + herdrconf.BEGIN + "\n"):
            with self.assertRaises(ValueError):
                herdrconf.split(text)

    def test_the_users_own_rows_tables(self):
        own = herdrconf.conflicts
        self.assertEqual(own("[ui.sidebar.spaces]\nrow_gap = 1\n"), ["ui.sidebar.spaces"])
        self.assertEqual(own("[ ui.sidebar.agents.rows_by_agent ]\n"), ["ui.sidebar.agents.rows_by_agent"])
        self.assertEqual(own("[ui.sidebar.agents]\nrow_gap = 1\n" + herdrconf.block(CFG, PALETTE)), [])

    def test_their_own_agent_rows_in_any_spelling(self):  # review 9 R176: rows_by_agent would override them
        own = herdrconf.conflicts
        self.assertEqual(own('[ui.sidebar.agents]\nrows = [\n  ["state_icon", "tab"],\n  ["terminal_title"]\n]\n'),
                         ["ui.sidebar.agents.rows"])
        self.assertEqual(own('[ui]\nsidebar.agents.rows = [["tab"]]\n'), ["ui.sidebar.agents.rows"])
        self.assertEqual(own('[ui.sidebar]\n"spaces".rows = [["workspace"]]\n'), ["ui.sidebar.spaces"])
        self.assertEqual(own('ui.sidebar.agents.rows_by_agent.claude = [["tab"]]\n'), ["ui.sidebar.agents.rows_by_agent"])
        # keys after an array of tables are its own; a line inside a value is no table or key
        self.assertEqual(own('[ui.sidebar.agents]\nrow_gap = 1\n[[keys.command]]\nrows = 1\n'), [])
        self.assertEqual(own('[keys]\nx = [\n  ["ui.sidebar.agents"]\n]\nrows = 1\n'), [])
        self.assertEqual(own('[ui.sidebar.agents]\nrow_gap = [\n  { token = "x", rows = 1 },\n]\n'), [])


class HerdrConfigFile(StateDir):
    """Herdr's config.toml in a temp folder and a fake `herdr` (no tests here:
    test_review10 builds on it)."""

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.dir.name, "herdr", "config.toml")
        os.makedirs(os.path.dirname(self.path))
        binary = os.path.join(self.dir.name, "herdr-bin")
        with open(binary, "w") as f:
            f.write(FAKE_HERDR)
        os.chmod(binary, stat.S_IRWXU)
        self.log = os.path.join(self.dir.name, "log")
        p = mock.patch.dict(os.environ, {"HERDR_BIN_PATH": binary, "HERDR_CONFIG_PATH": self.path,
                                         "FAKE_LOG": self.log, "FAKE_ISSUES": ""})
        p.start()
        self.addCleanup(p.stop)

    def write(self, text, mode=0o644):
        with open(self.path, "w") as f:
            f.write(text)
        os.chmod(self.path, mode)

    def text(self):
        with open(self.path) as f:
            return f.read()

    def calls(self):
        with open(self.log) as f:
            return [json.loads(line) for line in f]


class ApplyTests(HerdrConfigFile):
    def test_written_reloaded_backed_up_once_mode_kept(self):
        self.write("[keys]\nprefix = \"ctrl+space\"\n", 0o640)
        self.assertEqual(herdrconf.apply(CFG, PALETTE), ("written", self.path))
        self.assertTrue(self.text().startswith('[keys]\nprefix = "ctrl+space"\n\n' + herdrconf.BEGIN))
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)
        with open(self.path + herdrconf.BACKUP_SUFFIX) as f:
            self.assertEqual(f.read(), '[keys]\nprefix = "ctrl+space"\n')
        reloads = [c for c in self.calls() if c[-2:] == ["server", "reload-config"]]
        self.assertEqual(reloads, [["--session", "default", "server", "reload-config"],
                                   ["--session", "two", "server", "reload-config"]])
        self.assertEqual(herdrconf.apply(CFG, PALETTE), ("unchanged", ""))
        herdrconf.apply(cfg(counts_line="new"), PALETTE)
        with open(self.path + herdrconf.BACKUP_SUFFIX) as f:
            self.assertEqual(f.read(), '[keys]\nprefix = "ctrl+space"\n')  # the first copy stays

    def test_the_users_own_tables_are_left_alone(self):
        self.write("[ui.sidebar.spaces]\nrow_gap = 1\n")
        status, detail = herdrconf.apply(CFG, PALETTE)
        self.assertEqual(status, "refused")
        self.assertIn("ui.sidebar.spaces", detail)
        self.assertEqual(self.text(), "[ui.sidebar.spaces]\nrow_gap = 1\n")
        self.assertFalse(os.path.exists(self.log))  # not even a check

    def test_a_new_problem_rolls_back_an_old_one_doesnt(self):
        self.write("[ui]\nold = 1\n")
        with mock.patch.dict(os.environ, {"FAKE_ISSUES": "unknown config key ui.old"}):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "written")  # nothing new
        self.write("[ui]\nold = 1\n")
        with mock.patch.object(herdrconf, "block", return_value=herdrconf.BEGIN + "\n# BREAK\n" + herdrconf.END + "\n"):
            self.assertEqual(herdrconf.apply(CFG, PALETTE), ("rolled back", "new problem"))
        self.assertEqual(self.text(), "[ui]\nold = 1\n")

    def test_no_config_yet(self):
        self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "written")
        self.assertFalse(os.path.exists(self.path + herdrconf.BACKUP_SUFFIX))
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_keep_current_once_per_change_and_never_when_off(self):
        on = cfg(write_herdr_config=True)
        with mock.patch.object(herdrconf, "theme_stamp", return_value=["t", 1, 1]), \
                mock.patch.object(herdrconf, "theme_palette", return_value=PALETTE) as palette:
            self.assertEqual(herdrconf.keep_current(on)[0], "written")
            self.assertIsNone(herdrconf.keep_current(on))
            self.assertEqual(palette.call_count, 1)  # asked again only when the theme's file changes
        with mock.patch.object(herdrconf, "theme_stamp", return_value=["t", 2, 2]), \
                mock.patch.object(herdrconf, "theme_palette", return_value=dict(PALETTE, red="#ff0000")):
            self.assertEqual(herdrconf.keep_current(on)[0], "written")
        self.assertIn("#ff0000", self.text())
        text = self.text()
        self.assertEqual(herdrconf.keep_current(cfg(write_herdr_config=False, counts_line="new"))[0], "off")
        self.assertEqual(herdrconf.keep_current(dict(cfg(write_herdr_config=True, counts_line="new"), _broken="x"))[0],
                         "refused")
        self.assertEqual(self.text(), text)

    def test_the_theme_hook_follows_the_setting(self):  # review 9 R183
        text = "[keys]\n"
        self.write(text)
        with mock.patch.object(herdrconf, "theme_stamp", return_value=None):
            self.assertEqual(herdrconf.keep_current(cfg(write_herdr_config=False), now=True)[0], "off")
            self.assertEqual(herdrconf.keep_current(dict(cfg(write_herdr_config=True), _broken="x"), now=True)[0],
                             "refused")
            self.assertEqual(self.text(), text)
            on = cfg(write_herdr_config=True)
            self.assertEqual(herdrconf.keep_current(on)[0], "written")
            self.write(text)  # the block removed by hand (or by chezmoi apply): the next hook puts it back
            self.assertEqual(herdrconf.keep_current(on)[0], "written")  # review 10 R203
            self.assertIsNone(herdrconf.keep_current(on))  # and then nothing, the file untouched since
            self.assertEqual(herdrconf.keep_current(on, now=True)[0], "unchanged")
            from earmark import store
            with store.try_lock("herdrconf"):
                self.assertEqual(herdrconf.keep_current(on, now=True)[0], "busy")

    def test_nothing_rewritten_when_nothing_changed(self):  # review 9 R185
        from earmark import store
        on = cfg(write_herdr_config=True)
        with mock.patch.object(herdrconf, "theme_stamp", return_value=None):
            herdrconf.keep_current(on)
            with mock.patch.object(store, "save_json", wraps=store.save_json) as save:
                self.assertIsNone(herdrconf.keep_current(on))
                save.assert_not_called()

    def test_a_setting_herdr_put_inside_the_block_is_kept(self):  # review 9 R169
        self.write('[ui]\nsidebar_width = 30\n')
        self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "written")
        self.write(herdr_upsert(self.text(), "ui", "status_indicators", '"dots"'))  # Herdr's settings screen
        self.assertGreater(self.text().index("status_indicators"), self.text().index(herdrconf.BEGIN))  # inside
        self.assertEqual(herdrconf.apply(cfg(counts_line="new"), PALETTE)[0], "written")
        text = self.text()
        self.assertEqual(text.count('status_indicators = "dots"'), 1)
        self.assertLess(text.index("status_indicators"), text.index(herdrconf.BEGIN))  # back in [ui], above
        self.assertIn('status_indicators = "dots"', herdrconf.compose(text, ""))  # and when the block goes

    def test_a_symlinked_config_stays_a_link(self):  # review 9 R170
        real = os.path.join(self.dir.name, "dotfiles", "config.toml")
        os.makedirs(os.path.dirname(real))
        with open(real, "w") as f:
            f.write('[keys]\nprefix = "ctrl+b"\n')
        os.symlink(real, self.path)
        self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "written")
        self.assertTrue(os.path.islink(self.path))
        with open(real) as f:
            self.assertIn(herdrconf.BEGIN, f.read())
        self.assertTrue(os.path.exists(self.path + herdrconf.BACKUP_SUFFIX))  # by the link, not in the dotfiles
        self.assertFalse(os.path.exists(real + herdrconf.BACKUP_SUFFIX))
        with mock.patch.object(herdrconf, "block", return_value=herdrconf.BEGIN + "\n# BREAK\n" + herdrconf.END + "\n"):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "rolled back")
        self.assertTrue(os.path.islink(self.path))

    def test_an_edit_made_while_checking_survives(self):  # review 9 R177
        self.write("[keys]\n")
        with mock.patch.dict(os.environ, {"FAKE_EDIT_AT_CHECK": "1"}):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "busy")
        self.assertEqual(self.text(), '[keys]\n[theme]\nname = "edited meanwhile"\n')
        self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "written")  # the next try
        self.assertIn("edited meanwhile", self.text())

    def test_a_rollback_keeps_an_edit_made_after_the_write(self):  # review 9 R177
        self.write("[keys]\n")
        with mock.patch.dict(os.environ, {"FAKE_EDIT_AT_CHECK": "2"}), \
                mock.patch.object(herdrconf, "block", return_value=herdrconf.BEGIN + "\n# BREAK\n" + herdrconf.END + "\n"):
            self.assertEqual(herdrconf.apply(CFG, PALETTE)[0], "rolled back")
        self.assertIn("edited meanwhile", self.text())
        self.assertNotIn("BREAK", self.text())

    def test_the_first_copy_is_never_half_written(self):  # review 9 R187
        from earmark import store
        self.write("[keys]\n")
        with mock.patch.object(store.os, "fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                herdrconf.apply(CFG, PALETTE)
        self.assertFalse(os.path.exists(self.path + herdrconf.BACKUP_SUFFIX))
        self.assertEqual(self.text(), "[keys]\n")

    def test_a_failure_waits_for_a_change(self):
        on = cfg(write_herdr_config=True)
        self.write("[ui.sidebar.spaces]\nrow_gap = 1\n")
        with mock.patch.object(herdrconf, "theme_stamp", return_value=None), \
                mock.patch.object(herdrconf, "apply", wraps=herdrconf.apply) as apply:
            self.assertEqual(herdrconf.keep_current(on)[0], "refused")
            self.assertIsNone(herdrconf.keep_current(on))
            self.assertEqual(apply.call_count, 1)
            herdrconf.keep_current(cfg(write_herdr_config=True, counts_line="new"))
            self.assertEqual(apply.call_count, 2)


class ThemeTests(StateDir):
    def setUp(self):
        super().setUp()
        self.colors = herdrconf.theme_file()
        os.makedirs(os.path.dirname(self.colors), exist_ok=True)
        self.addCleanup(lambda: os.path.exists(self.colors) and os.remove(self.colors))

    def test_without_omarchys_tool_colors_toml_is_read(self):
        with open(self.colors, "w") as f:
            f.write('mode = "dark"\nred = "#f25e86"\ngreen = "#b2d977"\nnote = "not a colour"\n')
        with mock.patch.object(herdrconf.shutil, "which", return_value=None):
            self.assertEqual(herdrconf.theme_palette(), {"red": "#f25e86", "green": "#b2d977"})
        self.assertIsNotNone(herdrconf.theme_stamp())

    def test_omarchys_tool_first(self):
        with open(self.colors, "w") as f:
            f.write('red = "#000000"\n')
        tool = os.path.join(self.dir.name, "omarchy-theme-color")
        with open(tool, "w") as f:
            f.write('#!/bin/sh\nprintf "red\\t#f25e86\\ndark_foreground\\t#b3bdcc\\nbad\\tnope\\n"\n')
        os.chmod(tool, stat.S_IRWXU)
        with mock.patch.object(herdrconf.shutil, "which", return_value=tool):
            self.assertEqual(herdrconf.theme_palette(), {"red": "#f25e86", "dark_foreground": "#b3bdcc"})

    def test_no_theme(self):
        self.assertIsNone(herdrconf.theme_stamp())
        with mock.patch.object(herdrconf.shutil, "which", return_value=None):
            self.assertEqual(herdrconf.theme_palette(), {})

    def test_the_theme_hook_script(self):  # review 9 R168: through the launcher, never the install folder
        from earmark import launcher
        home = os.path.join(self.dir.name, "home")  # its own, whatever the suite's HOME is: it writes there
        os.makedirs(home)
        p = mock.patch.dict(os.environ, {"HOME": home})
        p.start()
        self.addCleanup(p.stop)
        self.assertIsNone(herdrconf.install_theme_hook())  # no Omarchy, no hook (nor its folder)
        self.assertFalse(os.path.exists(os.path.join(home, ".config", "omarchy")))
        os.makedirs(os.path.join(home, ".config", "omarchy"))
        path = herdrconf.install_theme_hook()
        self.assertTrue(path.startswith(home))
        with open(path) as f:
            script = f.read()
        self.assertIn(f"exec {launcher.path()} rows --apply", script)
        self.assertNotIn(launcher.ROOT, script)
        self.assertTrue(os.access(path, os.X_OK) and os.access(launcher.path(), os.X_OK))
        self.assertTrue(path.endswith("theme-set.d/earmark-sidebar"))


if __name__ == "__main__":
    unittest.main()
