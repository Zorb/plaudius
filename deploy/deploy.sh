#!/usr/bin/env bash
# Deploy plaudius. Target comes from arg or deploy/local.conf (gitignored):
#   bash deploy/deploy.sh [user@tailscale-ip]
# Host-specific values never live in the repo: __DEPLOY_USER__/__TAILNET_IP__
# tokens in the systemd unit and compose files are rendered on the VM below.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$SRC/deploy/local.conf" ] && . "$SRC/deploy/local.conf"
HOST="${1:-${DEPLOY_HOST:-}}"
if [ -z "$HOST" ]; then
    echo "usage: bash deploy/deploy.sh user@tailscale-ip   (or set DEPLOY_HOST in deploy/local.conf)" >&2
    exit 1
fi
DEPLOY_USER="${HOST%@*}"
TAILNET_IP="${HOST#*@}"

echo "== syncing $SRC -> $HOST:~/plaudius"
tar -C "$SRC" \
    --exclude .git --exclude .venv --exclude data --exclude plan \
    --exclude __pycache__ --exclude .pytest_cache --exclude .env \
    --exclude .claude --exclude CLAUDE.md --exclude local.conf \
    -czf - . | ssh "$HOST" 'mkdir -p ~/plaudius && tar -xzf - -C ~/plaudius'

ssh "$HOST" "DEPLOY_USER='$DEPLOY_USER' TAILNET_IP='$TAILNET_IP' bash -s" <<'EOF'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

cd "$HOME/plaudius"
# Render host-specific values into the shipped templates
sed -i "s|__DEPLOY_USER__|$DEPLOY_USER|g; s|__TAILNET_IP__|$TAILNET_IP|g" \
    deploy/plaudius.service deploy/obsidian-sync/compose.yaml deploy/ntfy/compose.yaml

uv sync --frozen --no-dev

if [ ! -f .env ]; then
    cp env.example .env
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^PLAUDIUS_TOKEN=.*/PLAUDIUS_TOKEN=$TOKEN/" .env
    chmod 600 .env
    echo "NOTE: created ~/plaudius/.env with a fresh PLAUDIUS_TOKEN; fill in the API keys."
fi

sudo -n systemctl link "$HOME/plaudius/deploy/plaudius.service" 2>/dev/null || true
sudo -n systemctl daemon-reload
sudo -n systemctl enable plaudius >/dev/null
sudo -n systemctl restart plaudius
sleep 2
sudo -n systemctl --no-pager status plaudius | head -5
EOF
