# ADR-0001 — Application stack and versions

- Status: **Proposed — awaiting user approval**
- Date: 2026-11-15
- Requirement basis: docs/05 recommends a modular monolith (React + TypeScript, Django + DRF, PostgreSQL, worker, private object storage). That stack is a **proposed default**, not a business requirement. The business requirements it serves are: transactional source of truth, durable background work, Arabic-first responsive console and deterministic dispatch (no LLM in the request path).

## Decision
Adopt the docs/05 stack as one repository using the docs/05 layout (`apps/web`, `services/api`, `contracts`, `infra`, `tests`, `docs`, `brand`).

| Component | Choice | Version evidence (Context7, 15 Nov 2026) |
|---|---|---|
| Python | 3.14 (local 3.14.4) | Django 6.1 supports 3.12–3.15 |
| Web framework | **Django 6.1**, upgrading to the next LTS before 6.1 support ends | 6.1: mainstream support to April 2027, extended to December 2027. LTS releases come every two years at x.2 (5.2 = April 2025), so 6.2 LTS is expected around April 2027. **Confirm on djangoproject.com before relying on it.** |
| API | Django REST Framework 3.18.x | 3.18.3 supports Django 5.2, 6.0, 6.1 and Python 3.10–3.15 |
| Database | **PostgreSQL 18** (managed in staging/production; Compose locally) | 18.7 is current (12 Nov 2026); 19 is only RC2, not GA |
| Console | React 19.x + TypeScript + Vite | Exact versions pinned at scaffold after a Context7 check |
| JS runtime | Node 24 LTS (local 24.18.0) + npm | npm already installed; no extra package manager |
| Python deps | uv (installed) with a lock file | — |
| API contract | OpenAPI generated from DRF; typed client generated into `contracts/` | Generator library chosen and verified at scaffold |
| Tests | pytest + pytest-django against real PostgreSQL; `@playwright/test` for E2E in CI | Real database required by docs/06 |
| Auth | Django session auth, same origin, CSRF; TOTP MFA for manager and above | MFA library chosen and verified in Phase 2 |
| Object storage | Private S3-compatible bucket; local emulator for dev | Emulator chosen at scaffold after checking licence and maintenance |
| Background work | Own worker on PostgreSQL tables (ADR-0002) | No Redis or Celery in V1 |

Alternative considered: **Django 5.2 LTS**, with security support until about April 2028. Safer support window, but it lacks 6.x features. Either version needs one framework upgrade within about 18 months: 6.1 → 6.2 is a small hop, 5.2 → 6.2 is a larger one.

## Rejected
Microservices, Kubernetes, event-stream infrastructure, vector databases, LLM agents in dispatch (docs/05). Also a separate staff app (docs/04).

## Consequences
- One language per tier.
- Domain rules live once in Django services. Web, WhatsApp handlers and workers call the same commands.
- A planned framework upgrade task appears in the Phase 4 checklist.
- No production-only dependency surprises: local Compose mirrors PostgreSQL 18.
