# 10 — Phased build plan

Status: **Proposed — awaiting approval.** Milestone-level plan keyed to the docs/06 gates and the CLAUDE.md slice order. A detailed, test-first task plan (Superpowers `writing-plans`) is written at the start of each phase, not now.

## Working method (every phase)
- Small reviewable branches and pull requests. Tests are written first for each command (Superpowers TDD).
- Context7 version check before adding any library.
- Code review before merge. Security Guidance review confirmed in its log for each code commit.
- Playwright E2E for every console change. Impeccable within DESIGN.md for UI.
- `docs/PROGRESS.md` updated per change.
- Gate evidence uses docs/06 format: PASS / FAIL / BLOCKED / NOT RUN, with build ID, environment and evidence path. Mocked WhatsApp is labelled *mocked*. An unconfigured provider is reported **BLOCKED**, never PASS.

## Phase 0 — Foundation and verification
**Precondition:** this review approved. That includes the brand, ADR-0001–0006 and the C4 cancellation cutoff.

**Work:**
- Commit the supplied pack as the baseline. Use a working branch.
- Repository skeleton per docs/05: `.gitignore`, `.env.example` (names only), Compose with PostgreSQL 18 and a storage emulator, Django 6.1 + DRF project, Vite + React + TypeScript app shell with brand tokens (no screens yet), uv and npm lock files.
- CI on GitHub Actions: lint, typecheck, pytest against a PostgreSQL 18 service, Playwright smoke.
- **WhatsApp platform spike** (documentation, plus the test number if available): button payloads, service windows, template categories and cost, sender identity, status webhooks. Results update ADR-0002 and ADR-0006 before templates are drafted for submission.
- **Tool proofs:**
  - Security Guidance LLM review runs on the first code commit; log line recorded.
  - Impeccable hooks fire in a fresh session.
  - Superpowers 7.0.2 is loaded.

**Exit:** CI green on the skeleton, tool proofs recorded, spike findings recorded.

## Phase 1 — Core vertical slices → **Gate 2 (core correctness)**
Slices in CLAUDE.md order. Each slice is domain command → database constraints → WhatsApp handler (fake adapter, mocked) → worker → tests.

| Slice | Content | Key tests |
|---|---|---|
| 1.0 Spine | Organization, venue, key stations, event, staff, roles, shifts, event scoping, audit, idempotency, inbox/outbox and worker loop | AT-42, AT-48 (DB part), AT-49, AT-50 (mock), AT-25, AT-26 |
| 1.1 Registration | “مركبة جديدة”, phone normalization and confirmation, ticket send, receipt confirmation, vehicle identity | AT-01, AT-02, AT-35, AT-38 |
| 1.2 Parking | Intake photos (private storage), location, key hook, PARKED, intake custody transfer | AT-03, AT-33 (collision), AT-37 |
| 1.3 Guest request | Opaque actions, one request, early request, multi-ticket selection, correction | AT-04, AT-10, AT-16, AT-17, AT-18 |
| 1.4 Atomic dispatch and custody | Queue order, affinity, longest-idle, per-event lock, offers, expiry, cooldown, alerts, acceptance races, availability and breaks. Plus `transfer_custody` for **accepted** work: establish key and car location, revoke old action authority, new valet acknowledges. Used by accepted-valet-offline, break, shift-end and deactivation exceptions | AT-05–09, AT-11–14, AT-19, AT-32, AT-39 |
| 1.5 Ready → verified handover → rating | READY, code, attempt limit, delivery, release, ratings | AT-15, AT-23 |
| 1.6 Minimal supervisor live view | Brand-approved, event-scoped live requests and attention list; stale banner | AT-34, AT-53 (subset) |

**Exit, Gate 2 (extended set, also stated in `09_Traceability_Matrix.md`):** the following pass against real PostgreSQL and a real worker process, with WhatsApp mocked and labelled. Failures are fixed before scope expands.
- docs/06 Gate 2 scenarios: AT-01–19, AT-32–34.
- Phase 1 additions: AT-25, AT-26, AT-35, AT-37, AT-38, AT-39, AT-42, AT-48 (database-role part), AT-49, AT-50 (mocked), and AT-53 limited to the live view.

## Phase 2 — Operational completeness → **Gate 3**
**Work:**
- Incidents and safety holds; assisted handover; withdrawal; cancellation and unclaimed carryover.
- Relocation.
- Full role-based console (supervisor, manager, admin, super admin), MFA, role grants, exports, reports and working hours.
- Configuration with audited timings and templates.
- Retention jobs with holds.
- Dead-letter operations view.
- Outage and database-failure behaviour.
- Opening health check.

**Tests:** AT-20–24, AT-27, AT-29–31, AT-36, AT-40, AT-41, AT-43–47, AT-51, AT-52, AT-54, full AT-53.

**Exit, Gate 3:** all of the above pass. Draft runbooks exist for the 13 docs/05 situations.

## Phase 3 — Staging → **Gate 4**
**Needs:** hosting choice, WhatsApp test sender and template approvals.

**Work:**
- Provision staging per ADR-0004.
- Configure the official sender, signed webhook and approved templates.
- Exercise real messages: delivery failures, window expiry (AT-28 real), webhook signature (AT-50 real).
- Browser QA in Arabic and English at 360 px, tablet and desktop.
- Security review.
- Load scenario LOAD-01 with hardware and version reported.
- Backup restore into an isolated environment (REC-01).

**Exit, Gate 4:** STG-01, LOAD-01 and REC-01 evidence recorded.

## Phase 4 — Production readiness → **Gate 5**
**Needs:** provider, region and data-location decision, domain, owners and retention policy.

**Work:**
- Production environment and managed secrets.
- Restore drill and rollback rehearsal (REC-02).
- Final runbooks with named business and on-call owners.
- Critical and high findings resolved or formally assessed.
- Django upgrade to the next LTS scheduled, per ADR-0001.

## Phase 5 — Release → **Gate 6**
Deploy the exact staging-tested image. Run health and readiness checks, then the designated production smoke test (PROD-01). Report the version, time and remaining limitations. Deployment is not claimed until both pass.

## What can proceed without external inputs
Phases 0–2 need **no** external credentials. WhatsApp is mocked and labelled, everything runs on local PostgreSQL, and the venue layout stays configurable.

Phase 3 onward is BLOCKED on the inputs listed in the readiness report.
