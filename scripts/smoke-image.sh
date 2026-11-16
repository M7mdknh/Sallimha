#!/usr/bin/env bash
# Local smoke test of the deployable image with staging settings and PLACEHOLDER secrets (never real ones).
# Uses the local Docker PostgreSQL (make db). Checks: migrations as a release job, health, console and assets on one
# origin, the worker process, and that deploy_check refuses exactly what is still missing locally.
set -euo pipefail
IMAGE="${IMAGE:-sallimha:local}"
DB="sallimha_smoke"
docker compose exec -T db psql -U sallimha -d sallimha -qc "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB" >/dev/null
ENV=(-e SALLIMHA_ENV=staging -e DATABASE_URL="postgres://sallimha:sallimha-local-only@127.0.0.1:55432/$DB"
     -e DJANGO_SECRET_KEY="smoke-placeholder-$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9)-not-a-real-key"
     -e FIELD_ENCRYPTION_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
     -e HASH_KEY="smoke-placeholder-hash-key-$(head -c 16 /dev/urandom | base64 | tr -dc A-Za-z0-9)"
     -e WHATSAPP_APP_SECRET=placeholder -e TRUSTED_PROXY_COUNT=1
     -e DJANGO_ALLOWED_HOSTS=staging.sallimha.test -e DJANGO_CSRF_TRUSTED_ORIGINS=https://staging.sallimha.test)
cleanup() { docker rm -f sallimha-smoke-web sallimha-smoke-worker >/dev/null 2>&1 || true; }
trap cleanup EXIT
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; exit 1; }

docker run --rm --network host "${ENV[@]}" "$IMAGE" python manage.py migrate --noinput >/dev/null && pass "release job: migrate"
docker run -d --name sallimha-smoke-worker --network host "${ENV[@]}" "$IMAGE" python manage.py run_worker >/dev/null
docker run -d --name sallimha-smoke-web --network host "${ENV[@]}" "$IMAGE" \
  gunicorn sallimha.wsgi:application --bind 127.0.0.1:8188 --workers 2 >/dev/null
for _ in $(seq 1 40); do curl -sf -H "Host: staging.sallimha.test" http://127.0.0.1:8188/healthz >/dev/null && break; sleep 1; done
H=(-H "Host: staging.sallimha.test" -H "X-Forwarded-Proto: https" -H "X-Forwarded-For: 203.0.113.9")
curl -sf "${H[@]}" http://127.0.0.1:8188/healthz >/dev/null && pass "healthz" || fail "healthz"
sleep 3
curl -sf "${H[@]}" http://127.0.0.1:8188/readyz | grep -q '"worker": "ok"' && pass "readyz: database and worker" || fail "readyz"
curl -sf "${H[@]}" http://127.0.0.1:8188/events/1 | grep -q '<div id="root">' && pass "console at a client route" || fail "console"
asset=$(curl -sf "${H[@]}" http://127.0.0.1:8188/ | grep -o '/assets/[^"]*\.js' | head -1)
curl -sf "${H[@]}" "http://127.0.0.1:8188$asset" -o /dev/null && pass "built asset $asset" || fail "asset"
curl -sf "${H[@]}" http://127.0.0.1:8188/brand/tokens.css -o /dev/null && pass "brand tokens" || fail "brand"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: staging.sallimha.test" http://127.0.0.1:8188/login)
[ "$code" = "301" ] && pass "plain HTTP redirected to HTTPS" || fail "https redirect ($code)"
code=$(curl -s -o /dev/null -w "%{http_code}" "${H[@]}" http://127.0.0.1:8188/api/dev/sim/phones)
[ "$code" = "404" ] && pass "simulator absent in staging" || fail "simulator reachable ($code)"
set +e
report=$(docker run --rm --network host "${ENV[@]}" "$IMAGE" python manage.py deploy_check --allow-blocked 2>&1)
status=$?
set -e
echo "$report" | sed 's/^/    /'
if [ $status -ne 0 ] && echo "$report" | grep -q "FAIL media" && ! echo "$report" | grep -v "FAIL media" | grep -q "^FAIL"; then
  pass "deploy_check refuses only for local media (no bucket here); WhatsApp BLOCKED"
else
  fail "deploy_check result unexpected"
fi
docker compose exec -T db psql -U sallimha -d sallimha -qc "DROP DATABASE IF EXISTS $DB" >/dev/null 2>&1 || true
