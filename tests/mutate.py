#!/usr/bin/env python3
"""Mutation check: plant each one-line regression from tests/mutations.md in
a scratch copy of the repo, one at a time, and run the whole unit suite. A
mutation the suite doesn't catch is a SURVIVOR: that behaviour isn't really
tested.

    python3 tests/mutate.py            all mutations
    python3 tests/mutate.py rearm      only those whose name contains "rearm"

Rules learned from earlier reviews (strict-review checklist):
- the unmutated suite must pass first, or every mutant would count as killed;
- a mutation whose pattern no longer matches the code is a FAILURE of the
  list, not a kill (fix the pattern);
- each kill is confirmed by running the suite again (a flake isn't a catch),
  and the test that caught it is recorded;
- a mutated file that doesn't compile is BROKEN, not caught (every test
  would fail on the import).

Never touches the working copy; the copies are deleted afterwards. The suite
can't reach a real Herdr (the test modules point HERDR_BIN_PATH at nothing).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(ROOT, "tests", "mutations.md")
ENV = {k: v for k, v in os.environ.items() if k != "HERDR_SOCKET_PATH"}
ENV["HERDR_BIN_PATH"] = "/nonexistent/herdr-blocked-in-tests"


def mutations():
    """Each `### name` section of mutations.md: the file, then a ```old```
    block and a ```new``` block (exact text)."""
    text = open(LIST, encoding="utf-8").read()
    out = []
    for section in re.split(r"^### ", text, flags=re.M)[1:]:
        name = section.splitlines()[0].strip()
        path = re.search(r"^file: (\S+)", section, re.M)
        blocks = re.findall(r"```(?:old|new)\n(.*?)\n```", section, re.S)
        if not path or len(blocks) != 2:
            out.append((name, None, None, None))
            continue
        out.append((name, path.group(1), blocks[0], blocks[1]))
    return out


def run_suite(cwd):
    # A sandbox of its own around the suite's: a mutant that switches off
    # tests/_isolate.py (R159's does) must not run the other tests against
    # the real home (one wrote the maintainer's Omarchy theme hook that way).
    home = os.path.join(os.path.dirname(cwd), "home")
    env = dict(ENV, HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"),
               XDG_STATE_HOME=os.path.join(home, ".local", "state"), XDG_DATA_HOME=os.path.join(home, ".local", "share"))
    for path in (env["XDG_CONFIG_HOME"], env["XDG_STATE_HOME"], env["XDG_DATA_HOME"]):
        os.makedirs(path, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "tests"], cwd=cwd, env=env,
                       capture_output=True, text=True, timeout=120, preexec_fn=_cap_memory)
    failed = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", r.stderr, re.M)
    return r.returncode == 0, [f"{cls.split('.')[-2] if cls.count('.') >= 2 else cls}.{test}" for test, cls in failed]


def _cap_memory():
    """A planted bug can loop forever growing a list: cap each suite run at
    2 GB of address space, so it dies (counted as caught) long before it
    hurts the machine (a hung mutant once grew to 13.7 GB)."""
    import resource
    limit = 2 * 1024 ** 3
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ValueError, OSError):
        pass


def copy():
    d = tempfile.mkdtemp(prefix="earmark-mutate-")
    shutil.copytree(ROOT, os.path.join(d, "r"),
                    ignore=shutil.ignore_patterns(".git", "media", "branding", "__pycache__"))
    return d, os.path.join(d, "r")


def main(argv):
    # python3 tests/mutate.py [name filter] [--shard i/n]: --shard runs every
    # n-th mutation from the i-th (0-based), so n copies can run in parallel.
    args = list(argv[1:])
    shard = None
    if "--shard" in args:
        i = args.index("--shard")
        k, n = (int(x) for x in args[i + 1].split("/"))
        shard = (k, n)
        del args[i:i + 2]
    only = args[0] if args else ""
    d, r = copy()
    try:
        ok, failed = run_suite(r)
    finally:
        shutil.rmtree(d)
    if not ok:
        print(f"baseline FAILS ({', '.join(failed[:5])}): fix the suite first")
        return 2
    caught = survived = broken = 0
    for index, (name, path, old, new) in enumerate(mutations()):
        if only and only not in name:
            continue
        if shard and index % shard[1] != shard[0]:
            continue
        if path is None:
            print(f"  BROKEN   {name}: needs a file: line and an old and a new block")
            broken += 1
            continue
        d, r = copy()
        try:
            target = os.path.join(r, path)
            src = open(target, encoding="utf-8").read()
            if src.count(old) != 1:
                print(f"  BROKEN   {name}: pattern found {src.count(old)} times in {path}")
                broken += 1
                continue
            mutated = src.replace(old, new)
            if path.endswith(".py"):
                try:  # a mutant that doesn't compile fails every test: that's no catch
                    compile(mutated, target, "exec")
                except SyntaxError as e:
                    print(f"  BROKEN   {name}: the mutated {path} doesn't compile ({e.msg}, line {e.lineno})")
                    broken += 1
                    continue
            open(target, "w", encoding="utf-8").write(mutated)
            def once():
                try:
                    return run_suite(r)
                except subprocess.TimeoutExpired:
                    return False, ["(timed out)"]
            ok, failed = once()
            if not ok:  # confirm (a hang too): a flake isn't a catch
                ok2, failed2 = once()
                ok = ok2
                failed = failed2 or failed
        finally:
            shutil.rmtree(d)
        if ok:
            print(f"  SURVIVED {name}")
            survived += 1
        else:
            print(f"  caught   {name}  by {failed[0] if failed else '?'}")
            caught += 1
    print(f"{caught} caught, {survived} survived, {broken} broken patterns")
    return 0 if not survived and not broken else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
