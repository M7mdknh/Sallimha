# 06 — Acceptance tests and release gates

Tests must verify observable behavior, invariants and failure recovery, not mirror implementation details. Use real PostgreSQL for concurrency; an in-memory database cannot prove the locking contract.

> **Since 17 Nov 2026 ([ADR-0011](adr/0011-staff-app-and-three-roles.md), [ADR-0012](adr/0012-admin-access-and-offer-acknowledgement.md)):** customers use WhatsApp only; valets and supervisors use the web app on phones and tablets; the roles are VALET, SUPERVISOR and ADMIN. Scenarios below keep their IDs; where a scenario named a staff WhatsApp message, a manager or a super admin, read the valet app, an admin, and the amended wording in the table. AT-61–AT-72 cover the staff app, the three roles and the pre-staging fixes.

## Critical acceptance scenarios
| ID | Scenario | Required outcome |
|---|---|---|
| AT-01 | Register Saudi and international numbers, including Arabic digits | Correct normalization, explicit confirmation, no hook/phone confusion |
| AT-02 | Register and send ticket before parking | Guest receives correct ticket; vehicle remains RECEIVED |
| AT-03 | Four photos and location/hook | Correct evidence binding; PARKED only after requirements or audited exception |
| AT-04 | Guest requests during parking | One WAITING_FOR_PARKING request; no second movement task |
| AT-05 | Original parking valet available | They receive the targeted offer |
| AT-06 | Original valet busy; another free | Other valet is offered immediately, respecting older requests |
| AT-07 | Everyone busy | Visible queue; original wait age preserved |
| AT-08 | Two dispatchers race | One live request assignment and one staff capacity reservation |
| AT-09 | Intake and retrieval compete for same valet | Exactly one wins capacity; other gets truthful state |
| AT-10 | Guest taps request repeatedly / webhook repeats | One business request; repeat status response |
| AT-11 | Offer acceptance races expiry | One valid transition; stale acceptance cannot move car |
| AT-12 | Valet declines or fails to respond | Requeue, release capacity, preserve age, cooldown and alert rules |
| AT-13 | Accepted valet times out/offline | Alert only; no second valet dispatched until custody transfer |
| AT-14 | Late ready/delivered action from old assignee | Rejected without changing state |
| AT-15 | READY then correct collection code | Verify ticket and handover; close once; release resources |
| AT-16 | Wrong/forwarded code, wrong sender or guessed ticket | No unauthorized retrieval/handover; rate limit and incident path |
| AT-17 | Correct phone after ticket already sent | Old tokens/code revoked; new guest confirmed; audit retained |
| AT-18 | Multiple vehicles on one guest phone | Exact ticket selection; no arbitrary car |
| AT-19 | Break, shift end or staff deactivation with active custody | Prevent silent release; explicit transfer/exception |
| AT-20 | Supervisor attempts an admin-only action (incident closure, phone bulk export; formerly manager+) | Server denies, including direct API calls |
| AT-21 | Cross-event ticket, media and export IDs | Server denies access regardless of client view |
| AT-22 | Damage incident on a READY vehicle | Incident is separate; handover blocked only if explicit hold |
| AT-23 | Poor / neutral / excellent rating | Complaint alert / silent record / delivering-valet praise |
| AT-24 | Empty ticket cancellation or unclaimed vehicle | Distinct outcome; required reason; unclaimed custody preserved |
| AT-25 | Restart between commit and outbound send | Outbox recovers; state does not disappear |
| AT-26 | Provider accepted send but response was lost | DELIVERY_UNKNOWN handled; no false delivery assertion |
| AT-27 | Webhook statuses arrive out of order | No state regression; full event history |
| AT-28 | Guest session window expired (staff no longer receive WhatsApp messages) | Correct approved template path; no invalid free-form assumption |
| AT-29 | Export filtered reports | Only permitted fields and selected scope; media not public |
| AT-30 | Retention with open dispute hold | Protected evidence survives; eligible deletion is audited |
| AT-31 | Service/database outage | No false success; recovery and human continuity runbook exercised |
| AT-32 | Concurrent older/newer requests with original-valet affinity | Queue fairness wins before candidate affinity |
| AT-33 | Key-hook collision and vehicle relocation | Collision rejected; movement task/custody recorded |
| AT-34 | Stale console and repeated submit after reconnect | Explicit stale banner; idempotent recovery |

### Added 15 Nov 2026 (approved by the user)
| ID | Scenario | Required outcome |
|---|---|---|
| AT-35 | Valet confirms or denies that the guest received the ticket | CONFIRMED_IN_PERSON only by staff confirmation; denial/no answer leaves the visible exception; provider DELIVERED/READ alone never confirms |
| AT-36 | Photo outside intake with 0/1/many open incidents; invalid type or size | Explicit incident selection; never “latest incident”; invalid files rejected |
| AT-37 | Intake started by A, parked by B | Custody transfer recorded; `parked_by` = B; retrieval affinity follows B |
| AT-38 | Every guest message, both languages | Queued never claims retrieval; no ETA; language preserved; identifiers isolated LTR |
| AT-39 | Offer content (valet app task card) | Ticket, vehicle, location, hook, expiry; never collection code or guest phone |
| AT-40 | Timing change while offers are live | Audited; live offers keep original deadlines |
| AT-41 | Guest without phone at handover | Supervisor+ assisted verification with reason/verifier/outcome; valet alone cannot |
| AT-42 | Second active shift for one person | Rejected by DB constraint with a clear message |
| AT-43 | Event closes with an unclaimed car | Carryover case visible; its venue key hook remains occupied for later events |
| AT-44 | Worker heartbeat stale / WhatsApp degraded at opening | Degraded status with cause, never healthy |
| AT-45 | Grant by a non-admin, removing the last admin, staff deletion | Denied; deactivate not delete; history kept |
| AT-46 | Admin login without MFA; repeated failures | MFA enforced; rate-limited and audited; a locked factor is cleared only by the controlled procedure (AT-70) |
| AT-47 | Customer button wording changed | Same operations; action identifiers unchanged |
| AT-48 | Overrides/exports/credential changes; app role UPDATE/DELETE on audit | Audited; mutation refused by the database |
| AT-49 | Full flow with log capture | No phones, codes or tokens in logs |
| AT-50 | Missing/invalid webhook signature; valid webhook | Rejected before persistence; valid stored before acknowledgement |
| AT-51 | Permanent send failure; operator replay | Dead letter visible; replay effects applied once |
| AT-52 | Reports after reassignment and breaks | Original timestamps kept; median/p95 correct; breaks separate |
| AT-53 | Design QA matrix | 360 px/tablet/desktop, 200% zoom, keyboard, Arabic/English, status labels |
| AT-54 | Supervisor withdraws a WAITING/QUEUED/OFFERED request | Request WITHDRAWN with reason; live offer superseded and reservation released; vehicle stays PARKED; ticket open; guest can request again |
| AT-55 | Cancel an intake before vs. after “بدء الركن”; with and without guest-has-vehicle-and-keys confirmation | Allowed only before parking starts and with the confirmation; refused otherwise; after parking starts the car leaves only through retrieval and verified handover |
| AT-56 | Cancel a ticket that has an early request and an intake reservation | Request WITHDRAWN (`ticket_cancelled`); intake task cancelled; valet released; guest tokens/codes revoked; guest told truthfully |
| AT-57 | Withdraw an ACCEPTED retrieval | Refused without custody resolution; with a recorded and acknowledged resolution the task closes, ticket returns to PARKED at the recorded location/hook, valet released explicitly |
| AT-58 | Unclaimed vehicle's key hook | Stays reserved across events until an explicit, audited release; release by non-authorized role denied |
| AT-59 | Supervisor console scope | Supervisor can monitor live work, start/end shifts and handle exceptions in assigned events; no control exists to dispatch routine retrieval manually; valets have no console access |
| AT-60 | Duplicate or expired valet taps in the app (double tap, second tab, retry after a lost reply: accept, ready, delivered, availability) | Duplicate returns the current outcome without a second effect; expired/superseded rejected with the stale message; no state change |

### Added 17 Nov 2026 (ADR-0011 staff app; ADR-0012 pre-staging fixes)
| ID | Scenario | Required outcome |
|---|---|---|
| AT-61 | Intake to verified delivery entirely in the valet app | Every staff step in the app; no message queued to staff and no staff action token issued; customer messages unchanged |
| AT-62 | Offer on the valet's screen: polling, refresh, a second tab, a late or lost acknowledgement | Reading My work changes nothing; the first explicit acknowledgement starts the window once; repeats return the same deadline; never past the hard limit; an unacknowledged offer lapses at the hard limit and is reassigned with cooldown and the original request time |
| AT-63 | Valet's connection drops and returns | Connection lost shown at once; state unchanged; nothing shown as done before the server confirms; the app resumes from the server's step; idempotency key kept until confirmed |
| AT-64 | A valet's device stops working | Supervisor marks it; records acceptance, ready, custody, photos and parking for that valet only, naming how it was confirmed; refused for other valets and for a customer outage alone |
| AT-65 | Customer WhatsApp down while the staff app works | Staff keep working in the app; assisted request and handover; after recovery only messages still true are sent; stale ones end OBSOLETE |
| AT-66 | Customer writes for help; supervisor contacts the customer | Message kept on the ticket; one open help alert per ticket; number revealed only on request, scoped and audited; valets refused |
| AT-67 | Three roles after migration | MANAGER/SUPER_ADMIN → ADMIN with one audit record each, reversible; navigation per role; server refuses every out-of-role read and command; valets have no console access; product admins are not framework superusers |
| AT-68 | Onboarding with a one-time setup code | Code shown once, stored hashed, 72 h, five attempts; replaced codes fail; completion ends other sessions; nobody else knows the password |
| AT-69 | One admin tries to obtain another admin's credentials in the app (directly, or demote → reset → promote) | No setup code and no second factor for an admin from the app; a pending code is cancelled when a role change involves ADMIN; the detour ends at a sign-in that needs the controlled procedure |
| AT-70 | Controlled admin access (first access, lockout, lost phone) | Requesting admin and a different approver, a reason, the operator named; password and second factor reset together; sessions end; lock cleared; first-admin only when nobody else could approve; record shown on the Team page; secrets never in the audit |
| AT-71 | Every main screen of the three roles at 360, 390, 768 and 1024 px, Arabic and English | No sideways overflow; screenshots reviewed by eye |
| AT-72 | Real phones and tablets (Gate 4 rehearsal): camera capture, locked screen, missed offer, connectivity loss and recovery | Manual checklist in docs/staging/real-device-checklist.md passes; NOT RUN until the rehearsal |

## Verification layers
- Unit: phone normalization, state guards, candidate ordering, permissions, formatting and deadline calculations.
- Integration: transactions, uniqueness constraints, media authorization, inbox/outbox, dead-letter handling and actual worker restart.
- Provider contracts: captured sanitized fixtures plus official sandbox/test-number scenarios; malformed signatures, duplicate callbacks, retryable/permanent failures and template rejection.
- End-to-end: the valet app on phone sizes, Operations and Team on tablets, the admin screens, role-specific views, Arabic and English, narrow screens, keyboard/focus behavior and supervisor exceptions. Use Playwright to preserve repeatable tests and traces.
- Manual on real devices: camera, locked screen, missed offers, venue connectivity (AT-72); browser emulation does not replace it.
- Load: declared event/staff/ticket mix; burst requests; p50/p95/p99 response times; worker lag; fairness and zero duplicate effects.
- Recovery: killed worker, unavailable provider, database failover where supported, backup restore, migration rollback compatibility.

## Design QA
Use DESIGN.md tokens. Test 360 and 390 px phones, 768 and 1024 px tablets (portrait and landscape) and desktop; 200% zoom; actual Arabic and mixed phone/plate identifiers; visible keyboard focus; semantic text with status color; sufficient contrast. Primary staff interactions should use at least 44 × 44 CSS px targets as a proposed usability standard. Do not rely solely on automated accessibility scans.

## Gates
1. **Specification / brand:** included files read, conflicts resolved, proposed defaults recorded, identity reviewed before UI build.
2. **Core correctness:** AT-01–19 and AT-32–34 pass against real database/worker; failures are fixed before expanding scope.
3. **Operational completeness:** incidents, roles, reporting, retention and recovery acceptance pass.
4. **Staging:** real WhatsApp template flow works (customer templates only); the real-device rehearsal (AT-72) passes with staff phones/tablets; browser QA, security review and load scenario have evidence.
5. **Production readiness:** provider/region/owner selected, secrets configured, restore proven, runbooks and rollback tested, critical/high issues resolved or explicitly assessed by the responsible owner.
6. **Release:** exact build deployed, health checks and designated production smoke pass; status is reported with version/time and remaining limitations.

## Evidence format
For each gate, record test command/scenario, environment, build identifier, result, evidence path and limitations. Use PASS / FAIL / BLOCKED / NOT RUN. An unconfigured provider is BLOCKED, not PASS. Mocked message delivery must be labelled mocked: results obtained with the local fake WhatsApp transport are reported as **PASS (SIMULATED)** and are never counted as real integration evidence; real-provider scenarios stay BLOCKED until run in staging. Retain test artifacts without guest personal data.

