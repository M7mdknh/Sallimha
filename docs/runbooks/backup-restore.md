# Backup restore

**Owner:** on-call technical — _to be named_. Must be rehearsed once on staging before Gate 4.

## What is backed up *(provider)*
- Managed PostgreSQL with point-in-time recovery: all operational data, audit log, outbox and inbox.
- Private media storage (`MEDIA_ROOT_PRIVATE` or the chosen bucket): intake and incident photos.

## Logical backups (in addition to provider point-in-time recovery)
- `DATABASE_URL=… scripts/backup.sh <dir>` writes `db.dump` (PostgreSQL custom format), media (local storage) or a
  note to rely on bucket versioning (S3), and a checksum manifest.
- `DATABASE_URL=<new empty database> scripts/restore.sh <dir>` verifies checksums, restores, and restores local media.
- Rehearsed locally with `scripts/rehearse-restore.sh` (synthetic data): schema current after restore, identical
  row counts, append-only audit trigger present. The provider-level rehearsal is still required before Gate 4.

## Steps
1. Stop the worker and put the web service in maintenance *(provider)*.
2. Restore the database to the chosen point into a **new** instance; restore media to the same point.
3. Point `DATABASE_URL` at the restored instance. Run `python manage.py migrate --check` (must report nothing to
   apply), then `python manage.py deploy_check`.
4. Start the web service, then the worker. Messages that were being sent when the backup was taken come back
   as "Delivery unknown" once their lease expires: handle them in **Operations**, never by bulk resend.
5. Run the opening check for open events. Supervisors reconcile the live view against the physical key board
   before resuming dispatch.

## Data rules
- Retention deletions made after the restore point come back with the restore: re-apply retention afterwards.
- A backup taken before a key rotation needs the old key: put it back in the matching `…_PREVIOUS` variable and run
  `python manage.py rotate_keys --apply` (ADR-0009). Keep retired keys in the secret store while such backups exist.
