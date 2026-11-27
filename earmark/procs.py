"""What Earmark needs to know about processes to suspend an agent safely:
what runs under it, when it started (so a reused pid is never mistaken for
it), one variable of its environment (CLAUDE_CONFIG_DIR), its memory, and
how much memory the machine has left.

Linux reads /proc. Elsewhere (macOS) `ps` gives less: no memory-pressure
mode, and the environment only where `ps eww` shows it.
"""
import os
import re
import subprocess
import time

# A shell under an agent means work in progress: Claude Code runs every Bash
# tool call and Monitor through one (`bash -c source .../shell-snapshots/...`),
# Codex its commands. MCP servers are started directly and don't count.
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "mksh", "tcsh", "csh", "nu", "xonsh", "elvish", "busybox"}


def linux():
    return os.path.isdir("/proc/self")


def _ps(*fields):
    try:
        out = subprocess.run(["ps", "-A", "-o", ",".join(f + "=" for f in fields)],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return out.splitlines()


class Table:
    """One look at every process: pid -> (ppid, name, command line)."""

    def __init__(self, procs=None):
        self.procs = procs if procs is not None else (self._linux() if linux() else self._other())
        self.kids = {}
        for pid, (ppid, _, _) in self.procs.items():
            self.kids.setdefault(ppid, []).append(pid)

    @staticmethod
    def _linux():
        procs = {}
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open(f"/proc/{d}/stat", "rb") as f:
                    stat = f.read().decode("utf-8", "replace")
                with open(f"/proc/{d}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            except OSError:
                continue
            name = stat[stat.find("(") + 1:stat.rfind(")")]
            rest = stat[stat.rfind(")") + 2:].split()
            try:
                procs[int(d)] = (int(rest[1]), name, cmd)
            except (IndexError, ValueError):
                continue
        return procs

    @staticmethod
    def _other():
        procs = {}
        names = {}
        for line in _ps("pid", "ppid", "comm"):
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                names[int(parts[0])] = (int(parts[1]), os.path.basename(parts[2].strip()))
        for line in _ps("pid", "args"):
            parts = line.strip().split(None, 1)
            if parts and parts[0].isdigit() and int(parts[0]) in names:
                ppid, name = names[int(parts[0])]
                procs[int(parts[0])] = (ppid, name, parts[1] if len(parts) > 1 else "")
        return procs

    def ppid(self, pid):
        return (self.procs.get(pid) or (None,))[0]

    def descendants(self, pid):
        out, stack = [], list(self.kids.get(pid, []))
        while stack:
            p = stack.pop()
            if p in out:
                continue
            out.append(p)
            stack.extend(self.kids.get(p, []))
        return out

    def busy(self, pids):
        """A command running under any of these processes (see SHELLS), as
        "name: command line", or "" when there's none."""
        for root in pids:
            for p in self.descendants(root):
                _, name, cmd = self.procs.get(p, (0, "", ""))
                if name.lstrip("-") in SHELLS or "shell-snapshots" in cmd:
                    return f"{name}: {cmd[:80]}"
        return ""


def start_token(pid):
    """Something that changes if pid is reused: the start time in clock ticks
    on Linux, `ps -o lstart` elsewhere. None if the process is gone."""
    if linux():
        try:
            with open(f"/proc/{pid}/stat", "rb") as f:
                stat = f.read().decode("utf-8", "replace")
            return stat[stat.rfind(")") + 2:].split()[19]
        except (OSError, IndexError):
            return None
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def started_at(pid):
    """When the process started (epoch seconds), or None."""
    if linux():
        token = start_token(pid)
        try:
            with open("/proc/stat") as f:
                btime = next(int(line.split()[1]) for line in f if line.startswith("btime "))
            return btime + int(token) / os.sysconf("SC_CLK_TCK")
        except (OSError, StopIteration, TypeError, ValueError):
            return None
    try:  # macOS has no etimes; etime is [[dd-]hh:]mm:ss
        out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        text = out.stdout.strip()
        days, _, clock = text.rpartition("-")
        seconds = 0
        for part in clock.split(":"):
            seconds = seconds * 60 + int(part)
        return time.time() - seconds - int(days or 0) * 86400
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


_ENV_WORD = re.compile(rb"^[A-Za-z_][A-Za-z0-9_]*=")


def environ(pid):
    """A process's environment as it was started, as a dict, or None when it
    couldn't be read (the caller asks again later). Exports a shell made
    after it started aren't in its own; its children have them."""
    if linux():
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                items = f.read().split(b"\0")
        except OSError:
            return None
        out = {}
        for item in items:
            name, eq, value = item.partition(b"=")
            if eq and name:
                out[name.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
        return out
    try:
        res = subprocess.run(["ps", "eww", "-o", "command=", "-p", str(pid)], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0 or not res.stdout.strip():
        return None
    out, name, value = {}, None, []
    for word in res.stdout.split():
        if _ENV_WORD.match(word):
            if name:
                out[name] = b" ".join(value).decode("utf-8", "replace")
            raw, _, first = word.partition(b"=")
            name, value = raw.decode("utf-8", "replace"), [first]
        elif name:
            # `ps eww` separates variables with spaces, so a value with a
            # space (".../Application Support/...") goes on to the next
            # NAME=value word.
            value.append(word)
    if name:
        out[name] = b" ".join(value).decode("utf-8", "replace")
    return out


def environ_var(pid, name):
    """One variable of a process's environment: its value, "" when the
    environment was read and doesn't have it, or None when it couldn't be
    read (the caller asks again later)."""
    env = environ(pid)
    return None if env is None else env.get(name, "")


def _status(pid):
    return open(f"/proc/{pid}/status")


def memory_kb(pids):
    """Resident plus swapped-out memory of these processes, in kB (Linux)."""
    total = 0
    for pid in pids:
        try:
            with _status(pid) as f:
                for line in f:
                    if line.startswith(("VmRSS:", "VmSwap:")):
                        total += int(line.split()[1])
        except (OSError, ValueError, IndexError):
            continue
    return total


def total_kb():
    """Total memory in kB (Linux), or None."""
    try:
        with open("/proc/meminfo") as f:
            return next(int(line.split()[1]) for line in f if line.startswith("MemTotal:"))
    except (OSError, StopIteration, ValueError, IndexError):
        return None


def suspended_seconds():
    """How long the machine has slept since it booted (Linux: the boot
    clock minus the monotonic one, which stops during suspend), or None."""
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME) - time.clock_gettime(time.CLOCK_MONOTONIC)
    except (AttributeError, OSError):
        return None


MEMINFO = "/proc/meminfo"


def available_percent():
    """Memory still available, as a percentage of the total (Linux's
    MemAvailable, not MemFree: the page cache counts as available), or None
    where Earmark can't tell."""
    try:
        with open(MEMINFO) as f:
            info = {line.split(":")[0]: int(line.split()[1]) for line in f if line.split()[1:2] and line.split()[1].isdigit()}
        return 100.0 * info["MemAvailable"] / info["MemTotal"]
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        return None
