#!/bin/bash
# Earmark 1.2 README shoot: the demo session (stage.sh, agents.sh) in a foot
# window on workspace 9. Driven through Herdr's CLI and Earmark's own code:
# no simulated keys or mouse. Restores the workspace and do-not-disturb and
# closes only the window it opened.
#   shots: suspended, sidebar, hero (archive over a full sidebar), notes-NN (the
#   note popup as a Claude writes the note). Staged: the context percent of
#   two agents (short demo chats never fill a context window).
set -u
REPO=$(cd "$(dirname "$0")/../.." && pwd)
SP=${SHOOT_DIR:?}
OUT=$SP/shots; rm -rf "$OUT"; mkdir -p "$OUT"
PLACE_WINDOW=$HOME/.claude/skills/go-public/scripts/place-window.sh
export HERDR_CONFIG_PATH=/tmp/earmark-demo/herdr-config.toml
S=earmark-demo
H="env -u HERDR_SOCKET_PATH -u HERDR_PANE_ID -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID -u HERDR_ENV -u HERDR_SESSION herdr --session $S"
SOCK=$HOME/.config/herdr/sessions/$S/herdr.sock
d() { hyprctl dispatch "$1" >/dev/null; }
HOME_WS=$(hyprctl activeworkspace -j | jq .id)
DND_WAS=$(omarchy-shell notifications isDnd 2>/dev/null || echo off)
pane_of() { grep "^$1=" /tmp/earmark-demo/panes.txt | cut -d= -f2; }
ws_id() { $H workspace list | jq -r --arg l "$1" '.result.workspaces[] | select(.label == $l) | .workspace_id' | head -1; }
tab_of() { $H pane get "$1" | jq -r '.result.pane.tab_id'; }
tab_named() { $H tab list --workspace "$(ws_id "$1")" | jq -r --arg l "$2" '.result.tabs[] | select(.label == $l) | .tab_id'; }
popup_close() {
  python3 - "$SOCK" <<'EOF'
import json, socket, sys
c = socket.socket(socket.AF_UNIX); c.connect(sys.argv[1])
c.sendall(b'{"id":"shoot","method":"popup.close","params":{}}\n'); c.recv(4096); c.close()
EOF
  sleep 1
}
earmark() {  # Earmark's own code against the demo session
  env -u HERDR_PANE_ID -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID HERDR_SOCKET_PATH=$SOCK HERDR_SESSION=$S \
    python3 -c "import sys; sys.path.insert(0, '$REPO')
from earmark import agentrow, config, core, herdr, noteui, notes, sidebar, store
$1"
}
restore() {
  [ -n "${ADDR:-}" ] && d "hl.dsp.window.close({ window = \"address:$ADDR\" })"
  d "hl.dsp.focus({ workspace = \"$HOME_WS\" })"
  [ "$DND_WAS" = off ] && omarchy-shell notifications setDnd off >/dev/null 2>&1
  echo "restored: workspace $HOME_WS, DND $DND_WAS"
}
trap restore EXIT

omarchy-shell notifications setDnd on >/dev/null 2>&1; omarchy-shell notifications dismissAll >/dev/null 2>&1
d "hl.dsp.exec_cmd([[[workspace 9 silent] foot -a earmark-demo -o 'font=JetBrainsMono Nerd Font:size=11' env HERDR_CONFIG_PATH=$HERDR_CONFIG_PATH herdr --session $S]])"
for _ in $(seq 1 30); do ADDR=$(hyprctl clients -j | jq -r '.[] | select(.class == "earmark-demo") | .address' | head -1); [ -n "$ADDR" ] && break; sleep 0.3; done
[ -z "$ADDR" ] && { echo "demo window didn't open"; exit 1; }
d "hl.dsp.focus({ workspace = \"9\" })"; sleep 0.5
"$PLACE_WINDOW" "$ADDR" 140 100 1000 640 >/dev/null || { echo "couldn't place the window"; exit 1; }
sleep 1.5
read -r X Y W Hh < <(hyprctl clients -j | jq -r --arg a "$ADDR" '.[] | select(.address == $a) | "\(.at[0]) \(.at[1]) \(.size[0]) \(.size[1])"')
GEO="$X,$Y ${W}x$Hh"; echo "window at $GEO"
shot() { sleep "${2:-0.8}"; grim -g "$GEO" "$OUT/$1.png"; echo "  shot $1"; }

# 1. Suspend api's "errors" with Earmark's own key action, then look at it.
$H workspace focus "$(ws_id api)" >/dev/null
$H tab focus "$(tab_of "$(pane_of api/errors)")" >/dev/null; sleep 1.5
$H plugin action invoke io.github.cwilliams5.earmark.suspend >/dev/null; sleep 12
shot suspended 1

# Hero: a working agent, staged context levels, the archive over web's server tab.
$H pane send-text "$(pane_of api/migrations)" "Write a careful 500-word checklist for zero-downtime Postgres migrations. Don't run, create or edit anything." >/dev/null
sleep .8; $H pane send-keys "$(pane_of api/migrations)" enter >/dev/null
earmark "cfg = config.load()
for key, pct in (('web/checkout', 88), ('api/pagination', 71)):
    pid = [l.split('=')[1].strip() for l in open('/tmp/earmark-demo/panes.txt') if l.startswith(key + '=')][0]
    rec = agentrow.load('$S', pid)
    agentrow.update('$S', pid, dict(rec, percent=pct), cfg, sidebar.sidebar_width('$S'))
    print('staged', key, pct)"
$H workspace focus "$(ws_id web)" >/dev/null
$H tab focus "$(tab_named web server)" >/dev/null; sleep 4
shot sidebar 0.5
$H plugin pane open --plugin io.github.cwilliams5.earmark --entrypoint archive --env EARMARK_VIEW=sessions >/dev/null
shot hero 2
popup_close

# Notes: the popup open on docs' empty note; a Claude there asked to write
# it (what `u` does); the note appears in the open popup.
DOCS=$(ws_id docs)
earmark "notes.write('$S', '$DOCS', '', clear=True)"
$H workspace focus "$DOCS" >/dev/null
$H tab focus "$(tab_named docs notes)" >/dev/null; sleep 3
$H plugin pane open --plugin io.github.cwilliams5.earmark --entrypoint note --env "EARMARK_NOTE_WS=$DOCS" >/dev/null
shot notes-01 2
earmark "noteui.ask('$(pane_of docs/outline)')"
for i in 02 03 04 05 06 07 08 09 10 11 12 13 14; do shot notes-$i 5; done
popup_close
echo "note now:"; earmark "print(notes.read('$S', '$DOCS'))"
