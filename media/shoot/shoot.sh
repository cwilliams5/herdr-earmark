#!/bin/bash
# Earmark README shoot: a demo Herdr session (earmark-demo, its own config)
# in a foot window on workspace 9. Everything is driven through Herdr's CLI
# and socket API: no simulated keys or mouse. Restores workspace 1, DND and
# closes only the window it opened.
set -u
SP=${SHOOT_DIR:-/tmp/earmark-shoot}
OUT=$SP/shots; rm -rf "$OUT"; mkdir -p "$OUT"
export HERDR_CONFIG_PATH=/tmp/earmark-demo/herdr-config.toml
S=earmark-demo; H="herdr --session $S"; SOCK=$HOME/.config/herdr/sessions/$S/herdr.sock
PLACE_WINDOW=${PLACE_WINDOW:?set PLACE_WINDOW to a place-window script: float, size and move a Hyprland window by address}
d() { hyprctl dispatch "$1" >/dev/null; }
HOME_WS=$(hyprctl activeworkspace -j | jq .id)
DND_WAS=$(omarchy-shell notifications isDnd 2>/dev/null || echo off)
ws_id() { $H workspace list | jq -r --arg l "$1" '.result.workspaces[] | select(.label == $l) | .workspace_id' | head -1; }
popup_open() { $H plugin pane open --plugin io.github.cwilliams5.earmark --entrypoint archive --env "EARMARK_VIEW=$1" >/dev/null; sleep 2; }
popup_close() {
  python3 - "$SOCK" <<'EOF'
import json, socket, sys
c = socket.socket(socket.AF_UNIX); c.connect(sys.argv[1])
c.sendall(b'{"id":"shoot","method":"popup.close","params":{}}\n'); c.recv(4096); c.close()
EOF
  sleep 1
}
earmark() {  # python snippet run against the demo session
  HERDR_SOCKET_PATH=$SOCK HERDR_SESSION=$S python3 -c "import sys; sys.path.insert(0, '$(cd "$(dirname "$0")/../.." && pwd)')
from earmark import config, core, store
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
"$PLACE_WINDOW" "$ADDR" 150 110 900 580 >/dev/null || { echo "couldn't place the window"; exit 1; }
sleep 1.5
read -r X Y W Hh < <(hyprctl clients -j | jq -r --arg a "$ADDR" '.[] | select(.address == $a) | "\(.at[0]) \(.at[1]) \(.size[0]) \(.size[1])"')
GEO="$X,$Y ${W}x$Hh"; echo "window at $GEO"
shot() { sleep "${2:-0.8}"; grim -g "$GEO" "$OUT/$1.png"; echo "  shot $1"; }

WEB=$(ws_id web-app)
$H workspace focus "$WEB" >/dev/null
RN_TAB=$($H tab list --workspace "$WEB" | jq -r '.result.tabs[] | select(.label == "release notes") | .tab_id')
SRV_TAB=$($H tab list --workspace "$WEB" | jq -r '.result.tabs[] | select(.label == "server") | .tab_id')

# Hero: the archive over the plain server tab (a calm background).
$H tab focus "$SRV_TAB" >/dev/null; sleep 1
popup_open sessions; shot hero 0.5; popup_close
$H tab focus "$RN_TAB" >/dev/null; sleep 1

# GIF 1: close a tab, open the archive, reopen it.
shot g1-01-tab
$H tab close "$RN_TAB" >/dev/null; sleep 2; shot g1-02-closed
popup_open sessions; shot g1-03-archive 0.5
popup_close
earmark "e = next(dict(v, key=k) for k, v in store.load_archive()['entries'].items()
          if v['herdr_session'] == '$S' and v.get('tab_label') == 'release notes')
print('reopen:', core.reopen(e, {'workspace_id': '$WEB'}, config.load()) or 'ok')"
sleep 7; shot g1-04-back

# Workspaces view, over the server tab.
$H tab focus "$SRV_TAB" >/dev/null; sleep 1
popup_open workspaces; shot workspaces 0.5

# GIF 2: restore the closed docs workspace.
cp "$OUT/workspaces.png" "$OUT/g2-01-list.png"
popup_close
earmark "w = next(w for w in core.closed_workspaces(store.load_archive(), '$S') if w['label'] == 'docs')
print('restore:', core.restore_workspace(w, config.load()) or 'ok')"
sleep 8; shot g2-02-restored
NOTES=$($H tab list --workspace "$(ws_id docs)" | jq -r '.result.tabs[] | select(.label == "notes") | .tab_id')
$H tab focus "$NOTES" >/dev/null; sleep 1; shot g2-03-notes
ls -la "$OUT"
