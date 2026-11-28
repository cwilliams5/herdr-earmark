#!/bin/bash
# Real agents in the demo session (see stage.sh). One workspace per call:
# agents.sh web|docs|api. Logs the pane ids it made.
set -u
export HERDR_CONFIG_PATH=/tmp/earmark-demo/herdr-config.toml
H="env -u HERDR_SOCKET_PATH -u HERDR_PANE_ID -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID -u HERDR_ENV -u HERDR_SESSION herdr --session earmark-demo"
ws_id() { $H workspace list | jq -r --arg l "$1" '.result.workspaces[] | select(.label == $l) | .workspace_id' | head -1; }
wait_ready() {  # pane: until the agent answered (or asks for permission: blocked)
  sleep 4
  for _ in $(seq 1 150); do
    st=$($H pane get "$1" | jq -r '.result.pane.agent_status // empty')
    case "$st" in idle|done|blocked) return 0 ;; esac
    sleep 1
  done; echo "  (timeout waiting for $1)" >&2; return 1
}
new_tab() {  # workspace tab-label -> pane id
  local r
  if [ -n "$2" ]; then r=$($H tab create --workspace "$(ws_id "$1")" --cwd "/tmp/demo/$1" --label "$2" --no-focus)
  else r=$($H tab create --workspace "$(ws_id "$1")" --cwd "/tmp/demo/$1" --no-focus); fi
  echo "$r" | jq -r '.result.root_pane.pane_id'
}
ask() {  # workspace tab-label prompt agent-argv... -> one exchange; prints the pane id
  local ws=$1 label=$2 prompt=$3 p; shift 3
  p=$(new_tab "$ws" "$label")
  $H pane run "$p" "$@" >/dev/null
  sleep 8
  if $H pane read "$p" --source recent --lines 40 2>/dev/null | grep -qi "trust"; then
    case "$1" in grok) $H pane send-text "$p" y >/dev/null ;; *) $H pane send-keys "$p" down >/dev/null; sleep .3; $H pane send-keys "$p" enter >/dev/null ;; esac
    sleep 6
  fi
  $H pane send-text "$p" "$prompt" >/dev/null; sleep .8; $H pane send-keys "$p" enter >/dev/null
  wait_ready "$p"
  echo "$ws/$label=$p" >> /tmp/earmark-demo/panes.txt
  echo "$p"
}
closed() {  # an exchange, then the tab closed: archived
  local p; p=$(ask "$@")
  sleep 2
  $H tab close "$($H pane get "$p" | jq -r '.result.pane.tab_id')" >/dev/null
}
NO_EDIT="Don't run, create or edit anything; just answer."
case "$1" in
web)
  $H tab rename "$($H tab list --workspace "$(ws_id web)" | jq -r '.result.tabs[0].tab_id')" server >/dev/null
  closed web "rate limits" "In two sentences: how would you add rate limiting to an Express login route? $NO_EDIT" claude
  closed web "flaky tests" "In three sentences: why might a Vitest test pass alone but fail in the full suite? $NO_EDIT" codex --no-daemon
  closed web "react 19" "In two sentences: what's the main thing to check when upgrading from React 18 to 19? $NO_EDIT" grok
  closed web "" "In two sentences: why would date range queries in Postgres get slow, and what's the usual fix? $NO_EDIT" claude
  ask web "release notes" "Draft two short release-note bullets for a fix that stops double charges at checkout. $NO_EDIT" codex --no-daemon
  ask web checkout "Run ls -la in this folder and tell me in one line what's here." claude
  ;;
docs)
  $H tab rename "$($H tab list --workspace "$(ws_id docs)" | jq -r '.result.tabs[0].tab_id')" notes >/dev/null
  ask docs outline "Suggest a five-section outline for the admin guide of a small online store, one line per section. $NO_EDIT" claude --permission-mode auto
  ask docs glossary "Define 'idempotency key' in one sentence for a payments glossary. $NO_EDIT" grok
  ;;
api)
  $H tab rename "$($H tab list --workspace "$(ws_id api)" | jq -r '.result.tabs[0].tab_id')" shell >/dev/null
  closed api versioning "In two sentences: URL versioning or header versioning for a public REST API? $NO_EDIT" claude
  closed api webhooks "In two sentences: how should a webhook receiver handle retries? $NO_EDIT" grok
  ask api pagination "In two sentences: cursor or offset pagination for an orders endpoint? $NO_EDIT" codex --no-daemon
  ask api errors "In two sentences: what should a JSON error body for a REST API contain? $NO_EDIT" claude
  ask api migrations "In one sentence: what makes a database migration safe to run during a deploy? $NO_EDIT" claude
  ;;
esac
echo "$1 done"
