# 09 — Requirements-to-tests traceability matrix

Status: **Proposed — awaiting approval.** Every test is **NOT RUN** (no code exists). Built from docs/01–07, CLAUDE.md, DESIGN.md and ADR-0005/0006.

**Origin:**
- **A** — approved business direction (docs/01 approved changes, docs/07 §Approved)
- **P** — preserved from the original operating documents
- **D** — proposed default, still awaiting approval

**Layer:**
- **U** — unit
- **I** — integration on real PostgreSQL and the real worker process
- **C** — provider contract
- **E** — Playwright end-to-end
- **L** — load
- **R** — recovery
- **M** — manual or operational evidence

**WA** (WhatsApp dependency):
- **mock** — runs against the fake adapter and is reported as *mocked*
- **real** — needs the staging sender; reported BLOCKED until one exists
- **—** — no WhatsApp dependency

**Phase:** see `10_Build_Plan.md`. Gates are defined in docs/06.

## Registration and intake
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-01 | Explicit “مركبة جديدة” reserves the intake valet; internal ID plus event display number | 01§2, 04 | A | AT-02, AT-09 | U I | 1 | mock |
| R-02 | Phone: Arabic/Persian digits normalized, country code kept, international numbers allowed, masked confirmation, never confused with a hook | 01§2 | A | AT-01 | U I | 1 | mock |
| R-03 | Service-messaging permission recorded at confirmation; no marketing use | 01§2, 04 | A | AT-01, AT-02 | I | 1 | mock |
| R-04 | Ticket sent immediately after confirmation, before parking | 01§2 | A | AT-02, AT-28 | I C | 1 / 3 | mock / real |
| R-05 | Staff-confirmed in-person receipt stored separately from provider delivery; “contact unconfirmed” exception visible | 01§2, 02, ADR-0005 C3 | A | AT-35 | I E | 1 | mock |
| R-06 | No messages to a guessed number; correction path for a wrong number | 01§2, 03 | A | AT-17 | I | 1 | mock |
| R-07 | Usable vehicle identifier required, or a reasoned supervisor exception | 01§2, 07 | D | AT-03 | U I | 1 | mock |
| R-08 | Four photos before movement; ticket, uploader and server receipt time; private originals; upload time never labelled capture time | 01§2, 04, ADR-0005 C8 | P / A | AT-03, AT-21, AT-29 | I | 1 | mock |
| R-09 | Photos outside intake go only to an explicitly selected incident; type, size and content validation | 04, 05 | D | AT-36 | I | 2 | mock |
| R-10 | Intake handed to another valet → explicit custody transfer; `parked_by` = the valet who completes parking | 01§3, 02 | A | AT-37 | I | 1 | mock |

## Parking and location
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-11 | Location and key hook are separate fields; PARKED only once both are recorded; valet released | 01§3 | A | AT-03 | U I | 1 | mock |
| R-12 | Key-hook collision rejected, including carryover across events | 01§3, 02, ADR-0005 C1 | D | AT-33, AT-43 | I | 1 / 2 | — |
| R-13 | Relocation is an explicit task with custody and old/new location | 02 | D | AT-33 | I | 2 | mock |
| R-14 | Parked confirmation sent to the guest | 01§3, 04 | A | AT-38 | I | 1 | mock |
| R-15 | Early request kept as WAITING_FOR_PARKING; no dispatch to an unparked car | 01§3 | A | AT-04 | I | 1 | mock |

## Guest request
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-16 | Request authenticated by guest binding plus opaque action reference; display number is never a credential; forwarded buttons rejected without leaking data | 01§4, 04 | A / D | AT-16 | U I C | 1 / 3 | mock / real |
| R-17 | Exactly one open request; repeat taps return current status | 01§4 | A | AT-10 | I | 1 | mock |
| R-18 | Several tickets on one phone → explicit selection | 01§4 | A | AT-18 | I | 1 | mock |
| R-19 | Truthful wording (queued vs. being retrieved); no invented ETA; guest's language preserved; identifiers kept LTR | 01§4, 04, DESIGN | A | AT-38 | U I | 1 | mock |
| R-20 | Supervisor withdrawal before acceptance with a reason; later re-request allowed; ticket cancellation withdraws the open request | 02, ADR-0005 C2 | P / D | AT-54 | I | 2 | mock |

## Dispatch
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-21 | Oldest eligible request first; original request time kept through reassignment | 01§5, 03 | A | AT-07, AT-12, AT-32 | U I | 1 | mock |
| R-22 | Original parking valet preferred only if available; otherwise another free valet immediately | 01§5, 03 | A | AT-05, AT-06, AT-32 | U I | 1 | mock |
| R-23 | Fallback is longest-idle valet with a stable tie-break | 03 | D | AT-06 | U | 1 | — |
| R-24 | Request and valet reserved atomically; outbox row written in the same transaction | 03, ADR-0002/3 | D | AT-08, AT-09, AT-25 | I | 1 | mock |
| R-25 | Targeted offer contents (ticket, vehicle, location, hook, accept, expiry); never the code or the phone | 01§5, 04, ADR-0006 | A / D | AT-39 | U C | 1 | mock |
| R-26 | Decline or timeout → requeue without resetting age; cooldown; supervisor alert after 2 failures | 01§5, 03 | A / D | AT-12 | I | 1 | mock |
| R-27 | Acceptance rechecks every rule; generation and opaque ID; one winner per race | 03 | D | AT-11 | I | 1 | mock |
| R-28 | Everyone busy → visible queue that keeps its age | 01§5 | A | AT-07 | I E | 1 | mock |
| R-29 | Accepted work never auto-transferred; alert plus explicit custody transfer | 01§5, 03 | A | AT-13 | I | 1 | mock |
| R-30 | Late or stale actions rejected with no state or audit change | 02, 03 | D | AT-14 | I | 1 | mock |
| R-31 | Timing settings audited; issued offers keep their original deadline | 03 | D | AT-40 | I | 2 | — |
| R-32 | Valet shift readiness, breaks and help through WhatsApp | ADR-0006, ADR-0005 C6 | D | AT-19, AT-42 | I C | 1 | mock |

## Ready, handover and feedback
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-33 | READY only by the current accepted assignee; guest receives the ready message and code | 01§6, 02 | A | AT-15, AT-14 | I | 1 | mock |
| R-34 | Code: 6 digits, keyed verifier, created at READY, 5-attempt limit, consumed at delivery | 01§6, 04 | D | AT-15, AT-16 | U I | 1 | mock |
| R-35 | Assisted verification without a phone: supervisor+, with reason, verifier and outcome; no routine ID photos | 01§6 | A | AT-41 | I E | 2 | — |
| R-36 | Close only on physical delivery confirmation; release valet, hook and location; consume credentials; send rating request | 01§6 | A | AT-15 | I | 1 | mock |
| R-37 | An explicit hold blocks handover; an incident alone does not and never falsifies location | 01§7, 02 | A | AT-22 | I | 2 | — |
| R-38 | Phone correction after send: supervisor verification, revoke old tokens and codes, reissue, masked audit | 04 | D | AT-17 | I | 1 | mock |
| R-39 | Ratings: excellent → valet praise; neutral → silent; poor → supervisor alert plus complaint incident | 01§7 | P | AT-23 | I | 1 | mock |

## Shifts, custody and event close
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-40 | One active shift per person; supervisor activates and ends shifts | 01§1, 02 | P | AT-42 | I | 1 | — |
| R-41 | Availability derived from state; a break takes effect after custody is released | 01§1, 02 | A / D | AT-19 | I | 1 | mock |
| R-42 | Deactivation or shift end while holding custody → exception, never silent release | 02 | D | AT-19 | I | 1 | — |
| R-43 | Cancelled empty ticket with a reason (cutoff per ADR-0005 C4) | 01§8, 02 | P | AT-24 | I | 2 | — |
| R-44 | Unclaimed: manager-approved custody plan, named custodian, carryover register | 01§8 | D | AT-24, AT-43 | I E | 2 | — |
| R-45 | Opening check never shows healthy while the worker or WhatsApp is down | 01§1 | A | AT-44 | I E | 2 | mock |

## Roles, administration and audit
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-46 | Role and scope matrix enforced server-side, including direct API calls | 02 | P | AT-20, AT-21 | I E | 1 / 2 | — |
| R-47 | Guest-phone exports admin+ only; manager exports omit phones | 01, 02 | P | AT-20, AT-29 | I | 2 | — |
| R-48 | WhatsApp credentials and connection super admin only | 01, 02 | P | AT-20 | I | 2 | — |
| R-49 | Role grants bounded by grantor; last super admin protected; deactivate rather than delete | 01, 02 | P / D | AT-45 | I | 2 | — |
| R-50 | MFA for manager and above; rate limits on login and recovery | 01, 05 | D | AT-46 | I E | 2 | — |
| R-51 | Admin-configurable timings, templates, public info and retention; button wording changes never change behaviour | 01 | P | AT-47 | I | 2 | mock |
| R-52 | Overrides, impersonation, exports and credential changes audited; app role cannot alter audit rows | 02, 05, ADR-0003 | P / D | AT-48 | I | 1 / 2 | — |
| R-53 | Logs mask phones, codes and tokens | 03, 05 | D | AT-49 | I | 1 | — |

## Messaging reliability
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-54 | Webhook signature validated on the raw body before persistence; durable receipt before acknowledgement | 03, 05, CLAUDE | D | AT-50 | C I | 1 / 3 | mock / real |
| R-55 | Inbound deduplication; status events keyed by transition; no status regression | 03 | D | AT-10, AT-27 | I | 1 | mock |
| R-56 | Transactional outbox survives a crash between commit and send | 03 | D | AT-25 | R | 1 | mock |
| R-57 | Lost provider response → DELIVERY_UNKNOWN; no blind resend | 03 | D | AT-26 | R | 1 | mock |
| R-58 | Bounded retry, dead letter, idempotent operator replay | 03 | D | AT-51 | I R | 2 | mock |
| R-59 | Template vs. session message chosen by verified window state | 04 | A (platform) | AT-28 | C | 1 / 3 | mock / real |
| R-60 | WhatsApp outage: state kept, outage shown, supervisor-assisted operation | 03 | A | AT-31 | R M | 2 | mock |

## Reporting, retention and console
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-61 | Stage durations kept through reassignment; median and p95 by event; oldest queued request | 02 | P | AT-52 | I | 2 | — |
| R-62 | Working hours from actual shifts, breaks shown separately; payroll input only | 01, 02 | P | AT-52 | I | 2 | — |
| R-63 | Exports respect filters and scope; media exported separately and access-controlled | 01, 05 | P | AT-29 | I | 2 | — |
| R-64 | Retention 0 = never delete, shown explicitly; deletion previewed and audited; holds protect evidence | 05 | P / D | AT-30 | I | 2 | — |
| R-65 | Console: stale banner, unsafe mutations disabled, idempotent resubmit | 03 | D | AT-34 | E | 1 | — |
| R-66 | Arabic-first bilingual RTL/LTR; 360 px, tablet and desktop; 200% zoom; keyboard focus; 44 px targets; status never conveyed by colour alone | DESIGN, 06 | D | AT-53 | E M | 1 / 2 | — |
| R-67 | Supervisor home puts attention items first, scoped to one event | DESIGN | D | AT-53 | E | 1 / 2 | — |

## Non-functional
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-68 | Deterministic core: no LLM in any operational path | README, 01 | A | Dependency and architecture check | M | all | — |
| R-69 | Database unavailable → no false success; automatic dispatch stops | 03 | D | AT-31 | R | 2 | — |
| R-70 | Load: 10 events, 100 staff, 1,000 tickets, 100 requests in 60 s; API p95 < 500 ms; wake-to-offer p95 < 2 s; zero duplicate effects | 05 | D | LOAD-01 | L | 3 | mock |
| R-71 | Backup restore (RPO ≤ 15 min, RTO ≤ 60 min) and rollback without losing custody | 05, 06 | D | REC-01, REC-02 | R M | 3 / 4 | — |
| R-72 | Real WhatsApp flow in staging: templates, signed webhooks, delivery failures | 05, 06 | A | STG-01 | C M | 3 | **real** |
| R-73 | Production smoke on the exact build: guest message, accept, ready, handover, audit | 05, 06 | A | PROD-01 | M | 5 | **real** |

## Proposed additional acceptance scenarios (AT-35+)
docs/06 has no scenario covering these requirements. They are proposed additions for approval.

| ID | Scenario | Required outcome |
|---|---|---|
| AT-35 | Ticket sent; valet confirms or denies in-person receipt | CONFIRMED_IN_PERSON only by staff confirmation; denial or no answer leaves the exception visible; a delivery callback alone never confirms |
| AT-36 | Photo sent outside intake with 0, 1 or several open incidents; invalid type or oversize | Explicit incident selection; never attached to the “latest” incident; invalid files rejected |
| AT-37 | Intake started by A, parked by B | Custody transfer recorded; `parked_by`=B; retrieval affinity goes to B |
| AT-38 | Each guest message across states and in both languages | Queued never claims retrieval; no ETA; language preserved; identifiers isolated LTR |
| AT-39 | Offer message content | Includes ticket, vehicle, location, hook and expiry; never the collection code or guest phone |
| AT-40 | Timing settings changed while offers are live | Change audited; live offers keep their original deadline |
| AT-41 | Guest without a phone at handover | Supervisor+ assisted verification with reason, verifier and outcome; valet alone cannot |
| AT-42 | Second active shift for the same person (same or another event) | Rejected by the database constraint and a clear message |
| AT-43 | Event closes with an unclaimed car | Carryover case visible; its key hook stays occupied at the next event at the same venue |
| AT-44 | Worker heartbeat stale or WhatsApp degraded at opening | Console shows degraded with the specific cause, never healthy |
| AT-45 | Grant escalation attempts; removing the last super admin; deleting staff | Denied; staff are deactivated rather than deleted; history kept |
| AT-46 | Privileged login without MFA; repeated failed logins | MFA enforced; rate limit applied and audited |
| AT-47 | Button wording changed in templates | Same operations execute; action identifiers unchanged |
| AT-48 | Override, export and credential change; app role tries UPDATE/DELETE on audit rows | Audit events written; the mutation is refused by the database |
| AT-49 | Full flow run with log capture | No phone numbers, codes or tokens appear in logs |
| AT-50 | Webhook with missing or invalid signature; valid webhook | Invalid ones rejected before persistence; valid ones stored before acknowledgement |
| AT-51 | Permanent send failure; operator replay | Dead letter visible; replay applies its effect once |
| AT-52 | Reassigned retrieval and break-containing shift in reports | Original timestamps kept; median/p95 correct; breaks shown separately |
| AT-53 | Design QA matrix (docs/06 Design QA) | Passes on 360 px, tablet and desktop, at 200% zoom, with keyboard navigation, in Arabic and English, with status labels |
| AT-54 | Supervisor withdraws a queued request; ticket cancelled with an early request | WITHDRAWN with a reason; later re-request allowed; no orphaned open request |

## Coverage check
- Every docs/06 scenario AT-01…AT-34 appears at least once above.
- Every row has at least one test ID.
- **Extended Gate 2 set** (identical in `10_Build_Plan.md`):
  - docs/06 Gate 2 scenarios: AT-01–19, AT-32–34.
  - Phase 1 additions: AT-25, AT-26, AT-35, AT-37, AT-38, AT-39, AT-42, AT-48 (database-role part), AT-49, AT-50 (mocked), and AT-53 limited to the live view.
- Everything else is Gate 3 or later.
