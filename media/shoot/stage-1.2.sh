#!/bin/bash
# Stage Earmark's 1.2 README demo: a headless named Herdr session
# (earmark-demo) with its own config, three workspaces over /tmp/demo and
# real agents doing short, neutral things. Nothing on screen.
set -u
LAUNCHER=$(herdr plugin config-dir io.github.cwilliams5.earmark)/earmark
mkdir -p /tmp/earmark-demo
export HERDR_CONFIG_PATH=/tmp/earmark-demo/herdr-config.toml
# The demo's config: the user's, without the hostname, with a sidebar wide
# enough for an agent line in full.
python3 - "$HOME/.config/herdr/config.toml" "$HERDR_CONFIG_PATH" <<'PYEOF'
import sys
text = open(sys.argv[1]).read()
text = text.replace('tab_bar_right = [{ type = "zoom" }, { type = "hostname" }]', 'tab_bar_right = [{ type = "zoom" }]')
lines = text.splitlines()
out, done = [], False
for line in lines:
    out.append(line)
    if line.strip() == "[ui]" and not done:
        out.append("sidebar_width = 30")
        done = True
assert done
open(sys.argv[2], "w").write("\n".join(out) + "\n")
PYEOF
grep -q 'type = "hostname"' "$HERDR_CONFIG_PATH" && { echo "hostname still in the demo config"; exit 1; }

for w in web docs api; do
  mkdir -p /tmp/demo/$w/.claude
  printf '{ "statusLine": { "type": "command", "command": "%s statusline" } }\n' "$LAUNCHER" > /tmp/demo/$w/.claude/settings.json
done
printf '# web\nA small storefront: Express API, React front end.\n' > /tmp/demo/web/README.md
printf '# docs\nThe user guide, in Markdown.\n' > /tmp/demo/docs/README.md
printf '# api\nThe public REST API.\n' > /tmp/demo/api/README.md

clean_env="env -u HERDR_SOCKET_PATH -u HERDR_PANE_ID -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID -u HERDR_ENV -u HERDR_SESSION"
setsid nohup $clean_env HERDR_CONFIG_PATH=$HERDR_CONFIG_PATH herdr --session earmark-demo server >/tmp/earmark-demo/server.log 2>&1 &
sleep 3
H="$clean_env herdr --session earmark-demo"
export H
echo "server: $($H session list --json | jq -c '.sessions[] | select(.name == "earmark-demo") | .running')"
for w in web docs api; do $H workspace create --label $w --cwd /tmp/demo/$w >/dev/null; done
$H workspace list | jq -c '[.result.workspaces[] | {workspace_id, label}]'
