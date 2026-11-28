"""Earmark's launcher: a small script in Earmark's config folder that runs
Earmark from wherever Herdr installed it.

Herdr installs a GitHub plugin into a new folder at every install and update
and deletes the old one (Herdr 0.9.5: src/plugin_paths.rs,
src/plugin_installations.rs), so nothing outside Herdr may point into it.
Claude Code's status line, the /herdr-note skill and Omarchy's theme hook go
through this launcher and the copy of the skill next to it, which every hook
keeps pointing at the folder Earmark runs from. The config folder survives
updates and uninstalls (`herdr plugin config-dir io.github.cwilliams5.earmark`
prints it). When Earmark is gone, the launcher still runs a status line's own
command (the part after `--`); anything else fails with a message (a `note
write` mustn't look saved).
"""
import os
import shlex

from . import config, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "earmark"
SKILL = "herdr-note"


def path():
    return os.path.join(config.config_dir(), NAME)


def skill_dir():
    return os.path.join(config.config_dir(), "skills", SKILL)


def script(root=ROOT):
    return ("#!/bin/sh\n"
            "# Earmark's launcher, kept by Earmark (rewritten when Herdr moves Earmark).\n"
            "# Runs Earmark; when Earmark is gone, a status line still runs your own\n"
            "# command (the part after --), and anything else fails with a message.\n"
            f"root={shlex.quote(root)}\n"
            'if [ -f "$root/earmark.py" ]; then exec python3 "$root/earmark.py" "$@"; fi\n'
            'if [ "$1" = statusline ]; then\n'
            "  shift\n"
            '  if [ "$1" = -- ]; then shift; fi\n'
            '  if [ "$#" -gt 0 ]; then exec "$@"; fi\n'
            "  exit 0\n"
            "fi\n"
            'echo "earmark: Earmark is not installed at $root any more" >&2\n'
            "exit 1\n")


def _holds(file, text):
    try:
        with open(file, encoding="utf-8") as f:
            return f.read() == text
    except (OSError, UnicodeDecodeError):
        return False


def ensure(root=ROOT):
    """The launcher and the skill's copy, written where missing or out of
    date (two small reads when nothing changed). Returns the launcher's path."""
    os.makedirs(config.config_dir(), exist_ok=True)
    launcher = path()
    want = script(root)
    if not _holds(launcher, want):
        store.write_atomic(launcher, want, mode=0o755)
    try:
        with open(os.path.join(root, "skills", SKILL, "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
    except OSError:
        return launcher
    copy = os.path.join(skill_dir(), "SKILL.md")
    if not _holds(copy, skill):
        os.makedirs(skill_dir(), exist_ok=True)
        store.write_atomic(copy, skill, mode=0o644)
    return launcher
