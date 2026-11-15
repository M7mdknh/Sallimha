# 05 — Proposed architecture and deployment plan

## Status
This is a recommended starting architecture, not an audit of existing code and not a hosting commitment. If real source appears, first assess it against the requirements and prefer a safe incremental improvement where viable. Record version choices in an ADR after checking current supported releases.

## Recommended shape: modular monolith
| Layer | Proposed choice | Rationale |
|---|---|---|
| Web console | React + TypeScript, responsive Arabic-first UI | Operational views, accessible forms, shared typed contracts |
| HTTP/API/domain | Django + Django REST Framework | Explicit domain services, mature authentication/ORM/migrations; custom role checks still required |
| Durable data | PostgreSQL | Transactions, constraints, row locking and auditable state |
| Background processing | Worker from same application codebase; database inbox/outbox + scheduled reconciliation | Recoverable messages, offers and timeouts |
| Queue | Decide in ADR: database-backed jobs initially; add Redis/Celery only if warranted | Keep source of truth in PostgreSQL regardless of wakeup transport |
| Media | Private S3-compatible object storage | Durable evidence independent of container filesystem |
| WhatsApp | Official Business Platform adapter | Separate provider payloads from business rules |
| Runtime | Containers, same-origin HTTPS reverse proxy | Repeatable web/API/worker deployment |
| Delivery | GitHub Actions with staging and production promotion | Test exact release, migrations, smoke checks and rollback |

This selection is based on project needs and maintainability, not a requirement that the old system used this stack. Do not add Kubernetes, microservices, vector databases, RAG, autonomous dispatch agents or event-stream infrastructure without a demonstrated need.

## Domain modules
Identity and access; venues/events/shifts; intake/tickets/media; task dispatch; guest contact/messaging; incidents/custody; ratings/reports; configuration/audit. All channels call the same domain commands. Web UI, WhatsApp handlers and workers cannot each implement their own version of a ticket transition.

Proposed command contracts: register_vehicle, confirm_guest_contact, attach_intake_media, complete_parking, request_retrieval, offer_task, accept_task, expire_offer, mark_ready, verify_collection, complete_handover, report_incident, resolve_incident, transfer_custody and end_shift. Each command validates actor/scope/current version and returns an explicit outcome. Read-only queries never trigger operational side effects.

## Suggested repository layout
```
apps/web/                # responsive console
services/api/            # API, domain modules and worker entrypoints
contracts/              # API schema and generated client types
infra/                  # container and deployment configuration
tests/                  # integration, concurrency, provider contract and e2e tests
docs/                   # this specification, ADRs and operational runbooks
brand/                  # assets and tokens
```

Use a conventional Django admin only as a tightly restricted engineering/admin aid, not a replacement for the operational supervisor experience. No unrestricted model editor that bypasses domain state rules.

## Security and data handling
- Same-origin web/API cookies with secure attributes and CSRF protection; no privileged credential stored in frontend bundles. MFA for manager/admin/super-admin as proposed default.
- Hash console passwords with a supported framework password hasher. Rate-limit login, account recovery, collection verification and guest actions.
- Authorize object access against organization/event scope before reading or changing records, including media download and report export.
- Encrypt transport; use managed secrets and encrypted storage. Mask phones by default. Do not log codes, tokens or raw provider secrets.
- Validate webhook signatures over the raw payload using current provider documentation. Store receipt and process asynchronously.
- Private media with short-lived authorized links, file type/size validation and retention metadata. Public evidence URLs are forbidden.
- Keep original photo evidence and controlled derivatives. Export datasets separately from media, with manifest and access control; CSV must not leak guest phones to manager roles.
- Application-append-only audit, restricted database roles, regular protected audit export. A database superuser remains powerful; avoid absolute “uneditable by anyone” claims.

## Retention
Original system default was zero = never delete. Preserve that meaning in configuration, show it explicitly, and require an operational owner to choose retention before launch. No legal retention duration is invented here.

Separate periods for guest contact, intake photos and resolved incident evidence. Put open disputes/custody cases under an explicit hold. Use a documented deletion job with previews, audit, backup interaction and authorization. Audit minimization must avoid embedding permanent copies of contact data in immutable logs.

## Hosting requirements
Select a provider/region only after confirming budget, data-location requirements, existing accounts and scale. The production topology must support a continuously running worker, reliable HTTPS webhooks, managed PostgreSQL backups, private persistent media and restricted operational access. A static frontend deployment alone does not satisfy this topology.

Minimum deployment environments: local development, isolated staging with test credentials, and production with separate secrets/data. Put console/API behind the same origin where practical. No production guest data in automated tests.

## Release sequence
1. Provision staging, database, private media and a real worker. Document exact environment variables without secret values.
2. Run migrations once as a controlled release job, not concurrently on every replica.
3. Verify liveness plus readiness for database, worker heartbeat and required storage. Report WhatsApp degradation separately where it should not make all read-only console functions unavailable.
4. Configure official WhatsApp sender, signed webhook endpoint and approved message templates; exercise real test messages and delivery failures.
5. Run acceptance, security and load checks. Restore a backup into an isolated environment and verify representative tickets/media references.
6. Promote the tested immutable build to production with a migration/rollback plan. Prefer additive database changes and backward-compatible rollout.
7. Run a production smoke test using designated test staff and tickets. Check guest message, offer acceptance, ready, handover and audit.
8. Observe worker lag/errors; retain a tested rollback artifact. A rollback must not erase accepted tasks or remove schema needed by in-flight work.

## Proposed performance/recovery targets
Treat these as pilot test targets, not a service promise: first-party API p95 < 500 ms under declared representative load; queue wakeup to committed offer p95 < 2 s when staff are available; console update within 5 s; RPO ≤ 15 min and RTO ≤ 60 min for disaster recovery. Provider message latency is measured separately.

Proposed initial load scenario: 10 simultaneous events, 100 active staff, 1,000 open vehicle tickets and 100 retrieval requests arriving over 60 seconds. Confirm actual peak volume before sizing. Test queue drain, fairness and database contention; report hardware, version and conditions. An internal duplicate-effect tolerance of zero is a correctness requirement, not merely a performance target.

## Operational runbooks required before launch
WhatsApp outage; invalid phone correction; dead-letter replay; stuck accepted task; missing key/car; identity dispute; unclaimed custody; account compromise; backup restore; database migration failure; rollback; retention deletion; secret rotation. Name the business owner and on-call technical owner before production.

