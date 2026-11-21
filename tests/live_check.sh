#!/bin/bash
# End-to-end check against a real Herdr, in a throwaway named session
# ("herdr --session earmark-live-check server"), so the user's own session
# is never touched. Needs Claude Code; it sends two one-word prompts.
#
# It checks: a closed tab is archived under its workspace; reopening runs
# `claude --resume` in a new tab and the entry leaves the archive; /exit
# archives again; a server restart archives nothing. Then it removes the
# session, the test transcripts and the test's archive entries.
#
# Run from the repo: tests/live_check.sh   (about two minutes)
# Also test other agents (each must be installed and signed in):
#   EARMARK_AGENTS="codex grok" tests/live_check.sh
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD
S=earmark-live-check
H="herdr --session $S"
SOCK="$HOME/.config/herdr/sessions/$S/herdr.sock"
STATE="$HOME/.local/state/herdr/plugins/io.github.cwilliams5.earmark"
# One fixed folder, so Claude Code records a single trusted test folder. It's
# in the user's private runtime folder, not a shared /tmp: the agents are
# told to trust it, so nobody else may be able to put files there first.
DIR=${XDG_RUNTIME_DIR:-$HOME/.cache}/earmark-live-check
mkdir -p -m 700 "$DIR"
[ -O "$DIR" ] && [ ! -L "$DIR" ] || { echo "$DIR isn't a folder of yours; not using it" >&2; exit 1; }
SLUG=$(echo "$DIR" | sed 's|[/.]|-|g')  # Claude Code's project folder name for it
PASS=0 FAIL=0

ok()   { echo "  ok: $*"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL: $*"; FAIL=$((FAIL + 1)); }
say()  { echo "== $*"; }
entry() {  # field of this test's archive entry for a session id ("" if absent)
  jq -r --arg s "$S" --arg id "$1" --arg f "$2" \
    '[.entries[] | select(.herdr_session == $s and .session_id == $id)][0][$f] // ""' \
    "$STATE/archive.json" 2>/dev/null
}
start_server() {
  (cd /tmp && setsid nohup herdr --session $S server >>"$DIR/server.log" 2>&1 </dev/null &)
  for _ in $(seq 1 30); do $H workspace list >/dev/null 2>&1 && return 0; sleep 0.3; done
  echo "test server didn't start"; exit 1
}
wait_session() {  # pane -> session id
  for _ in $(seq 1 60); do
    s=$($H pane get "$1" 2>/dev/null | jq -r '.result.pane.agent_session.value // empty')
    [ -n "$s" ] && { echo "$s"; return 0; }
    sleep 0.5
  done; return 1
}
wait_idle() {  # pane: until Claude is idle again after a prompt
  sleep 3
  for _ in $(seq 1 60); do
    st=$($H pane get "$1" 2>/dev/null | jq -r '.result.pane.agent_status // empty')
    [ "$st" = idle ] || [ "$st" = done ] && return 0
    sleep 1
  done; return 1
}
claude_tab() {  # workspace label -> pane id running claude with one prompt answered
  local r p
  r=$($H tab create --workspace "$1" --cwd "$DIR" --label probe --no-focus)
  p=$(echo "$r" | jq -r '.result.root_pane.pane_id')
  $H pane run "$p" claude >/dev/null
  sleep 4
  # The first run asks whether to trust the folder, defaulting to "No, exit":
  # pick "Yes, I trust this folder".
  if $H pane read "$p" --source visible 2>/dev/null | grep -qi "trust this folder"; then
    $H pane send-keys "$p" down >/dev/null; sleep 0.3; $H pane send-keys "$p" enter >/dev/null
  fi
  echo "$p"
}
prompt() {
  $H pane send-text "$1" "Reply with the single word OK." >/dev/null
  sleep 0.5; $H pane send-keys "$1" enter >/dev/null
  wait_idle "$1"
}
cleanup() {
  say "cleaning up"
  $H server stop >/dev/null 2>&1; sleep 1
  herdr session delete $S >/dev/null 2>&1
  # Through Earmark's own store, under its lock: the user's real hooks share
  # these files.
  python3 - "$S" "$ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[2])
from earmark import store
with store.locked():
    archive = store.load_archive()
    for part in ("entries", "workspaces"):
        archive[part] = {k: v for k, v in archive[part].items() if v.get("herdr_session") != sys.argv[1]}
    store.save_archive(archive)
    index = store.load_index()
    index["sessions"].pop(sys.argv[1], None)
    store.save_index(index)
EOF
  rm -rf "$HOME/.claude/projects/$SLUG" "$DIR"
  echo "passed $PASS, failed $FAIL"
}
trap cleanup EXIT

say "starting the test session"
start_server
WS=$($H workspace create --cwd "$DIR" --label Alpha --no-focus | jq -r '.result.workspace.workspace_id')
$H workspace create --cwd "$DIR" --label Beta --no-focus >/dev/null

say "1. closing a tab archives its session under the workspace"
P=$(claude_tab "$WS"); SID=$(wait_session "$P") || { bad "no session reported"; exit 1; }
prompt "$P" || bad "Claude didn't answer"
T=$($H pane get "$P" | jq -r '.result.pane.tab_id')
$H tab close "$T" >/dev/null; sleep 2
[ "$(entry "$SID" workspace_label)" = Alpha ] && ok "archived under Alpha" || bad "not archived under Alpha"
[ "$(entry "$SID" reason)" = closed ] && ok "reason: closed" || bad "reason: $(entry "$SID" reason)"

say "2. reopening resumes it in a new tab and it leaves the archive"
HERDR_SOCKET_PATH=$SOCK HERDR_SESSION=$S python3 - "$SID" "$STATE" "$ROOT" <<'EOF' || bad "reopen failed"
import json, os, sys
sys.path.insert(0, sys.argv[3])
from earmark import config, core
entries = json.load(open(os.path.join(sys.argv[2], "archive.json")))["entries"]
key, e = next((k, v) for k, v in entries.items() if v["session_id"] == sys.argv[1])
err = core.reopen(dict(e, key=key), {}, config.load())
sys.exit(1 if err else 0)
EOF
sleep 3
P2=$($H pane list | jq -r --arg s "$SID" '.result.panes[] | select(.agent_session.value == $s) | .pane_id' | head -1)
[ -z "$P2" ] && P2=$($H pane list | jq -r '.result.panes[] | select(.agent == "claude") | .pane_id' | tail -1)
S2=$(wait_session "$P2")
[ "$S2" = "$SID" ] && ok "same session resumed in $P2" || bad "resumed session '$S2' != '$SID'"
$H pane get "$P2" >/dev/null; sleep 1
[ -z "$(entry "$SID" session_id)" ] && ok "left the archive" || bad "still archived while live"

say "3. /exit archives it again"
$H pane send-text "$P2" "/exit" >/dev/null; sleep 0.5; $H pane send-keys "$P2" enter >/dev/null; sleep 4
[ "$(entry "$SID" reason)" = exited ] && ok "reason: exited" || bad "after /exit: '$(entry "$SID" reason)'"

say "4. a server restart archives nothing"
P3=$(claude_tab "$WS"); SID3=$(wait_session "$P3") || bad "no session for restart test"
prompt "$P3" || bad "Claude didn't answer"
$H pane get "$P3" >/dev/null; sleep 1
BEFORE=$(jq --arg s "$S" '[.entries[] | select(.herdr_session == $s)] | length' "$STATE/archive.json")
$H server stop >/dev/null; sleep 2
start_server; sleep 6
AFTER=$(jq --arg s "$S" '[.entries[] | select(.herdr_session == $s)] | length' "$STATE/archive.json")
[ "$AFTER" = "$BEFORE" ] && ok "archive unchanged across restart ($AFTER)" || bad "archive went from $BEFORE to $AFTER"
[ -z "$(entry "$SID3" session_id)" ] && ok "restored session not archived" || bad "restored session archived"

say "5. a closed workspace comes back with its tabs, names and session"
GW=$($H workspace create --cwd "$DIR" --label Gamma --no-focus | jq -r '.result.workspace.workspace_id')
GT1=$($H tab list --workspace "$GW" | jq -r '.result.tabs[0].tab_id')
$H tab rename "$GT1" notes >/dev/null
PG=$(claude_tab "$GW"); SIDG=$(wait_session "$PG") || bad "no session in Gamma"
prompt "$PG" || bad "Claude didn't answer"
$H tab rename "$($H pane get "$PG" | jq -r '.result.pane.tab_id')" agent-work >/dev/null
$H pane get "$PG" >/dev/null; sleep 1
$H workspace close "$GW" >/dev/null; sleep 2
REC=$(jq -c --arg s "$S" '[.workspaces[]? | select(.herdr_session == $s and .label == "Gamma")][0]' "$STATE/archive.json")
[ "$(echo "$REC" | jq '.tabs | length')" = 2 ] && ok "recorded Gamma with 2 tabs" || bad "record: $REC"
[ "$(entry "$SIDG" workspace_label)" = Gamma ] && ok "its session archived under Gamma" || bad "session not archived"
HERDR_SOCKET_PATH=$SOCK HERDR_SESSION=$S python3 - "$STATE" "$ROOT" "$S" <<'EOF2' || bad "restore failed"
import json, os, sys
sys.path.insert(0, sys.argv[2])
from earmark import config, core
archive = json.load(open(os.path.join(sys.argv[1], "archive.json")))
rec = next(r for r in core.closed_workspaces(archive, sys.argv[3]) if r["label"] == "Gamma")
err = core.restore_workspace(rec, config.load())
print(err or "", end="")
sys.exit(1 if err else 0)
EOF2
sleep 3
NW=$($H workspace list | jq -r '.result.workspaces[] | select(.label == "Gamma") | .workspace_id')
LABELS=$($H tab list --workspace "$NW" | jq -r '[.result.tabs[] | .label] | join(",")')
[ "$LABELS" = "notes,agent-work" ] && ok "tabs back in order: $LABELS" || bad "tabs: '$LABELS'"
PR=$($H pane list | jq -r --arg w "$NW" '.result.panes[] | select(.workspace_id == $w and .agent == "claude") | .pane_id' | head -1)
[ -n "$PR" ] && [ "$(wait_session "$PR")" = "$SIDG" ] && ok "agent tab resumed its session" || bad "session not resumed"
[ "$(jq --arg s "$S" '[.workspaces[]? | select(.herdr_session == $s)] | length' "$STATE/archive.json")" = 0 ] \
  && ok "closed-workspace record removed" || bad "record still there"

for AG in ${EARMARK_AGENTS:-}; do
  say "6. $AG: close, reopen through Earmark, close again"
  r=$($H tab create --workspace "$WS" --cwd "$DIR" --label "$AG-tab" --no-focus)
  PA=$(echo "$r" | jq -r '.result.root_pane.pane_id')
  # Codex 0.157+ runs sessions in a shared daemon that reports them to the
  # wrong pane (herdrdev/herdr#4649); --no-daemon is Herdr's workaround.
  case "$AG" in codex) $H pane run "$PA" codex --no-daemon >/dev/null ;; *) $H pane run "$PA" "$AG" >/dev/null ;; esac
  sleep 6
  SCREEN=$($H pane read "$PA" --source visible 2>/dev/null)
  if echo "$SCREEN" | grep -qi "trust"; then  # first run in the folder
    case "$AG" in grok) $H pane send-text "$PA" y >/dev/null ;; *) $H pane send-keys "$PA" down >/dev/null; sleep .3; $H pane send-keys "$PA" enter >/dev/null ;; esac
    sleep 4
  fi
  prompt "$PA" || bad "$AG didn't answer"
  SA=$(wait_session "$PA") || { bad "$AG reported no session"; continue; }
  $H tab close "$($H pane get "$PA" | jq -r '.result.pane.tab_id')" >/dev/null; sleep 2
  T=$(entry "$SA" title)
  [ -n "$(entry "$SA" session_id)" ] && ok "$AG archived as \"$T\"" || { bad "$AG not archived"; continue; }
  HERDR_SOCKET_PATH=$SOCK HERDR_SESSION=$S python3 - "$SA" "$ROOT" <<'EOF3' || bad "$AG reopen failed"
import sys
sys.path.insert(0, sys.argv[2])
from earmark import config, core, store
e = next(dict(v, key=k) for k, v in store.load_archive()["entries"].items() if v["session_id"] == sys.argv[1])
sys.exit(1 if core.reopen(e, {}, config.load()) else 0)
EOF3
  sleep 8
  PB=$($H pane list | jq -r --arg a "$AG" '.result.panes[] | select(.agent == $a) | .pane_id' | tail -1)
  $H pane read "$PB" --source recent 2>/dev/null | grep -q "single word OK" && ok "$AG conversation is back" || bad "$AG conversation not shown"
  [ -z "$(entry "$SA" session_id)" ] && ok "$AG left the archive" || bad "$AG still archived"
  $H tab close "$($H pane get "$PB" | jq -r '.result.pane.tab_id')" >/dev/null; sleep 2
  [ -n "$(entry "$SA" session_id)" ] && ok "$AG archived again after closing the reopened tab" || bad "$AG lost after reopen + close"
done
