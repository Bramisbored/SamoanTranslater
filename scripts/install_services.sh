#!/bin/bash
# Start the server and the tunnel automatically whenever you're logged in to the Mac mini.
#   bash scripts/install_services.sh          install / reinstall
#   bash scripts/install_services.sh remove   uninstall
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$DIR/logs"
SERVER_LABEL="com.samoantranslater.server"
TUNNEL_LABEL="com.samoantranslater.tunnel"
DOMAIN="gui/$(id -u)"

unload() { launchctl bootout "$DOMAIN/$1" 2>/dev/null || true; rm -f "$AGENTS/$1.plist"; }

if [ "${1:-}" = "remove" ]; then
  unload "$SERVER_LABEL"; unload "$TUNNEL_LABEL"
  echo "Removed."; exit 0
fi

[ -x "$DIR/.venv/bin/uvicorn" ] || { echo "Run scripts/setup_mac.sh first." >&2; exit 1; }
[ -f "$HOME/.cloudflared/samoan.yml" ] || { echo "Run scripts/setup_tunnel.sh first." >&2; exit 1; }
mkdir -p "$AGENTS" "$LOGS"
CLOUDFLARED="$(command -v cloudflared)"

unload "$SERVER_LABEL"
cat > "$AGENTS/$SERVER_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$SERVER_LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/uvicorn</string><string>app:app</string>
    <string>--host</string><string>127.0.0.1</string><string>--port</string><string>8000</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR/server</string>
  <key>EnvironmentVariables</key><dict>
    <key>PRELOAD_MODELS</key><string>1</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGS/server.log</string>
  <key>StandardErrorPath</key><string>$LOGS/server.log</string>
</dict></plist>
EOF

unload "$TUNNEL_LABEL"
cat > "$AGENTS/$TUNNEL_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$TUNNEL_LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$CLOUDFLARED</string><string>tunnel</string>
    <string>--config</string><string>$HOME/.cloudflared/samoan.yml</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGS/tunnel.log</string>
  <key>StandardErrorPath</key><string>$LOGS/tunnel.log</string>
</dict></plist>
EOF

launchctl bootstrap "$DOMAIN" "$AGENTS/$SERVER_LABEL.plist"
launchctl bootstrap "$DOMAIN" "$AGENTS/$TUNNEL_LABEL.plist"
echo "Installed. Logs: $LOGS (server takes ~30s to load the models after each start)."
echo "Check: curl -s http://127.0.0.1:8000/api/health"
