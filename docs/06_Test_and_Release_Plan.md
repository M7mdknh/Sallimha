# 06 — Acceptance tests and release gates

Tests must verify observable behavior, invariants and failure recovery, not mirror implementation details. Use real PostgreSQL for concurrency; an in-memory database cannot prove the locking contract.

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
| AT-20 | Supervisor attempts manager incident closure / phone bulk export | Server denies, including direct API calls |
| AT-21 | Cross-event ticket, media and export IDs | Server denies access regardless of client view |
| AT-22 | Damage incident on a READY vehicle | Incident is separate; handover blocked only if explicit hold |
| AT-23 | Poor / neutral / excellent rating | Complaint alert / silent record / delivering-valet praise |
| AT-24 | Empty ticket cancellation or unclaimed vehicle | Distinct outcome; required reason; unclaimed custody preserved |
| AT-25 | Restart between commit and outbound send | Outbox recovers; state does not disappear |
| AT-26 | Provider accepted send but response was lost | DELIVERY_UNKNOWN handled; no false delivery assertion |
| AT-27 | Webhook statuses arrive out of order | No state regression; full event history |
| AT-28 | Guest/staff session window expired | Correct approved template path; no invalid free-form assumption |
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
| AT-39 | Offer content | Ticket, vehicle, location, hook, expiry; never collection code or guest phone |
| AT-40 | Timing change while offers are live | Audited; live offers keep original deadlines |
| AT-41 | Guest without phone at handover | Supervisor+ assisted verification with reason/verifier/outcome; valet alone cannot |
| AT-42 | Second active shift for one person | Rejected by DB constraint with a clear message |
| AT-43 | Event closes with an unclaimed car | Carryover case visible; its venue key hook remains occupied for later events |
| AT-44 | Worker heartbeat stale / WhatsApp degraded at opening | Degraded status with cause, never healthy |
| AT-45 | Grant escalation, last super admin, staff deletion | Denied; deactivate not delete; history kept |
| AT-46 | Privileged login without MFA; repeated failures | MFA enforced; rate-limited and audited |
| AT-47 | Button wording changed | Same operations; action identifiers unchanged |
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
| AT-60 | Duplicate or expired valet button taps (accept, ready, delivered, ready-for-work) | Duplicate returns the current outcome without a second effect; expired/superseded rejected with the stale message; no state change |

## Verification layers
- Unit: phone normalization, state guards, candidate ordering, permissions, formatting and deadline calculations.
- Integration: transactions, uniqueness constraints, media authorization, inbox/outbox, dead-letter handling and actual worker restart.
- Provider contracts: captured sanitized fixtures plus official sandbox/test-number scenarios; malformed signatures, duplicate callbacks, retryable/permanent failures and template rejection.
- End-to-end: responsive console, role-specific views, Arabic and English, narrow screens, keyboard/focus behavior and supervisor exceptions. Use Playwright to preserve repeatable tests and traces.
- Load: declared event/staff/ticket mix; burst requests; p50/p95/p99 response times; worker lag; fairness and zero duplicate effects.
- Recovery: killed worker, unavailable provider, database failover where supported, backup restore, migration rollback compatibility.

## Design QA
Use DESIGN.md tokens. Test 360 px mobile, tablet and desktop; 200% zoom; actual Arabic and mixed phone/plate identifiers; visible keyboard focus; semantic text with status color; sufficient contrast. Primary staff interactions should use at least 44 × 44 CSS px targets as a proposed usability standard. Do not rely solely on automated accessibility scans.

## Gates
1. **Specification / brand:** included files read, conflicts resolved, proposed defaults recorded, identity reviewed before UI build.
2. **Core correctness:** AT-01–19 and AT-32–34 pass against real database/worker; failures are fixed before expanding scope.
3. **Operational completeness:** incidents, roles, reporting, retention and recovery acceptance pass.
4. **Staging:** real WhatsApp template flow works; browser QA, security review and load scenario have evidence.
5. **Production readiness:** provider/region/owner selected, secrets configured, restore proven, runbooks and rollback tested, critical/high issues resolved or explicitly assessed by the responsible owner.
6. **Release:** exact build deployed, health checks and designated production smoke pass; status is reported with version/time and remaining limitations.

## Evidence format
For each gate, record test command/scenario, environment, build identifier, result, evidence path and limitations. Use PASS / FAIL / BLOCKED / NOT RUN. An unconfigured provider is BLOCKED, not PASS. Mocked message delivery must be labelled mocked: results obtained with the local fake WhatsApp transport are reported as **PASS (SIMULATED)** and are never counted as real integration evidence; real-provider scenarios stay BLOCKED until run in staging. Retain test artifacts without guest personal data.

