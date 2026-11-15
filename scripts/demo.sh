#!/usr/bin/env bash
# Local demo: PostgreSQL in Docker, synthetic data, API + worker, and the console at http://127.0.0.1:5180.
# WhatsApp is SIMULATED (fake transport + simulator page). Local only — never staging or production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose up -d --wait db
(cd services/api && uv sync --frozen)
(cd apps/web && npm ci --no-fund --no-audit && npm run build)
export DATABASE_URL="${DATABASE_URL:-postgres://sallimha:sallimha-local-only@127.0.0.1:55432/sallimha}"
SEED_ARGS="${SEED_ARGS:---with-activity}" scripts/run-local-backend.sh &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null || true' EXIT INT TERM
until curl -sf http://127.0.0.1:8100/readyz >/dev/null; do sleep 1; done
cat <<'MSG'

  Sallimha local demo is running (WhatsApp is SIMULATED).
  Console:   http://127.0.0.1:5180
  Accounts:  see README "Local demo" (synthetic, local-only)
  Stop:      Ctrl+C

MSG
cd apps/web && npm run preview
