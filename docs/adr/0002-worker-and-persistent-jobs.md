# ADR-0002 — Worker design and persistent jobs

- Status: **Proposed — awaiting user approval**
- Date: 2026-11-15
- Requirement basis: CLAUDE.md (no in-memory-only locks or timers; durable outbox; authenticated, deduplicated webhooks), docs/03 (durable messaging, recovery from stored deadlines, no external calls under long-lived locks).

## Decision
A single worker process type from the API codebase (`manage.py run_worker`) drives all background work **from domain tables in PostgreSQL**. No separate broker holds state.

Work sources, all durable rows:
| Source | Due when | Effect |
|---|---|---|
| `webhook_inbox` | `status=received` | Parse, deduplicate, call the domain command, mark processed |
| `message_outbox` | `status in (pending, retry)` and `next_attempt_at <= now()` | Send through the WhatsApp adapter; record the outcome |
| Offer and reservation deadlines (`assignment_attempt.deadline`, `task.reservation_expires_at`) | Deadline passed | `expire_offer`, release capacity, requeue |
| Dispatch queue per event | A request is eligible and capacity may exist | `offer_task` under the per-event lock (ADR-0003) |
| Alert thresholds (docs/03 table) | Elapsed time past threshold | Create a supervisor alert once (idempotent key) |
| Scheduled maintenance | Cron-like rows (reconciliation, retention preview, heartbeat) | Run under a leader advisory lock |

Mechanics:
1. **Claiming.** `SELECT … FOR UPDATE SKIP LOCKED LIMIT n` on due rows inside a short transaction. Set `status=in_progress`, `lease_until=now()+lease` and commit. Multiple worker replicas are therefore safe.
2. **External calls happen outside transactions.** Claim → commit → call the provider → record the result in a new transaction. If the response is lost after the provider may have accepted the send, record `DELIVERY_UNKNOWN` and never blindly resend (docs/03, AT-26).
3. **Waking up.** Committing transactions emit `pg_notify` as a *hint*. Notifications are lost if no listener is connected, so the worker also polls due rows every ~1 s. A reconciliation scan (~30 s) repairs anything missed. **Correctness never depends on NOTIFY.**
4. **Crash recovery.** Expired leases return rows to due status. Restarting rebuilds all due work from stored deadlines (AT-25).
5. **Retries.** Bounded exponential backoff with retryable/permanent classification. After the limit, `dead` status appears in an operator view with an idempotent replay (AT-51).
6. **Heartbeat.** The worker updates `worker_heartbeat` each loop. Readiness and the opening check fail if it goes stale (AT-44).
7. **Transactional outbox.** Every business command that must notify someone inserts its outbox row in the same transaction as the state change.

## Platform facts to verify in Phase 0 (official Meta documentation; do not assume)
- Whether template quick-reply buttons accept a per-send payload. If not, bind actions via the replied-to message ID (`context.id`) plus a server-side lookup.
- Whether a guest's button tap opens the customer-service window (affects ADR-0005 C7).
- Template category, cost and latency for valet offers sent outside a window.
- Sender identity fields (phone vs. business-scoped user IDs), and how status webhooks identify the message and transition.

## Alternatives considered
- **Celery + Redis.** Adds infrastructure, and the broker is not the source of truth. Revisit only with measured need (docs/05).
- **Django built-in Tasks (6.x).** Ships only immediate and dummy backends, so production needs a third-party backend. Revisit later for non-critical jobs.
- **Procrastinate (PostgreSQL-based queue).** Viable, but generic job rows would duplicate our domain deadline rows. Revisit if the worker grows beyond these sources.

## Consequences
We own about one module of worker code and must prove it: kill/restart tests, lease expiry, duplicate webhooks, lost responses and dead-letter replay all run against real PostgreSQL in CI.
