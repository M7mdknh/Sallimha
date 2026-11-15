# ADR-0004 — Deployment topology (provider-neutral)

- Status: **Proposed — awaiting user approval. Provider and region selection BLOCKED on inputs.**
- Date: 2026-11-15
- Requirement basis: docs/05 hosting requirements and release sequence; CLAUDE.md delivery rules.

## Decision
| Component | Requirement |
|---|---|
| HTTPS entry | Managed TLS and a reverse proxy. Console and `/api` on the **same origin**. Public webhook path for the WhatsApp provider |
| Web console | Static build served by the proxy or the API container from the same origin |
| API | One immutable container image, at least 2 replicas in production |
| Worker | **Same image**, run command `run_worker`. Continuously running (not request-triggered or serverless). At least 1 replica; more are safe (ADR-0002) |
| Database | Managed PostgreSQL 18 with automated backups and point-in-time recovery sized for RPO ≤ 15 min (target). Separate instances for staging and production |
| Media | Private S3-compatible bucket per environment. Short-lived authorized links only; no public URLs |
| Secrets | Provider secret manager. `.env.example` documents names only |
| Observability | Structured logs with masking, metrics (queue age, worker heartbeat, inbox lag, failed messages, DB errors), alerts, external uptime check |
| Migrations | A one-off release job before rolling out new replicas. Changes are expand/contract and backward-compatible |
| Health | `/healthz` (process alive); `/readyz` (DB, worker heartbeat, storage). WhatsApp health is reported separately so read-only console functions survive a provider outage |

## Environments
- **Local:** Docker Compose with PostgreSQL 18, an object-storage emulator and a fake WhatsApp adapter, clearly labelled mocked.
- **Staging:** isolated, with test WhatsApp sender and credentials and synthetic data only.
- **Production:** separate secrets and data; designated test staff and tickets for smoke tests.

## Delivery
GitHub Actions run lint, unit and integration tests on real PostgreSQL, worker recovery tests and Playwright E2E. The pipeline then builds an image tagged with the git SHA, deploys to staging and runs acceptance and smoke checks. Promotion of the same image to production is manual, followed by a production smoke test. Rollback redeploys the previous image; migrations stay compatible with the previous release, so accepted tasks and in-flight schema are never lost.

## Blocked inputs (not decided here)
- **Hosting provider, account and budget.**
- **Region and data location.** Guest phone numbers and vehicle photos are personal data. Saudi data-protection rules may constrain where they are stored or transferred. **A legal/business owner must decide.** This ADR makes no legal determination.
- **Domain and DNS.**
- **Monitoring and on-call ownership.**

## Rejected
Static-only hosting (no persistent worker), per-request serverless workers, Kubernetes for V1.

## Consequences
The topology fits any provider that offers containers, a long-running process, managed PostgreSQL with PITR and private object storage. Selection happens at Gate 5 inputs, without redesign.
