#!/usr/bin/env bash
# Local backup/restore rehearsal on Docker PostgreSQL with synthetic data. Proves: dump and restore round-trip,
# checksums, current schema after restore (migrate --check), identical row counts, and that the append-only audit
# trigger survives the restore. Provider point-in-time recovery stays BLOCKED until a host exists.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=sallimha_rehearsal_src DST=sallimha_rehearsal_dst BK="$(mktemp -d)"
PSQL=(docker compose exec -T db psql -U sallimha -v ON_ERROR_STOP=1 -qtA)
"${PSQL[@]}" -d sallimha -c "DROP DATABASE IF EXISTS $SRC" -c "DROP DATABASE IF EXISTS $DST" \
  -c "CREATE DATABASE $SRC" -c "CREATE DATABASE $DST" >/dev/null
URL=postgres://sallimha:sallimha-local-only@127.0.0.1:55432
( cd services/api && export SALLIMHA_ENV=local DATABASE_URL=$URL/$SRC MEDIA_ROOT_PRIVATE="$BK/media-src"
  uv run python manage.py migrate --noinput >/dev/null && uv run python manage.py seed_demo --with-activity >/dev/null )
echo "PASS synthetic source database seeded"
DATABASE_URL="postgres://sallimha:sallimha-local-only@127.0.0.1:5432/$SRC" PG_DUMP="docker compose exec -T db pg_dump" \
  MEDIA_ROOT_PRIVATE="$BK/media-src" scripts/backup.sh "$BK/backup" >/dev/null
echo "PASS backup with checksums ($(du -h "$BK/backup/db.dump" | cut -f1))"
DATABASE_URL="postgres://sallimha:sallimha-local-only@127.0.0.1:5432/$DST" PG_RESTORE="docker compose exec -T db pg_restore -U sallimha" \
  MEDIA_ROOT_PRIVATE="$BK/media-dst" scripts/restore.sh "$BK/backup" >/dev/null
echo "PASS restore into an empty database"
( cd services/api && SALLIMHA_ENV=local DATABASE_URL=$URL/$DST uv run python manage.py migrate --check >/dev/null )
echo "PASS schema current after restore (migrate --check)"
for t in ops_ticket ops_keyoccupancy ops_staff messaging_messageoutbox core_auditevent ops_retrievalrequest; do
  a=$("${PSQL[@]}" -d $SRC -c "SELECT count(*) FROM $t"); b=$("${PSQL[@]}" -d $DST -c "SELECT count(*) FROM $t")
  [ "$a" = "$b" ] && echo "PASS $t rows $a = $b" || { echo "FAIL $t rows $a != $b"; exit 1; }
done
if "${PSQL[@]}" -d $DST -c "UPDATE core_auditevent SET action = action" >/dev/null 2>&1; then
  echo "FAIL audit trigger missing after restore"; exit 1
else
  echo "PASS append-only audit trigger present after restore"
fi
"${PSQL[@]}" -d sallimha -c "DROP DATABASE $SRC" -c "DROP DATABASE $DST" >/dev/null
rm -rf "$BK"
