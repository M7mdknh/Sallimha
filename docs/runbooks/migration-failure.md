# Database migration failure

**Owner:** on-call technical — _to be named_.

## Policy
- Migrations run before new code takes traffic (`uv run python manage.py migrate --noinput`).
- PostgreSQL runs each migration in a transaction: a failed migration leaves the schema as it was.
- Migrations are additive first (expand), with removals in a later release (contract), so the previous release
  keeps working against a migrated schema.

## Steps
1. If `migrate` fails, **do not** switch traffic. The current release keeps serving.
2. Read the error. Never use `--fake` to get past it in staging or production.
3. Fix the migration in code, test it against a copy of the data (`makemigrations --check` and the backend suite
   run in CI), and redeploy.
4. If a migration succeeded but the new release misbehaves, follow [rollback.md](rollback.md).

## Signs during an incident
- The console shows "service unavailable" (HTTP 503 with code `service_unavailable`) when the database cannot be
  reached; actions are not half-applied.
