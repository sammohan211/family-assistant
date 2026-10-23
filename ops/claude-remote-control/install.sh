#!/usr/bin/env bash
# Copy the Claude Remote Control setup to the server's `sam` user.
#
# Runs on the laptop from the repo root. Copies the service template, the `rc`
# command, the server CLAUDE.md and Claude settings (deny rules), then reloads
# systemd. Running sessions keep going on the old service file until restarted
# (`rc restart <repo>`).
#
#   ops/claude-remote-control/install.sh                  # host family-assistant-sam
#   RC_HOST=other-alias ops/claude-remote-control/install.sh
set -euo pipefail

# Not $HOST: many shells already set that to the local machine name.
RC_HOST="${RC_HOST:-family-assistant-sam}"
DIR="$(cd "$(dirname "$0")" && pwd)"

ssh "$RC_HOST" 'mkdir -p ~/.config/systemd/user ~/.local/bin ~/.claude'
scp -q "$DIR/claude-rc@.service" "$RC_HOST:.config/systemd/user/claude-rc@.service"
scp -q "$DIR/rc" "$RC_HOST:.local/bin/rc"
scp -q "$DIR/server-CLAUDE.md" "$RC_HOST:.claude/CLAUDE.md"
scp -q "$DIR/server-settings.json" "$RC_HOST:.claude/settings.json"
ssh "$RC_HOST" 'chmod +x ~/.local/bin/rc && systemctl --user daemon-reload && systemd-analyze --user verify ~/.config/systemd/user/claude-rc@.service && ~/.local/bin/rc list'
echo "Installed. Restart a repo to pick up service changes: ssh $RC_HOST .local/bin/rc restart <repo>"
