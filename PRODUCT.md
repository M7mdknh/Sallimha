# Product

<!-- impeccable:product-schema 1 -->

Source: compiled on 15 Nov 2026 from the user-approved handoff pack (`docs/01`–`07`, `CLAUDE.md`, `DESIGN.md`) and the user's decisions recorded in ADR-0005/0006. No separate interview was held; every line below traces to those documents. Items marked *(open)* are undecided.

## Platform

web

## Users
- **Valets** (primary operators of the service) work on foot at a venue entrance and car park, phone in hand, during an event shift. They register cars, park them and bring them back. They use **WhatsApp only**; they have no console access.
- **Supervisors** run one event at a time from a phone or tablet (and sometimes a laptop) under venue lighting. Their job is live monitoring, shift operations and exception handling: unaccepted offers, late requests, guests who did not receive their ticket, code lockouts, incidents and custody problems. They do **not** dispatch routine work.
- **Managers** set up events and teams, review reports and close incidents. **Admins** configure timings, message copy, retention and restricted exports. **Super admins** control the WhatsApp connection.
- **Guests** give a phone number at the counter, receive a WhatsApp ticket, request their car and collect it with a code. No app, account or QR scan.

## Product Purpose
Make vehicle intake, parking, retrieval and handover traceable without paper tickets, with an automatic, fair assignment of retrieval work and a truthful status at every stage. Success: every car has an accountable owner at every moment, guests are never told something untrue (for example "being retrieved" while only queued), and supervisors spend their attention on exceptions instead of routing routine work.

## Positioning
WhatsApp-first valet operations where assignment is deterministic and database-guarded: the valet who parked the car is preferred only when free, otherwise the longest-idle valet, oldest request first; an accepted job is never silently moved; handover requires a ticket-bound collection code. No LLM sits in the operational path.

## Operating Context
- Event-based operations at restaurants and halls; one organization, many venues and events (not public SaaS).
- Arabic-first, English supported; Asia/Riyadh time; operational identifiers in Western digits 0–9.
- Noisy, bright or dim venue environments; staff glance at screens between physical tasks.
- WhatsApp is the staff and guest channel; the console is for supervisors and above.

## Capabilities and Constraints
- Ticket states: RECEIVED, PARKED, RETRIEVING, READY, DELIVERED, CANCELLED, UNCLAIMED. Requests: WAITING_FOR_PARKING, QUEUED, OFFERED, ACCEPTED, COMPLETED, WITHDRAWN.
- Supervisor exception actions: withdraw a request, cancel an abandoned intake before parking starts, custody transfer, phone correction, intake exceptions, acknowledge alerts, start/end shifts.
- The console must show a stale-data banner and disable unsafe actions when disconnected; repeated submits are idempotent.
- Full guest phone numbers are never shown in routine views (masked only).
- V1 excludes payments, tipping, customer app, dynamic pricing, plate recognition, GPS tracking, marketing and public SaaS onboarding.
- *(open)* Real WhatsApp sender and templates; hosting region; retention durations; peak volumes.

## Brand Commitments
Approved identity in `DESIGN.md` and `brand/` (plum/gold palette, Noto Sans Arabic + Noto Sans, supplied handoff mark and outlined lockups). Voice: composed, clear, attentive; no luxury clichés, technology jargon or invented arrival estimates.

## Evidence on Hand
Brand guide PDF, preview PNG, SVG logos, licensed fonts and tokens in the repository. No customer testimonials, metrics or venue photography exist; none may be fabricated. Demo data is synthetic and must be labelled as such.

## Product Principles
1. One obvious next action.
2. Show real status; never imply progress that has not happened.
3. Preserve accountability: every car, key and task has a named owner.
4. Exceptions are the supervisor's work; routine flow is automatic.
5. Respect the guest's time.

## Accessibility & Inclusion
WCAG AA contrast; RTL and LTR; 360 px phones to desktop; 200% zoom; visible keyboard focus; 44 × 44 px primary targets; status never conveyed by colour alone (DESIGN.md, docs/06 Design QA).
