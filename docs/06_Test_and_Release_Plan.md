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
For each gate, record test command/scenario, environment, build identifier, result, evidence path and limitations. Use PASS / FAIL / BLOCKED / NOT RUN. An unconfigured provider is BLOCKED, not PASS. Mocked message delivery must be labelled mocked. Retain test artifacts without guest personal data.

