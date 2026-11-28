"""Claude Code's status line through Earmark: the user's own command first,
Earmark's part after it.

Claude Code runs `earmark statusline [-- command...]` on every status line
refresh. The user's own command gets Claude's input, and its output and exit
code go back to Claude before Earmark does anything. Earmark's part (this
agent's line in Herdr's sidebar, earmark/agentrow.py) then runs in a process
of its own that holds none of Claude's pipes, so a slow Herdr, a held lock or
a bug in Earmark can't hold up, empty or change the status line. Nothing of
Earmark's beyond this file is loaded before the output is out.
"""
import os
import subprocess
import sys


def run(argv, stdin=None, stdout=None, env=None, apart=True):
    """Returns the exit code for Claude. `apart=False` (tests) runs
    Earmark's part in this process, after the output is written."""
    env = os.environ if env is None else env
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    data = stdin.read()
    command = argv[argv.index("--") + 1:] if "--" in argv else argv
    code = own(command, data, stdout) if command else 0
    stdout.flush()
    if not env.get("HERDR_PANE_ID"):  # a Claude outside Herdr: nothing for Earmark to do
        return code
    if apart:
        _apart(lambda: earmark_part(data, env))
    else:
        earmark_part(data, env)
    return code


def own(command, data, stdout):
    """The user's status line: Claude's input in, its output out, its exit
    code (a signal N as the shell's 128+N)."""
    try:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    except OSError as e:
        print(f"earmark statusline: {command[0]}: {e}", file=sys.stderr)
        return 127
    out, _ = child.communicate(data)
    stdout.write(out)
    return 128 - child.returncode if child.returncode < 0 else child.returncode


def earmark_part(data, env):
    try:
        from earmark import agentrow
        agentrow.from_statusline(data, env)
    except Exception as e:  # never the status line's problem
        print(f"earmark statusline: {e!r}", file=sys.stderr)


def _apart(job):
    """Run `job` in a child process with no hold on Claude's pipes (they go
    to /dev/null), in a session of its own, so this process can exit now."""
    try:
        pid = os.fork()
    except OSError:
        return  # Earmark's part waits for the next refresh
    if pid:
        return
    try:
        os.setsid()
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)
        job()
    finally:
        os._exit(0)
