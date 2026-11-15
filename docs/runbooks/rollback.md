# Release rollback

**Owner:** on-call technical — _to be named_.

## Steps *(provider)*
1. Redeploy the previous release (web and worker together; they share the same code version).
2. Keep the database as it is: migrations are additive, so the previous release works with the newer schema.
   Do not reverse migrations during an event.
3. Check `/readyz`, the worker heartbeat in the live view and the opening check.
4. Review **Operations** for messages that failed during the bad release.

## When not to roll back
- If the new release included a data migration that the previous code cannot read, fix forward instead. Each
  pull request states whether it is safe to roll back.
