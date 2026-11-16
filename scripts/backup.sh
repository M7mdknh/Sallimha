#!/usr/bin/env bash
# Logical backup: PostgreSQL (custom format) + private media + a manifest with checksums.
#   DATABASE_URL=... scripts/backup.sh <output-dir>
# Complements, never replaces, the provider's point-in-time recovery (docs/runbooks/backup-restore.md).
# PG_DUMP may be overridden (e.g. "docker compose exec -T db pg_dump" for the local rehearsal).
set -euo pipefail
OUT="${1:?usage: scripts/backup.sh <output-dir>}"
: "${DATABASE_URL:?DATABASE_URL is required}"
PG_DUMP="${PG_DUMP:-pg_dump}"
mkdir -p "$OUT"
$PG_DUMP --format=custom --no-owner --no-acl --dbname="$DATABASE_URL" > "$OUT/db.dump"
case "${MEDIA_STORAGE:-local}" in
  local) tar -C "${MEDIA_ROOT_PRIVATE:-var/media}" -czf "$OUT/media.tar.gz" . 2>/dev/null || tar -czf "$OUT/media.tar.gz" -T /dev/null ;;
  s3) echo "media: bucket ${MEDIA_S3_BUCKET:-?} is backed up by provider versioning/replication (not copied here)" > "$OUT/media.txt" ;;
esac
( cd "$OUT" && sha256sum db.dump media.* > MANIFEST.sha256 && date -u +"created %Y-%m-%dT%H:%M:%SZ" >> MANIFEST.sha256 )
echo "backup written to $OUT"
