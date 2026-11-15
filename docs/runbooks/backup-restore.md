# Backup restore

**Owner:** on-call technical — _to be named_. Must be rehearsed once on staging before Gate 4.

## What is backed up *(provider)*
- Managed PostgreSQL with point-in-time recovery: all operational data, audit log, outbox and inbox.
- Private media storage (`MEDIA_ROOT_PRIVATE` or the chosen bucket): intake and incident photos.

## Steps
1. Stop the worker and put the web service in maintenance *(provider)*.
2. Restore the database to the chosen point into a **new** instance; restore media to the same point.
3. Point `DATABASE_URL` at the restored instance. Run `uv run python manage.py migrate` (a no-op if the schema
   matches).
4. Start the web service, then the worker. Messages that were being sent when the backup was taken come back
   as "Delivery unknown" once their lease expires: handle them in **Operations**, never by bulk resend.
5. Run the opening check for open events. Supervisors reconcile the live view against the physical key board
   before resuming dispatch.

## Data rules
- Retention deletions made after the restore point come back with the restore: re-apply retention afterwards.
