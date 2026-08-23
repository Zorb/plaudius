#!/usr/bin/env bash
# Deploy plaudius to the VM. Run from anywhere: bash deploy/deploy.sh [user@host]
set -euo pipefail

HOST="${1:-__DEPLOY_USER__@__TAILNET_IP__}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "== syncing $SRC -> $HOST:~/plaudius"
tar -C "$SRC" \
    --exclude .git --exclude .venv --exclude data --exclude plan \
    --exclude __pycache__ --exclude .pytest_cache --exclude .env \
    -czf - . | ssh "$HOST" 'mkdir -p ~/plaudius && tar -xzf - -C ~/plaudius'

ssh "$HOST" 'bash -s' <<'EOF'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

cd ~/plaudius
uv sync --frozen --no-dev

if [ ! -f .env ]; then
    cp env.example .env
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^PLAUDIUS_TOKEN=.*/PLAUDIUS_TOKEN=$TOKEN/" .env
    chmod 600 .env
    echo "NOTE: created ~/plaudius/.env with a fresh PLAUDIUS_TOKEN; fill in the API keys."
fi

sudo -n systemctl link /home/__DEPLOY_USER__/plaudius/deploy/plaudius.service 2>/dev/null || true
sudo -n systemctl daemon-reload
sudo -n systemctl enable plaudius >/dev/null
sudo -n systemctl restart plaudius
sleep 2
sudo -n systemctl --no-pager status plaudius | head -5
EOF
