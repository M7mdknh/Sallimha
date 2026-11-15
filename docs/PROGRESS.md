# Progress log

Newest first. Status vocabulary: PASS / PASS (SIMULATED) / FAIL / BLOCKED / NOT RUN. Results obtained with the local fake WhatsApp transport are **SIMULATED** and are not real integration evidence.

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
