# ADR-0003 — Database constraints, scoping and lock order

- Status: **Accepted 2026-11-15**
- Date: 2026-11-15
- Requirement basis: CLAUDE.md non-negotiables; docs/02 database-enforced invariants; docs/03 atomicity. Constraints are the final guard; application checks give friendly errors first.

## Invariants enforced in PostgreSQL
| # | Invariant (plain terms) | Mechanism |
|---|---|---|
| 1 | Display numbers are unique per event and never used for authorization | `UNIQUE (event_id, display_number)` |
| 2 | A person has at most one open shift, across all events | Partial unique index on `shift(staff_id) WHERE ended_at IS NULL` |
| 3 | A valet holds at most one live capacity-consuming task (intake, retrieval, relocation; offers count) | Partial unique index on `task(assignee_id) WHERE status IN ('RESERVED','OFFERED','ACCEPTED')` |
| 4 | A vehicle has at most one live movement task | Partial unique index on `task(ticket_id) WHERE status IN (live)` |
| 5 | A ticket has at most one open retrieval request | Partial unique index on `retrieval_request(ticket_id) WHERE state NOT IN ('COMPLETED','WITHDRAWN')` |
| 6 | A physical (venue-owned) key hook holds at most one unreleased key, across events and carryover, until explicitly released (ADR-0005 C1) | Partial unique index on `key_occupancy(key_station_id, hook_number) WHERE released_at IS NULL` |
| 7 | Each offer generation exists once per request | `UNIQUE (request_id, generation)` |
| 8 | Each inbound provider message or action has exactly one effect | `UNIQUE (provider, provider_message_id)` on inbound operations; status events keyed by `(provider, message_id, status, provider_timestamp)` |
| 9 | Client-retried mutations are applied once | `idempotency_key UNIQUE (actor_id, key)` storing the recorded outcome |
| 10 | Rows that reference an event's objects belong to the same event | `UNIQUE (event_id, id)` on parent tables plus **composite foreign keys** `(event_id, ticket_id) → ticket(event_id, id)`. Django's `ForeignKey` cannot express these and `ForeignObject` creates no DB constraint (Django 6.1 docs), so they are added with reviewed `RunSQL` migrations |
| 11 | States and their required fields agree (e.g., PARKED has location and hook; DELIVERED has verification and actor) | `CHECK` constraints per state |
| 12 | Concurrent edits cannot silently overwrite | `version` column; mutations use `UPDATE … WHERE id=$1 AND version=$2` |
| 13 | Audit rows are application-append-only | The app DB role gets `INSERT, SELECT` only on `audit_event`; `UPDATE/DELETE/TRUNCATE` revoked. Migrations run as a separate owner role. A database superuser still has power (docs/02) |

Database roles: `sallimha_owner` (migrations only), `sallimha_app` (runtime DML; no audit mutation), `sallimha_readonly` (reports and exports).

## Transactions and locking
- Isolation is READ COMMITTED plus explicit locks. Races are proven with real concurrent connections in tests: AT-08, AT-09, AT-11 and AT-32.
- **Per-event dispatch serialization:** `pg_advisory_xact_lock(<event lock key>)` at the start of each dispatch transaction gives predictable FIFO selection. Constraints 3–5 still guard against any bypass.
- **Lock order (all commands):** event advisory lock → retrieval_request → ticket → task → staff/shift → key_occupancy. Commands that don't need a level skip it but never reverse the order.
- Rows are taken with `SELECT … FOR UPDATE` in that order. Worker claims use `SKIP LOCKED` (ADR-0002).
- No network I/O happens while holding these locks.
- Every command rechecks shift, permission, event scope and expected version inside the transaction (CLAUDE.md).

## Scoping
- Every object lookup is filtered by organization and event scope on the server before reading or mutating, including media download and exports (AT-21).
- A shared query helper makes unscoped lookups impossible to call by accident.
- Guest-facing references are high-entropy opaque tokens; the database stores only keyed verifiers.

## Consequences
- Some migrations are hand-written SQL and are reviewed as such.
- Constraint-violation errors are mapped to explicit domain outcomes, never surfaced as 500s.
