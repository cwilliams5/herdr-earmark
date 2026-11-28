"""Imported first by every test module: keeps the suite away from the user's
real Herdr, settings and agent data (HOME, the XDG folders and every agent
folder point into one temporary folder).

The tests run inside Herdr panes, where HERDR_SOCKET_PATH points at the
user's real server; every Herdr call goes through HERDR_BIN_PATH, so that
points at nothing. Earmark's settings and state, and the agents' folders,
point at empty temporary folders (a test that needs one sets its own).
"""
import atexit
import os
import shutil
import sys
import tempfile

import glob
import time
# Runs that were killed leave their folders: remove ours older than a day.
for stale in glob.glob(os.path.join(tempfile.gettempdir(), "earmark-tests-*")):
    try:
        if os.stat(stale).st_uid == os.getuid() and time.time() - os.stat(stale).st_mtime > 86400:
            shutil.rmtree(stale, True)
    except OSError:
        pass
# Account settings (ANTHROPIC_*, proxies, ...) in the shell running the
# tests would change what the placeholder's account check sees: none.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from earmark import agents as _agents  # noqa: E402  (side-effect free: constants and functions)
for _name in [k for k in os.environ if _agents.account_env({k: ""})]:
    del os.environ[_name]
ROOT = tempfile.mkdtemp(prefix="earmark-tests-")
atexit.register(shutil.rmtree, ROOT, True)
os.environ.pop("HERDR_SOCKET_PATH", None)
os.environ.pop("HERDR_SESSION", None)
for _name in ("HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID", "HERDR_ENV"):  # the pane running the tests
    os.environ.pop(_name, None)
os.environ["HERDR_BIN_PATH"] = "/nonexistent/herdr-blocked-in-tests"
for name in ("HERDR_PLUGIN_STATE_DIR", "HERDR_PLUGIN_CONFIG_DIR", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "GROK_HOME"):
    path = os.path.join(ROOT, name.lower())
    os.makedirs(path, exist_ok=True)
    os.environ[name] = path
# HOME too: a Claude folder of "" means ~/.claude, and the suite must never
# read the user's real one.
os.environ["HOME"] = os.path.join(ROOT, "home")
os.makedirs(os.environ["HOME"], exist_ok=True)
# Where Earmark looks when Herdr's plugin variables are unset (XDG folders):
# never the user's.
for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME"):
    os.environ[name] = os.path.join(ROOT, name.lower())
# Herdr's own config.toml (toast delivery, restore delay): never the user's.
os.environ["HERDR_CONFIG_PATH"] = os.path.join(ROOT, "herdr-config.toml")
