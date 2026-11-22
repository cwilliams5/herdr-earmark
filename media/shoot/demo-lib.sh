# Helpers for staging Earmark's demo session.
# Staging for the README media (see media/shoot/README.md). Source it.
export HERDR_CONFIG_PATH=/tmp/earmark-demo/herdr-config.toml
H="herdr --session earmark-demo"
ws_id() { $H workspace list | jq -r --arg l "$1" '.result.workspaces[] | select(.label == $l) | .workspace_id' | head -1; }
wait_ready() {  # pane: until the agent answered
  sleep 4
  for _ in $(seq 1 90); do
    st=$($H pane get "$1" | jq -r '.result.pane.agent_status // empty')
    [ "$st" = idle ] || [ "$st" = done ] && return 0
    sleep 1
  done; echo "  (timeout waiting for $1)"; return 1
}
agent_tab() {  # workspace-label tab-label agent prompt [reuse-pane] -> runs one exchange; prints pane id
  local ws p r
  ws=$(ws_id "$1")
  if [ -n "${5:-}" ]; then p=$5; [ -n "$2" ] && $H tab rename "$($H pane get "$p" | jq -r '.result.pane.tab_id')" "$2" >/dev/null
  else
    if [ -n "$2" ]; then r=$($H tab create --workspace "$ws" --cwd "/tmp/demo/$1" --label "$2" --no-focus)
    else r=$($H tab create --workspace "$ws" --cwd "/tmp/demo/$1" --no-focus); fi
    p=$(echo "$r" | jq -r '.result.root_pane.pane_id')
  fi
  case "$3" in codex) $H pane run "$p" codex --no-daemon >/dev/null ;; *) $H pane run "$p" "$3" >/dev/null ;; esac
  sleep 7
  if $H pane read "$p" --source visible 2>/dev/null | grep -qi "trust"; then
    case "$3" in grok) $H pane send-text "$p" y >/dev/null ;; *) $H pane send-keys "$p" down >/dev/null; sleep .3; $H pane send-keys "$p" enter >/dev/null ;; esac
    sleep 5
  fi
  $H pane send-text "$p" "$4" >/dev/null; sleep .6; $H pane send-keys "$p" enter >/dev/null
  wait_ready "$p"
  echo "$p"
}
