#!/bin/bash
# Create a Cloudflare Tunnel that points your hostname at the server on this Mac.
#   bash scripts/setup_tunnel.sh samoan.yourdomain.com
# The domain must already be on your Cloudflare account.
set -euo pipefail
HOST="${1:?Usage: setup_tunnel.sh samoan.yourdomain.com}"
NAME="${TUNNEL_NAME:-samoan}"
PORT="${PORT:-8000}"
CF="$HOME/.cloudflared"

if [ ! -f "$CF/cert.pem" ]; then
  echo "==> A browser window will open — log in to Cloudflare and pick your domain."
  cloudflared tunnel login
fi

PY="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
tunnel_id() {
  cloudflared tunnel list --name "$NAME" -o json 2>/dev/null |
    "$PY" -c 'import json,sys; d=json.load(sys.stdin) or []; print(d[0]["id"] if d else "")'
}
ID="$(tunnel_id)"
if [ -z "$ID" ]; then
  echo "==> Creating tunnel '$NAME'"
  cloudflared tunnel create "$NAME"
  ID="$(tunnel_id)"
fi
[ -n "$ID" ] || { echo "Couldn't find the tunnel ID." >&2; exit 1; }
[ -f "$CF/$ID.json" ] || { echo "Missing $CF/$ID.json — this tunnel was made on another machine. Delete it in Cloudflare or set TUNNEL_NAME to a new name." >&2; exit 1; }

echo "==> Pointing $HOST at the tunnel"
cloudflared tunnel route dns "$NAME" "$HOST" || echo "   (DNS record may already exist — continuing)"

cat > "$CF/samoan.yml" <<EOF
tunnel: $ID
credentials-file: $CF/$ID.json
ingress:
  - hostname: $HOST
    service: http://127.0.0.1:$PORT
  - service: http_status:404
EOF
echo "==> Wrote $CF/samoan.yml"
echo
echo "Test it now (Ctrl+C to stop):  cloudflared tunnel --config $CF/samoan.yml run $NAME"
echo "Then lock it down with Cloudflare Access — see README step 4 — before sharing the link anywhere."
