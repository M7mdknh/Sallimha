# Progress log

Newest first. Status vocabulary: PASS / PASS (SIMULATED) / FAIL / BLOCKED / NOT RUN. Results obtained with the local fake WhatsApp transport are **SIMULATED** and are not real integration evidence.

## 2026-11-18 — Pilot usability (ADR-0013)
Evidence: [evidence/usability-2026-11-18.md](evidence/usability-2026-11-18.md). Nothing deployed; WhatsApp and
location results SIMULATED; Google Maps with a real key BLOCKED (billing approval, decision M1).

- **Review of bc7d8dd:** its CI passed. One finding fixed: `admin_access` refuses to print secrets outside an
  interactive terminal.
- **Dashboards:**
  - Admin: the operation period, four counts, activity by hour from recorded times, team, problems, Add staff.
  - Supervisor: problems first, one queue by longest wait with plate, valet and elapsed time, search and team at hand.
- **No receipt question:** the ticket message's provider status is shown instead. A failure becomes one issue with
  correct-number and resend.
- **Phone entry:** a country selector, with the server as the authority and specific refusals.
- **Plate entry:** Saudi plates kept as entered (verified letter set), other plates as written, an explicit
  no-plate path, search in either script, and possible duplicates flagged.
- **Parking place:** floor, description and an optional confirmed pin with accuracy. Google Maps is lazy-loaded with a
  run-time key, and parking never waits for a position or a map.
- **Intake:** three stages.
- **Tests:** backend 590, retired channel 82, Playwright 41 passed / 0 failed / 11 skipped (full run), then 21 passed
  on the specs touched by the last refinements.

## 2026-11-17 — Pre-staging fixes (ADR-0012)
Evidence: [evidence/pre-staging-2026-11-17.md](evidence/pre-staging-2026-11-17.md). Nothing deployed; WhatsApp
still SIMULATED.

- No admin credential from the app: setup codes for admins refused, the in-app second-factor reset removed, and a
  pending code cancelled when a role change involves ADMIN. Admin access goes through a controlled server procedure
  (`manage.py admin_access`) with a requesting admin and a different approver; the last use shows on the Team page.
- My work is a pure read; the app acknowledges a displayed offer with an explicit, CSRF-protected, idempotent
  command that starts the window once and never past the hard limit.
- docs/06, 07 and 09 brought in line with ADR-0011/0012 (IDs kept; AT-61–AT-72, R-74–R-86 added); A1–A8 with
  recommendations; real-device checklist (NOT RUN).
- Tests: backend 521 passed, retired channel 82 passed. Playwright full run 37 passed, 1 failed, 8 skipped; the
  failure was a race in an old test (it read headings before Operations rendered), fixed with a waiting assertion,
  and that file then passed 10/10. CI runs the full suite on the pushed commit.

## 2026-11-17 — Staff app pilot redesign (ADR-0011)
Branch `build/phase-0-2`. Evidence: [evidence/staff-app-2026-11-17.md](evidence/staff-app-2026-11-17.md). Nothing
deployed; WhatsApp still SIMULATED.

- Customers use WhatsApp only; valets and supervisors use a phone/tablet web app. No staff message is queued and no
  staff token issued (`STAFF_CHANNEL=app`); the retired valet conversation stays behind the flag with its tests.
- Valet app on the existing services: My work (offer with countdown, ready, code, delivered, moves, custody) and a
  six-step Register car flow. Offers start their window when the app shows them; the hard limit still releases them.
- Roles consolidated to VALET, SUPERVISOR, ADMIN by a reversible data migration with an audit record per person.
  Admin onboarding with one-time setup codes; sign-in by mobile number.
- Operations (problems first; waiting / on the way / ready; ticket detail with one primary action), Team (device not
  working, register for that valet; people for admins), Dashboard, Settings with an Advanced section.
- Customer help messages stored and raised to the team; Contact customer reveals the number, audited.
- Tests: backend 503 passed (82 cover the retired channel), Playwright 38 passed / 8 skipped (desktop-only), with 48
  phone/tablet screenshots in Arabic and English.

## 2026-11-16 — Review and staging preparation
Branch `build/phase-0-2`. Findings and fixes: [evidence/review-2026-11-16.md](evidence/review-2026-11-16.md).
Decisions needed: [decisions-needed.md](decisions-needed.md). Nothing deployed; WhatsApp still SIMULATED.

- Review (claims re-verified): idempotency keys bound to the request body; CSRF on sign-in/out; `SALLIMHA_ENV` must be
  explicit; relocation custody rebuilt as offer → acceptance → completion by the mover (ADR-0007); settings saves
  versioned; venue time zone authoritative; flat list queries.
- Outages (ADR-0008): declared WhatsApp outage with relayed actions and intake on behalf; recorded system outage
  with two-person reconciliation (actual vs entry time, evidence, holds respected, no double completion).
- Key rotation (ADR-0009): multi-key encryption and hashing with `rotate_keys`; Django secret-key fallbacks.
- Staging preparation: one Docker image, `deploy_check` release gate, private S3 media, backup/restore scripts with
  a local rehearsal, image smoke test, CI image build.
- Tests: see the final hand-over for the counts on the final commit. Mobile (360 px) now runs every operational flow;
  browser zoom is exercised via Chromium page-zoom emulation and CSS layout zoom.

## 2026-11-16 — Phase 1 finished, contract gap closed, Phase 2 built (Gate 2 and Gate 3 locally)
Branch `build/phase-0-2`. Backend suite: **360 passed**. Playwright: **27 passed, 5 skipped** (desktop 1280 px +
mobile 360 px; skips are desktop-only flows). Nothing deployed; WhatsApp is SIMULATED.

Authentication (the two open findings from the paused session, both **fixed**):
- Login throttling uses atomic upsert counters in PostgreSQL (safe under concurrent requests and across workers):
  per (account, network) pair, per network for spraying, and an account-under-attack tightening that never hard-locks
  the real user from a known network. Generic responses kept. 14 regression tests (concurrency, targeted lockout
  abuse, expiry, success). Later Security Guidance findings fixed test-first: proxy misattribution (HIGH →
  `TRUSTED_PROXY_COUNT` required outside dev), IPv6 /64 bucketing, IPv4-mapped/NAT64/6to4/Teredo unwrapping.
- MFA (TOTP) for manager and above: admin-issued enrolment only (no trust-on-first-use), replay protection,
  lock after five failures, session epoch invalidation on role change, deactivation and re-enrolment.

Phase 1 completion:
- Console UI: login (password → code), live view (attention first, requests, team, shifts), ticket panel with
  exception actions, development simulator; Arabic RTL / English LTR; 360 px layouts; loading, error and stale
  states (stale data disables every action). Brand tokens and fonts as approved.
- Worker restart test (SIGKILL + restart on real PostgreSQL) and Gate 2 evidence: [evidence/gate-2.md](evidence/gate-2.md).
- Simulator and demo seeding cannot run outside local/test: settings refuse `SIMULATOR_ENABLED` and the fake
  transport, `demo_totp` refuses, the simulator routes are not registered, and the console hides the link.

API contract gap: every endpoint has request and response serializers; `contracts/openapi.yaml` is generated with
`--fail-on-warn`, committed and checked for drift in CI; the console's TypeScript types are generated from it and
also drift-checked. Tests assert every route documents its request and 200 response.

Phase 2 (Tasks 2.1–2.7): incidents (supervisor opens/annotates, manager resolves), safety holds, assisted request and
handover, relocation, unclaimed proposal/approval with venue key hooks kept until explicit release, carryover
register, staff directory with bounded role grants and deactivation, MFA issue, configuration (timings, retention,
message wording with reset), retention preview/apply with hold protection, dead letters and unknown-outcome sends
with explicit replay, opening check, outage handling (503 without false success), event create/close, reports and
CSV exports (no phones for managers; audited admin-only phone export; formula-injection guard). Full role-based
console (AT-59) and design QA matrix (AT-53). Evidence: [evidence/gate-3.md](evidence/gate-3.md).
Runbook drafts: [runbooks/](runbooks/README.md). Local demo: README "Local demo".

Limits: real WhatsApp BLOCKED (inputs in [staging-inputs.md](staging-inputs.md)); `FIELD_ENCRYPTION_KEY`/`HASH_KEY`
rotation not supported yet; backup restore not rehearsed (needs hosting); runbook owners not named.

## 2026-11-15 — Phase 1 core slices (Tasks 1.0–1.7)
Branch `build/phase-0-2`. Backend suite: **241 passed** on Django 6.1.3 / PostgreSQL 18.7 (local Docker), plus 4 Playwright brand tests.

Completed:
- Core: phone parsing (Arabic/Persian digits, international), Fernet field encryption, keyed hashes, append-only audit (DB trigger), idempotency, log masking.
- Data model with DB-enforced invariants (ADR-0003): one open shift per person, one live task per valet and per vehicle, one open request per ticket, venue key hooks unique across events, cancellation only before parking starts, same-event composite FKs. Mutation run proved each constraint test fails without its constraint.
- Messaging: signed webhook inbox (two secrets), outbox with leases/backoff/dead letters/replay, DELIVERY_UNKNOWN without blind resend, monotonic statuses, 24 h window selection, worker loop + heartbeat.
- Intake/parking, guest request, dispatch, ready/code/handover, custody transfer, withdrawal (before and after acceptance), phone correction, ratings, alerts.
- Valet and guest WhatsApp conversations (SIMULATED); full journey intake → request → offer → accept → ready → code → delivered → rating passes end to end.

Evidence highlights:
| Scenario | Result |
|---|---|
| AT-08 two dispatchers race | PASS (real concurrent PostgreSQL transactions) |
| AT-09 intake vs retrieval capacity | PASS (real concurrency) |
| AT-10 repeated taps (sequential and concurrent) | PASS / PASS (SIMULATED webhooks) |
| AT-11 accept races expiry | PASS (real concurrency) |
| AT-25 / AT-26 outbox recovery, lost response | PASS (SIMULATED transport) |
| AT-27 out-of-order statuses | PASS (SIMULATED) |
| AT-01–07, 12–19, 23, 32, 35, 37–39, 42, 49, 50, 54–57, 60 | PASS (domain) / PASS (SIMULATED) where WhatsApp is involved |

Findings fixed along the way:
- Race tests found two real deadlocks → canonical lock order ticket → request → task → shift → key → tokens and `FOR NO KEY UPDATE` row locks (ADR-0003 revised).
- Security Guidance commit reviews (LLM review **confirmed running**): 9 MEDIUM findings across masking (exception text, JSON keys, bypasses, linear-time, placeholder injection, colon boundary), short-number phone masking and a shift-start privilege escalation — each fixed with a failing test first.

Blockers / limits:
- Real WhatsApp: BLOCKED (no sender, token or approved templates). Cloud API request builder is contract-tested only.
- Media is stored privately on the local filesystem; S3-compatible storage is a staging item.
- Superpowers 7.0.2 installed but this session still runs 7.0.0 (needs a fresh session); Impeccable hooks still UNVERIFIED.

## 2026-11-15 — Phase 0 foundation
- Approved decisions recorded in docs/01, 02, 04, 06, 07, ADR-0001–0006, docs/11 (WhatsApp platform facts from official docs).
- Compose PostgreSQL 18.7; Django 6.1.3 + DRF 3.18.3 verified (pytest-django 4.14 and drf-spectacular 0.30 work on 6.1.3 despite older classifiers).
- Brand font inheritance fixed (tokens.css v1.0.1) and verified at 360 px and 1280 px in Chromium/Chrome.
- CI (GitHub Actions): backend + web + e2e green on run 43707738541.

## 2026-11-15 — Initial review (no application code)
- Repository was empty apart from the handoff pack; inspection, matrix, ADRs and plan written and approved.

## 2026-11-15 — Session paused (usage limit) — state and remaining work
Done since the last entry: console API (Task 1.8, 256+ tests), login lockout, dev simulator API and synthetic demo seed (Task 1.9 backend). Branch `build/phase-0-2` is pushed.

**Open security findings at that time (Security Guidance review of f58a19b, both MEDIUM) — since fixed, see the 2026-11-16 entry:**
1. Login lockout check-then-insert race lets parallel attempts exceed the 5-failure cap → record the attempt before `authenticate()` and check the count after inserting.
2. The username-only lockout key lets anyone lock out a known user → hard-lock on (IP, user) only; use delays or an IP-only limit for spraying.

**Remaining Phase 1 work (at that time; done since):** Task 1.9 console UI (login, live view, ticket panel, simulator page, Playwright e2e for RTL/360 px/stale banner/simulated full flow); Task 1.10 worker-process restart test and Gate 2 evidence table.
**Phase 2 (not started at that time; built since):** incidents and holds, assisted handover, relocation, unclaimed carryover and key release, MFA and role grants, configuration/retention/dead-letter view/opening check, reports and exports, full role-based console UI, runbook drafts, `make demo` script.
**Not done at that time:** final whole-branch review; Impeccable detector run on the UI.
