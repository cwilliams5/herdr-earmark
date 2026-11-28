"""1.2, PLAN M4 and M5: agent rows (earmark/agentrow.py): Claude's status
line wrapper, Codex's and Grok's files, and the hooks' refit and clearing."""
import io
import json
import os
import signal
import stat
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate  # noqa: E402,F401  (first: no real Herdr, settings or agent data)

from earmark import agentrow, agents, config, herdr, sidebar, statusline, store  # noqa: E402
from test_suspend import pane, snap  # noqa: E402
from test_review1 import StateDir  # noqa: E402

CFG = dict(config.DEFAULTS, sidebar=dict(config.SIDEBAR_DEFAULTS), colors=dict(config.COLOR_DEFAULTS))
STATUS = {"session_id": "s1", "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
          "effort": {"level": "xhigh"}, "context_window": {"used_percentage": 9.4, "context_window_size": 1000000}}


class Sent:
    """Records sidebar.report calls instead of reaching Herdr."""

    def __init__(self, fail=False):
        self.calls, self.fail, self.seqs = [], fail, []

    def __call__(self, kind, target, tokens, seq):
        if self.fail:
            raise herdr.HerdrError("busy")
        self.calls.append((kind, target, dict(tokens)))
        self.seqs.append(seq)

    def shown(self, target):
        """The tokens a pane shows after all calls."""
        out = {}
        for _, t, tokens in self.calls:
            if t == target:
                for k, v in tokens.items():
                    if v:
                        out[k] = v
                    else:
                        out.pop(k, None)
        return out


class ValuesTests(unittest.TestCase):
    def test_claude_status_line(self):
        self.assertEqual(agentrow.claude_values(STATUS), {"agent": "claude", "session_id": "s1", "model": "Opus 5.5",
                                                          "effort": "xhigh", "percent": 9})
        partial = agentrow.claude_values({"model": {"id": "x"}, "context_window": {"total_input_tokens": 500,
                                                                                    "context_window_size": 1000}})
        self.assertEqual((partial["model"], partial["effort"], partial["percent"]), ("x", None, 50))
        self.assertIsNone(agentrow.claude_values([1]))
        odd = agentrow.claude_values({"model": "Opus", "effort": "high", "context_window": {"used_percentage": True}})
        self.assertEqual((odd["model"], odd["effort"], odd["percent"]), (None, None, None))


class FileValuesTests(StateDir):
    def write(self, path, records):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for r in records:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")

    def test_codex_last_turn_and_tokens_with_the_default_effort(self):
        home = os.environ["CODEX_HOME"]
        with open(os.path.join(home, "models_cache.json"), "w") as f:
            json.dump({"models": [{"slug": "gpt-6.2-sol", "display_name": "GPT-6.2-Sol",
                                   "default_reasoning_level": "low"}]}, f)
        rollout = os.path.join(self.dir.name, "rollout.jsonl")
        self.write(rollout, [
            {"type": "turn_context", "payload": {"model": "old-model", "effort": "high"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": 1000}, "model_context_window": 10000}}},
            {"type": "turn_context", "payload": {"model": "gpt-6.2-sol", "effort": None}},
            "not json",
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": 32390}, "model_context_window": 475000}}}])
        self.assertEqual(agentrow.codex_values(rollout),
                         {"agent": "codex", "model": "GPT-6.2-Sol", "effort": "low", "percent": 7})
        self.write(rollout, [{"type": "event_msg", "payload": {"type": "token_count"}}])
        self.assertIsNone(agentrow.codex_values(rollout))  # no turn yet: no row
        self.write(rollout, [  # read last first: the newest turn, then an older one before any token count
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": 1000}, "model_context_window": 10000}}},
            {"type": "turn_context", "payload": {"model": "old-model", "effort": "high"}},
            {"type": "turn_context", "payload": {"model": "gpt-6.2-sol", "effort": "medium"}}])
        self.assertEqual(agentrow.codex_values(rollout)["model"], "GPT-6.2-Sol")

    def test_grok_summary_signals_and_label(self):
        folder = os.path.join(os.environ["GROK_HOME"], "sessions", "x", "g1")
        os.makedirs(folder)
        for name, data in (("summary.json", {"current_model_id": "grok-4.7", "reasoning_effort": "high"}),
                           ("signals.json", {"contextTokensUsed": 1921, "contextWindowTokens": 256000}),
                           ("prompt_context.json", {"system_prompt_label": "Grok 4.7"})):
            with open(os.path.join(folder, name), "w") as f:
                json.dump(data, f)
        self.assertEqual(agentrow.grok_values(os.path.join(folder, "summary.json")),
                         {"agent": "grok", "model": "Grok 4.7", "effort": "high", "percent": 1})
        os.remove(os.path.join(folder, "prompt_context.json"))
        self.assertEqual(agentrow.grok_values(os.path.join(folder, "summary.json"))["model"], "grok-4.7")

    def test_files_are_read_again_only_when_they_change(self):
        source = os.path.join(self.dir.name, "rollout.jsonl")
        self.write(source, [{"type": "turn_context", "payload": {"model": "m", "effort": "high"}}])
        with mock.patch.object(agents, "session_facts", return_value={"source": source}), \
                mock.patch.object(agentrow, "codex_values", wraps=agentrow.codex_values) as read:
            first = agentrow.file_values("codex", "c1", {})
            cached = dict(first, session_id="c1")
            agentrow.file_values("codex", "c1", cached)
            self.assertEqual(read.call_count, 1)
            self.write(source, [{"type": "turn_context", "payload": {"model": "m", "effort": "low"}}, "x" * 50])
            self.assertEqual(agentrow.file_values("codex", "c1", cached)["effort"], "low")
            self.assertEqual(read.call_count, 2)

    def test_the_file_is_looked_up_once(self):  # review 9 R185: not Codex's database on every hook
        source = os.path.join(self.dir.name, "rollout.jsonl")
        self.write(source, [{"type": "turn_context", "payload": {"model": "m", "effort": "high"}}])
        with mock.patch.object(agents, "session_facts", return_value={"source": source}) as facts:
            cached = dict(agentrow.file_values("codex", "c1", {}), session_id="c1", agent="codex")
            agentrow.file_values("codex", "c1", cached)
            self.assertEqual(facts.call_count, 1)
            agentrow.file_values("codex", "c2", cached)  # another session: looked up
            self.assertEqual(facts.call_count, 2)


class UpdateTests(StateDir):
    def test_only_changes_are_sent_and_remembered(self):
        sent = Sent()
        values = agentrow.claude_values(STATUS)
        with mock.patch.object(sidebar, "report", sent):
            agentrow.update("default", "w1:p1", values, CFG, 26)
            agentrow.update("default", "w1:p1", values, CFG, 26)
            agentrow.update("default", "w1:p1", dict(values, percent=88), CFG, 26)
        self.assertEqual(len(sent.calls), 2)
        self.assertEqual(sent.calls[0][2], {"earmark_model": "Opus 5.5", "earmark_effort": "xhigh", "earmark_ctx_1": "9%"})
        # a change sends the whole set (review 9 R182: Herdr keeps only the newest report per source)
        self.assertEqual(sent.calls[1][2], sidebar.agent_tokens("Opus 5.5", "xhigh", 88, CFG["sidebar"], 26))
        self.assertEqual(sent.shown("w1:p1"), {"earmark_model": "Opus 5.5", "earmark_effort": "xh", "earmark_ctx_3": "88%"})
        self.assertLess(sent.seqs[0], sent.seqs[1])  # each report newer than the last

    def test_a_stuck_lock_is_given_up_on(self):  # review 9 R174
        values = agentrow.claude_values(STATUS)
        with mock.patch.object(agentrow, "LOCK_WAIT", 0.2), \
                store.flock(os.path.join(agentrow.rows_dir("default"), ".lock")):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                agentrow.update("default", "w1:p1", values, CFG, 26)
            self.assertLess(time.monotonic() - started, 2)

    def test_a_failed_send_is_tried_again(self):
        values = agentrow.claude_values(STATUS)
        with mock.patch.object(sidebar, "report", Sent(fail=True)):
            with self.assertRaises(herdr.HerdrError):
                agentrow.update("default", "w1:p1", values, CFG, 26)
        sent = Sent()
        with mock.patch.object(sidebar, "report", sent):
            agentrow.update("default", "w1:p1", values, CFG, 26)
        self.assertEqual(sent.shown("w1:p1")["earmark_ctx_1"], "9%")

    def test_a_restart_sends_everything_again(self):
        sent = Sent()
        values = agentrow.claude_values(STATUS)
        with mock.patch.object(sidebar, "report", sent):
            agentrow.update("default", "w1:p1", values, CFG, 26)
            agentrow.update("default", "w1:p1", values, CFG, 26, fresh=True)
        self.assertEqual(sent.calls[1][2], sent.calls[0][2])


class RefreshTests(StateDir):
    def setUp(self):
        super().setUp()
        self.sent = Sent()
        p = mock.patch.object(sidebar, "report", self.sent)
        p.start()
        self.addCleanup(p.stop)
        agentrow.update("default", "w1:p1", agentrow.claude_values(STATUS), CFG, 26)
        self.sent.calls.clear()

    def test_a_narrower_sidebar_refits(self):
        live = snap([pane("w1:p1")])
        agentrow.refresh("default", live, CFG, boot=1)  # first boot seen: sent again
        self.sent.calls.clear()
        agentrow.refresh("default", live, CFG, boot=1)
        self.assertEqual(self.sent.calls, [])
        with mock.patch.object(sidebar, "sidebar_width", return_value=20):
            agentrow.refresh("default", live, CFG, boot=1)
        self.assertEqual(self.sent.shown("w1:p1")["earmark_model"], "O5.5")

    def test_after_a_restart_everything_is_sent_again(self):
        live = snap([pane("w1:p1")])
        agentrow.refresh("default", live, CFG, boot=1)
        self.sent.calls.clear()
        agentrow.refresh("default", live, CFG, boot=2)
        self.assertEqual(self.sent.calls[0][2]["earmark_ctx_1"], "9%")

    def test_an_agent_that_left_is_cleared(self):
        agentrow.refresh("default", snap([pane("w1:p1", session=None)]), CFG, boot=1)
        self.assertEqual(self.sent.shown("w1:p1"), {})
        self.assertEqual(agentrow.cached_panes("default"), {})

    def test_another_session_in_the_pane_is_cleared(self):
        agentrow.refresh("default", snap([pane("w1:p1", session="s2")]), CFG, boot=1)
        self.assertEqual(self.sent.shown("w1:p1"), {})

    def test_a_closed_pane_is_forgotten_without_a_call(self):
        agentrow.refresh("default", snap([]), CFG, boot=1)
        self.assertEqual(self.sent.calls, [])
        self.assertEqual(agentrow.cached_panes("default"), {})

    def test_codex_rows_come_from_its_files(self):
        values = {"agent": "codex", "model": "GPT-6.2-Sol", "effort": "low", "percent": 4, "stamp": []}
        with mock.patch.object(agentrow, "file_values", return_value=values):
            agentrow.refresh("default", snap([pane("w1:p2", session="c1", agent="codex")]), CFG, boot=1)
        self.assertEqual(self.sent.shown("w1:p2"), {"earmark_model": "GPT-6.2-Sol", "earmark_effort": "l",
                                                    "earmark_ctx_1": "4%"})  # 22 columns in full: effort shortened

    def test_a_refit_never_puts_back_older_values(self):  # review 9 R175
        stale = agentrow.cached_panes("default")  # what a hook read before its loop
        newer = dict(agentrow.claude_values(STATUS), model="Sonnet 5", percent=41)
        agentrow.update("default", "w1:p1", newer, CFG, 26)  # the status line, meanwhile
        with mock.patch.object(agentrow, "cached_panes", return_value=stale):
            agentrow.refresh("default", snap([pane("w1:p1")]), CFG, boot=1)
        rec = agentrow.load("default", "w1:p1")
        self.assertEqual((rec["model"], rec["percent"]), ("Sonnet 5", 41))
        self.assertEqual(self.sent.shown("w1:p1")["earmark_model"], "Sonnet 5")

    def test_the_boot_mark_is_written_only_after_a_restart(self):  # review 9 R185
        live = snap([pane("w1:p1")])
        agentrow.refresh("default", live, CFG, boot=1)
        with mock.patch.object(store, "write_atomic", wraps=store.write_atomic) as write:
            agentrow.refresh("default", live, CFG, boot=1)
        self.assertNotIn(".boot", " ".join(str(c.args[0]) for c in write.call_args_list))

    def test_grok_rows_through_the_hooks(self):  # review 9 R193: the whole Grok path, files to tokens
        folder = os.path.join(os.environ["GROK_HOME"], "sessions", "x", "g9")
        os.makedirs(folder)
        self.addCleanup(__import__("shutil").rmtree, folder, True)

        def put(name, data):
            with open(os.path.join(folder, name), "w") as f:
                json.dump(data, f)
        put("summary.json", {"current_model_id": "grok-4.7", "reasoning_effort": "high", "session_summary": "t",
                             "last_active_at": "2026-11-27T10:00:00.000000000Z", "num_messages": 2})
        put("signals.json", {"contextTokensUsed": 2560, "contextWindowTokens": 256000})
        live = snap([pane("w1:p3", session="g9", agent="grok")])
        agentrow.refresh("default", live, CFG, boot=1)
        self.assertEqual(self.sent.shown("w1:p3"), {"earmark_model": "grok-4.7", "earmark_effort": "high",
                                                    "earmark_ctx_1": "1%"})
        put("signals.json", {"contextTokensUsed": 192000, "contextWindowTokens": 256000})
        os.utime(os.path.join(folder, "signals.json"), (time.time() + 5, time.time() + 5))
        agentrow.refresh("default", live, CFG, boot=1)
        self.assertEqual(self.sent.shown("w1:p3")["earmark_ctx_2"], "75%")

    def test_turning_agent_rows_off_clears_them(self):  # review 10 R208
        cfg = dict(CFG, sidebar=dict(CFG["sidebar"], agent_row=[]))
        agentrow.refresh("default", snap([pane("w1:p1")]), cfg, boot=5)
        self.assertEqual(self.sent.shown("w1:p1"), {})
        self.assertEqual(agentrow.cached_panes("default"), {})
        self.sent.calls.clear()
        agentrow.refresh("default", snap([pane("w1:p1")]), cfg, boot=5)
        self.assertEqual(self.sent.calls, [])  # nothing more once cleared


class StatuslineTests(StateDir):
    def run_line(self, argv, payload=STATUS, env=None):
        out = io.BytesIO()
        env = {"HERDR_PANE_ID": "w1:p1"} if env is None else env
        sent = Sent()
        with mock.patch.object(sidebar, "report", sent), \
                mock.patch.object(herdr, "pane", return_value={"agent_session": {"value": "s1"}}):
            code = statusline.run(argv, stdin=io.BytesIO(json.dumps(payload).encode()), stdout=out, env=env,
                                  apart=False)
        return code, out.getvalue(), sent

    def test_the_users_command_gets_the_input_and_its_output_passes_through(self):
        code, out, sent = self.run_line(["--", sys.executable, "-c",
                                         "import sys,json; print('model:', json.load(sys.stdin)['model']['id'])"])
        self.assertEqual((code, out), (0, b"model: claude-opus-5-5\n"))
        self.assertEqual(sent.shown("w1:p1")["earmark_ctx_1"], "9%")

    def test_its_exit_code_passes_through(self):
        code, out, _ = self.run_line(["--", sys.executable, "-c", "import sys; sys.stdin.read(); print('x'); sys.exit(3)"])
        self.assertEqual((code, out), (3, b"x\n"))
        code, _, _ = self.run_line(["--", sys.executable, "-c", "import os,signal; os.kill(os.getpid(), signal.SIGTERM)"])
        self.assertEqual(code, 128 + signal.SIGTERM)  # review 9 R186: as the shell says it

    def test_earmark_failing_never_touches_the_status_line(self):
        with mock.patch.object(agentrow, "update", side_effect=RuntimeError("boom")):
            code, out, _ = self.run_line(["--", sys.executable, "-c", "import sys; sys.stdin.read(); print('ok')"])
        self.assertEqual((code, out), (0, b"ok\n"))
        code, out, _ = self.run_line(["--", sys.executable, "-c", "import sys; sys.stdin.read(); print('ok')"],
                                     payload="not a status")
        self.assertEqual((code, out), (0, b"ok\n"))

    def test_the_output_is_out_before_earmark_starts(self):  # review 9 R174
        seen = []
        out = io.BytesIO()
        with mock.patch.object(statusline, "earmark_part", side_effect=lambda d, e: seen.append(out.getvalue())):
            statusline.run(["--", sys.executable, "-c", "import sys; sys.stdin.read(); print('mine')"],
                           stdin=io.BytesIO(b"{}"), stdout=out, env={"HERDR_PANE_ID": "w1:p1"}, apart=False)
        self.assertEqual(seen, [b"mine\n"])

    def test_a_slow_herdr_never_holds_up_the_status_line(self):  # review 9 R174, the real command
        fake = os.path.join(self.dir.name, "slow-herdr")
        mark = os.path.join(self.dir.name, "reported")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\n"
                    "if [ \"$1 $2\" = \"pane get\" ]; then echo '{\"result\":{\"pane\":{\"agent_session\":{\"value\":\"s1\"}}}}'; exit 0; fi\n"
                    f"sleep 2\necho \"$@\" > {mark}\necho '{{}}'\n")
        os.chmod(fake, stat.S_IRWXU)
        env = dict(os.environ, HERDR_PANE_ID="w1:p1", HERDR_BIN_PATH=fake)
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "earmark.py")
        started = time.monotonic()
        done = subprocess.run([sys.executable, script, "statusline", "--", sys.executable, "-c",
                               "import sys; sys.stdin.read(); print('mine')"],
                              input=json.dumps(STATUS).encode(), capture_output=True, env=env, timeout=10)
        self.assertEqual((done.returncode, done.stdout), (0, b"mine\n"))
        self.assertLess(time.monotonic() - started, 1.5)
        deadline = time.monotonic() + 8  # Earmark's part still ran, apart (time.sleep is mocked here)
        while not os.path.exists(mark) and time.monotonic() < deadline:
            __import__("select").select([], [], [], 0.05)
        with open(mark) as f:
            self.assertIn("report-metadata w1:p1", f.read())

    def test_outside_herdr_nothing_is_sent(self):
        _, _, sent = self.run_line(["--", sys.executable, "-c", "import sys; sys.stdin.read()"], env={})
        self.assertEqual(sent.calls, [])

    def test_the_session_names_the_rows(self):  # review 9 R193
        self.run_line([], env={"HERDR_PANE_ID": "w1:p1", "HERDR_SESSION": "two"})
        self.assertEqual(agentrow.load("two", "w1:p1")["percent"], 9)
        self.assertEqual(agentrow.load("default", "w1:p1"), {})

    def test_a_big_input_doesnt_block(self):
        payload = dict(STATUS, padding="x" * 300000)
        code, out, _ = self.run_line(["--", sys.executable, "-c", "import sys; print(len(sys.stdin.read()) > 300000)"],
                                     payload=payload)
        self.assertEqual((code, out), (0, b"True\n"))

    def test_without_a_command(self):
        code, out, sent = self.run_line([])
        self.assertEqual((code, out), (0, b""))
        self.assertTrue(sent.calls)
        code, _, _ = self.run_line(["--", "/nonexistent/command"])
        self.assertEqual(code, 127)


if __name__ == "__main__":
    unittest.main()
