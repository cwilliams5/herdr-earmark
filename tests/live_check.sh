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
# Run from the repo: tests/live_check.sh   (about a minute)
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD
S=earmark-live-check
H="herdr --session $S"
SOCK="$HOME/.config/herdr/sessions/$S/herdr.sock"
STATE="$HOME/.local/state/herdr/plugins/io.github.cwilliams5.earmark"
# One fixed folder, so Claude Code records a single trusted test folder.
DIR=/tmp/earmark-live-check
mkdir -p "$DIR"
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
  python3 - "$STATE" "$S" <<'EOF'
import json, os, sys
state, s = sys.argv[1], sys.argv[2]
for name, drop in (("archive.json", lambda d: {k: v for k, v in d.get("entries", {}).items() if v.get("herdr_session") != s}),):
    p = os.path.join(state, name)
    if os.path.exists(p):
        d = json.load(open(p)); d["entries"] = drop(d); json.dump(d, open(p, "w"), indent=1)
p = os.path.join(state, "index.json")
if os.path.exists(p):
    d = json.load(open(p)); d.get("sessions", {}).pop(s, None); json.dump(d, open(p, "w"), indent=1)
EOF
  rm -rf "$HOME/.claude/projects/-tmp-earmark-live-check" "$DIR"
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
