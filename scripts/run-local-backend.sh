#!/usr/bin/env bash
# Local/test only: migrate, seed the synthetic demo, then run the worker and the API together.
# Used by `make demo` and the Playwright suite. Never use for staging or production.
set -euo pipefail
cd "$(dirname "$0")/../services/api"
export SALLIMHA_ENV="${SALLIMHA_ENV:-local}" SIMULATOR_ENABLED=1 WHATSAPP_TRANSPORT=fake
uv run python manage.py migrate --noinput
uv run python manage.py seed_demo --reset ${SEED_ARGS:-}
uv run python manage.py run_worker --poll 0.5 --id local-worker &
WORKER=$!
trap 'kill $WORKER 2>/dev/null || true' EXIT INT TERM
uv run python manage.py runserver 127.0.0.1:8100 --noreload
