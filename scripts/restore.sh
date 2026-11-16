#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into an EMPTY database, then check the schema is current.
#   DATABASE_URL=<new empty database> scripts/restore.sh <backup-dir>
# Never restore over the live database: restore into a new one and switch DATABASE_URL (runbook).
set -euo pipefail
IN="${1:?usage: scripts/restore.sh <backup-dir>}"
: "${DATABASE_URL:?DATABASE_URL (the new, empty target) is required}"
PG_RESTORE="${PG_RESTORE:-pg_restore}"
( cd "$IN" && grep -v '^created' MANIFEST.sha256 | sha256sum --check --quiet ) || { echo "checksum mismatch"; exit 1; }
$PG_RESTORE --no-owner --no-acl --exit-on-error --dbname="$DATABASE_URL" < "$IN/db.dump"
if [ -f "$IN/media.tar.gz" ] && [ "${MEDIA_STORAGE:-local}" = "local" ]; then
  mkdir -p "${MEDIA_ROOT_PRIVATE:-var/media}" && tar -C "${MEDIA_ROOT_PRIVATE:-var/media}" -xzf "$IN/media.tar.gz"
fi
echo "restored $IN"
