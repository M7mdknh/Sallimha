# 09 — Requirements-to-tests traceability matrix

Status: **Approved 2026-11-15** (user decision 6); **amended 2026-11-17** for [ADR-0011](adr/0011-staff-app-and-three-roles.md) (staff web app, customer-only WhatsApp, three roles) and [ADR-0012](adr/0012-admin-access-and-offer-acknowledgement.md) (controlled admin access, explicit offer acknowledgement). IDs are stable: rows were amended in place and new ones added (R-74–R-86, AT-61–AT-72). Test status is tracked in `PROGRESS.md`; WhatsApp-dependent results from the fake transport are reported as **PASS (SIMULATED)**, never as real integration evidence. Built from docs/01–07, CLAUDE.md, DESIGN.md and ADR-0005/0006/0011/0012.

**Origin:**
- **A** — approved business direction (docs/01 approved changes, docs/07 §Approved)
- **P** — preserved from the original operating documents
- **D** — proposed default accepted for the build (pilot-tunable; not separately validated in production)

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
- **—** — no WhatsApp dependency (since ADR-0011 every staff step is in the app; only customer messages depend on WhatsApp)

**Phase:** see `10_Build_Plan.md`; **P** = staff-app pilot changes (ADR-0011/0012), evidenced with Gate 3. Gates are defined in docs/06.

## Registration and intake
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-01 | Explicit new-vehicle action reserves the intake valet (app: **Register car**, ADR-0011); internal ID plus event display number | 01§2, 04 | A | AT-02, AT-09, AT-61 | U I E | 1 / P | mock |
| R-02 | Phone: Arabic/Persian digits normalized, country code kept, international numbers allowed, masked confirmation, never confused with a hook | 01§2 | A | AT-01 | U I | 1 | mock |
| R-03 | Service-messaging permission recorded at confirmation; no marketing use | 01§2, 04 | A | AT-01, AT-02 | I | 1 | mock |
| R-04 | Ticket sent immediately after confirmation, before parking | 01§2 | A | AT-02, AT-28 | I C | 1 / 3 | mock / real |
| R-05 | ~~Explicit staff confirmation that the guest received the ticket~~ — **retired by ADR-0013**: provider status shown instead (never treated as confirmation); failures raise a supervisor issue (R-87) | 01§2, 02, ADR-0005 C3, ADR-0013 | A | AT-73, AT-74 | I E | 1 / P | mock |
| R-06 | No messages to a guessed number; correction path for a wrong number | 01§2, 03 | A | AT-17 | I | 1 | mock |
| R-07 | Usable vehicle identifier required, or a reasoned supervisor exception | 01§2, 07 | D | AT-03 | U I | 1 | mock |
| R-08 | Four photos before movement; ticket, uploader and server receipt time; private originals; upload time never labelled capture time | 01§2, 04, ADR-0005 C8 | P / A | AT-03, AT-21, AT-29 | I | 1 | mock |
| R-09 | Photos outside intake go only to an explicitly selected incident; type, size and content validation | 04, 05 | D | AT-36 | I | 2 | mock |
| R-10 | Intake handed to another valet → explicit custody transfer; `parked_by` = the valet who completes parking | 01§3, 02 | A | AT-37 | I | 1 | mock |

## Parking and location
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-11 | Location and key hook are separate fields; PARKED only once both are recorded; valet released | 01§3 | A | AT-03 | U I | 1 | mock |
| R-12 | Venue-owned key hooks: collision rejected; occupancy survives event closure and stays reserved for unclaimed cars until explicit audited release | 01§3, 02, ADR-0005 C1 | A | AT-33, AT-43, AT-58 | I | 1 / 2 | — |
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
| R-20 | Withdrawal leaves vehicle PARKED and ticket open; before acceptance it supersedes offers and releases reservations; after acceptance only with supervised custody resolution; re-request allowed | 01, 02, ADR-0005 C2 | A | AT-54, AT-57 | I | 1 | mock |

## Dispatch
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-21 | Oldest eligible request first; original request time kept through reassignment | 01§5, 03 | A | AT-07, AT-12, AT-32 | U I | 1 | mock |
| R-22 | Original parking valet preferred only if available; otherwise another free valet immediately | 01§5, 03 | A | AT-05, AT-06, AT-32 | U I | 1 | mock |
| R-23 | Fallback is longest-idle valet with a stable tie-break | 03 | D | AT-06 | U | 1 | — |
| R-24 | Request and valet reserved atomically; outbox row written in the same transaction | 03, ADR-0002/3 | D | AT-08, AT-09, AT-25 | I | 1 | mock |
| R-25 | Targeted offer contents (ticket, vehicle, location, hook, accept, expiry) on the valet's task card; never the code or the phone | 01§5, 04, ADR-0006, ADR-0011 | A / D | AT-39 | U I E | 1 / P | — |
| R-26 | Decline or timeout → requeue without resetting age; cooldown; supervisor alert after 2 failures; timeout = response window from the app's acknowledgement or the hard limit (ADR-0012) | 01§5, 03 | A / D | AT-12, AT-62 | I | 1 / P | — |
| R-27 | Acceptance rechecks every rule; generation and opaque ID; one winner per race | 03 | D | AT-11 | I | 1 | mock |
| R-28 | Everyone busy → visible queue that keeps its age | 01§5 | A | AT-07 | I E | 1 | mock |
| R-29 | Accepted work never auto-transferred; alert plus explicit custody transfer | 01§5, 03 | A | AT-13 | I | 1 | mock |
| R-30 | Late or stale actions rejected with no state or audit change | 02, 03 | D | AT-14 | I | 1 | mock |
| R-31 | Timing settings audited; issued offers keep their original deadline | 03 | D | AT-40 | I | 2 | — |
| R-32 | Valet contract — **in the app since ADR-0011** (the WhatsApp contract of ADR-0006 is retired behind `STAFF_CHANNEL=whatsapp`): availability, intake, receipt confirmation, parking start/completion, offer accept/decline, retrieval, ready, code, handover, moves, custody acknowledgement, breaks | ADR-0006, ADR-0005 C6, ADR-0011 | A | AT-19, AT-42, AT-60, AT-61 | I E | 1 / P | — |
| R-32a | Duplicate or expired valet taps rejected safely; no second effect (double tap, second tab, retry) | ADR-0006, 03, ADR-0011 | A | AT-60, AT-14 | I E | 1 / P | — |

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
| R-43 | Cancel abandoned intake only before “بدء الركن” and after confirming guest has vehicle and keys; cascade withdraws requests, cancels intake task, releases reservation, revokes credentials | 01, 02, ADR-0005 C2/C4 | A | AT-24, AT-55, AT-56 | I | 1 | mock |
| R-44 | Unclaimed: admin-approved (formerly manager) custody plan, named custodian, carryover register | 01§8, ADR-0011 | D | AT-24, AT-43 | I E | 2 | — |
| R-45 | Opening check never shows healthy while the worker or WhatsApp is down | 01§1 | A | AT-44 | I E | 2 | mock |

## Roles, administration and audit
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-46 | Role and scope matrix enforced server-side, including direct API calls | 02 | P | AT-20, AT-21 | I E | 1 / 2 | — |
| R-47 | Guest-phone exports admin only; supervisors have no exports | 01, 02, ADR-0011 | P | AT-20, AT-29 | I | 2 | — |
| R-48 | WhatsApp connection status admin only; credentials only in the hosting secret store | 01, 02, ADR-0011 | P | AT-20 | I | 2 | — |
| R-49 | Role grants by admins only, never to themselves; last admin protected; deactivate rather than delete | 01, 02, ADR-0011 | P / D | AT-45, AT-67 | I | 2 / P | — |
| R-50 | MFA for admins; rate limits on login and recovery; an admin's password and second factor only from the controlled procedure (ADR-0012) | 01, 05, ADR-0011/0012 | D / A | AT-46, AT-69, AT-70 | I E | 2 / P | — |
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
| R-60 | Customer WhatsApp outage: state kept, outage shown, staff keep working in the app, supervisor-assisted request and handover | 03, ADR-0011 | A | AT-31, AT-65 | R E M | 2 / P | mock |

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
| R-67a | Supervisor console = live monitoring, shift operations and exception handling; no manual routine-dispatch control; valets have no console access | 01 (clarified), 02 | A | AT-59 | I E | 1 / 2 | — |

## Staff app, three roles and pre-staging fixes (ADR-0011, ADR-0012)
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-74 | Customers use WhatsApp only; in app mode no message is queued to staff and no staff action token is issued | ADR-0011 | A | AT-61 | I | P | mock |
| R-75 | Valet app: My work shows one task with the next action; Register car in six steps; only the valet's own shift, task and ticket, customer number masked | ADR-0011 | A | AT-61, AT-63 | I E | P | — |
| R-76 | My work is a read without side effects; an explicit, CSRF-protected, idempotent acknowledgement starts an offer's window once; never extended; hard limit kept | ADR-0012 | A | AT-62 | I E | P | — |
| R-77 | Connection indicator, recovery on reconnection, nothing shown as done before the server confirms, idempotency key kept until confirmed; optional sound never the only signal | ADR-0011 | A | AT-63, AT-34 | E | P | — |
| R-78 | Staff device not working: supervisor records for that valet only, naming how it was confirmed | ADR-0011, ADR-0008 | A | AT-64 | I E | P | — |
| R-79 | Customer WhatsApp outage never forces relays while the staff app works | ADR-0011 | A | AT-65 | I E | P | mock |
| R-80 | Customer help message kept on the ticket; Contact customer reveals the number on request, scoped and audited; the call or chat happens outside Sallimha | ADR-0011 | A | AT-66 | I E | P | mock |
| R-81 | Three roles; audited, reversible migration; navigation per role; server refusals; valets have no console access; console roles have no valet endpoints | ADR-0011 | A | AT-67, AT-20, AT-59 | I E | P | — |
| R-82 | Onboarding without shared credentials: one-time setup code, hashed, 72 h, five attempts | ADR-0011 | A | AT-68 | I E | P | — |
| R-83 | No admin credential from the app; controlled admin access with a requesting admin and a different approver; visible record on the Team page | ADR-0012 | A | AT-69, AT-70 | I E | P | — |
| R-84 | Operations: problems first, then waiting / on the way / ready with waiting time, search; ticket detail with one primary action and More actions; admin dashboard with defined metrics, no invented scores | ADR-0011 | A | AT-71, AT-53 | E | P | — |
| R-85 | Phone and tablet layouts in Arabic and English at 360, 390, 768 and 1024 px | ADR-0011 | A | AT-71 | E M | P | — |
| R-86 | Real devices: camera capture, locked screen, missed offer, connectivity loss and recovery | ADR-0011, ADR-0012 | A | AT-72 | M | 3 | — |

## Usability: intake, phone, plate, location, dashboards (ADR-0013)
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-87 | No receipt question; ticket message status from provider events; one deduplicated failure issue with correct-number and resend | ADR-0013 | A | AT-73, AT-74 | I E | P | mock |
| R-88 | Phone entry with a country selector (SA default); server authority with specific refusals; canonical E.164; input kept; no phone uniqueness on tickets | ADR-0013 | A | AT-75 | U I E | P | — |
| R-89 | Saudi plate entry stored as entered (verified 17-letter set); other plates as typed; explicit missing-plate path; search by normalised key in either script | ADR-0013 | A | AT-76 | U I E | P | — |
| R-90 | Possible duplicate active plate shown before registering; explicit override; finished tickets never block | ADR-0013 | A | AT-77 | I E | P | — |
| R-91 | Parking place: zone/spot required, floor and description, optional confirmed pin with accuracy, source and times; never the venue centre; parking never blocked by the map | ADR-0013 | A | AT-78 | I E | P | — |
| R-92 | Retrieval and relocation use the saved place and pin; Open in Google Maps with coordinates only; pin set or cleared with every place write | ADR-0013 | A | AT-79 | I E | P | — |
| R-93 | Maps JavaScript API lazy-loaded with a run-time, website-restricted key; unconfigured or failing map labelled; no Geolocation API; referrer sends origin only | ADR-0013 | A | AT-78, staging header test | I E M | P / 3 | — |
| R-94 | Admin dashboard and supervisor Operations as specified, from real data, with clear empty states | ADR-0013 | A | AT-80, AT-71 | I E M | P | — |

## Non-functional
| ID | Requirement | Source | Origin | Tests | Layer | Phase | WA |
|---|---|---|---|---|---|---|---|
| R-68 | Deterministic core: no LLM in any operational path | README, 01 | A | Dependency and architecture check | M | all | — |
| R-69 | Database unavailable → no false success; automatic dispatch stops | 03 | D | AT-31 | R | 2 | — |
| R-70 | Load: 10 events, 100 staff, 1,000 tickets, 100 requests in 60 s; API p95 < 500 ms; wake-to-offer p95 < 2 s; zero duplicate effects | 05 | D | LOAD-01 | L | 3 | mock |
| R-71 | Backup restore (RPO ≤ 15 min, RTO ≤ 60 min) and rollback without losing custody | 05, 06 | D | REC-01, REC-02 | R M | 3 / 4 | — |
| R-72 | Real WhatsApp flow in staging: templates, signed webhooks, delivery failures | 05, 06 | A | STG-01 | C M | 3 | **real** |
| R-73 | Production smoke on the exact build: guest message, accept, ready, handover, audit | 05, 06 | A | PROD-01 | M | 5 | **real** |

## Additional acceptance scenarios (AT-35+, approved 2026-11-15; also listed in docs/06)

| ID | Scenario | Required outcome |
|---|---|---|
| AT-35 | ~~Ticket sent; valet confirms or denies in-person receipt~~ (retired, ADR-0013) | CONFIRMED_IN_PERSON only by staff confirmation; denial or no answer leaves the exception visible; a delivery callback alone never confirms |
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
| AT-54 | Supervisor withdraws a WAITING/QUEUED/OFFERED request | WITHDRAWN with reason; live offer superseded and reservation released; vehicle stays PARKED; ticket open; guest may request again |
| AT-55 | Cancel intake before vs. after “بدء الركن”, with/without guest-has-vehicle-and-keys confirmation | Allowed only before parking starts and with confirmation; refused otherwise |
| AT-56 | Cancel a ticket with an early request and an intake reservation | Request WITHDRAWN (`ticket_cancelled`); intake task cancelled; valet released; tokens/codes revoked; guest informed |
| AT-57 | Withdraw an ACCEPTED retrieval | Refused without custody resolution; with recorded, acknowledged resolution: task closed, ticket PARKED at recorded location/hook, valet released explicitly |
| AT-58 | Unclaimed car's key hook | Reserved across events until explicit audited release; unauthorized release denied |
| AT-59 | Supervisor console scope | Monitoring, shift start/end and exceptions in assigned events; no manual routine-dispatch control; valets have no console access |
| AT-60 | Duplicate or expired valet taps | Duplicate returns current outcome without second effect; expired/superseded rejected with stale message |

## Acceptance scenarios added 2026-11-17 (ADR-0011/0012; also listed in docs/06)

| ID | Scenario | Required outcome | Automated evidence |
|---|---|---|---|
| AT-61 | Intake to verified delivery entirely in the valet app | No staff message or token; customer messages unchanged | `tests/app/test_valet_api.py::test_full_journey_in_the_app_without_any_staff_whatsapp_message`; Playwright `valet-app.spec.ts` |
| AT-62 | Offer on screen: polling, refresh, second tab, late or lost acknowledgement | Read changes nothing; window starts once; never extended or past the hard limit; unacknowledged offer lapses at the hard limit | `tests/app/test_offer_shown.py`; `test_valet_api.py::test_unseen_offer_expires_at_the_hard_limit_and_is_reassigned` |
| AT-63 | Connection drops and returns | Banner at once; state unchanged; resumes from the server's step | Playwright `valet-app.spec.ts` (connection) |
| AT-64 | A valet's device stops working | Supervisor records for that valet only | `tests/app/test_operations_app.py`; Playwright `operations.spec.ts` |
| AT-65 | Customer WhatsApp down, staff app up | Staff keep working; assisted request/handover; stale messages OBSOLETE | Playwright `operations.spec.ts` (SIMULATED) |
| AT-66 | Customer help and Contact customer | Stored, one open alert, audited reveal, valets refused | `tests/app/test_operations_app.py`; Playwright `operations.spec.ts` (SIMULATED) |
| AT-67 | Three roles after migration | Audited reversible migration; per-role navigation and refusals | `tests/app/test_roles_and_onboarding.py`; Playwright `roles.spec.ts` |
| AT-68 | One-time setup code onboarding | Shown once, hashed, 72 h, five attempts, sessions end | `tests/app/test_roles_and_onboarding.py`; Playwright `roles.spec.ts` |
| AT-69 | One admin tries to get another admin's credentials in the app | Refused directly and through demote → reset → promote | `tests/app/test_admin_access.py`; Playwright `roles.spec.ts` |
| AT-70 | Controlled admin access | Two different people, reason, full reset, sessions end, visible record | `tests/app/test_admin_access.py`; `tests/console/test_mfa.py` |
| AT-71 | Main screens at 360/390/768/1024 px, both languages | No sideways overflow; screenshots reviewed | Playwright `layout.spec.ts` |
| AT-72 | Real phones and tablets | Manual checklist passes | docs/staging/real-device-checklist.md — NOT RUN |

## Acceptance scenarios added 2026-11-18 (ADR-0013; also listed in docs/06)

| ID | Scenario | Required outcome | Automated evidence |
|---|---|---|---|
| AT-73 | No receipt question | Photos → Start parking; nothing waits; no automatic CONFIRMED_IN_PERSON | `tests/app/test_message_status.py`; Playwright `valet-app.spec.ts`, `intake-location.spec.ts` |
| AT-74 | Message status and failure handling | Provider status only; one issue; resend rules; correction revokes | `tests/app/test_message_status.py`; Playwright `intake-location.spec.ts` (SIMULATED) |
| AT-75 | Phone entry | E.164; specific refusals; input kept; several tickets per number | `tests/core/test_phone.py`; `tests/app/test_intake_entry.py`; Playwright `intake-location.spec.ts` |
| AT-76 | Plate entry | As entered; order kept; no guessing; search either script | `tests/core/test_plate.py`; `tests/app/test_intake_entry.py`; Playwright `intake-location.spec.ts` |
| AT-77 | Possible duplicate | Shown before registering; override; later visits allowed | `tests/app/test_intake_entry.py`; Playwright `intake-location.spec.ts` |
| AT-78 | Location capture and fallbacks | Confirmed pins only; parking never blocked | `tests/app/test_parking_location.py`; Playwright `intake-location.spec.ts` (SIMULATED positions, map unconfigured) |
| AT-79 | Retrieval and relocation with the pin | Saved place first; link with coordinates only; old pin until completion | `tests/app/test_parking_location.py`; Playwright `intake-location.spec.ts` |
| AT-80 | Dashboards | Real data, empty states, phone and tablet, both languages | `tests/app/test_dashboards.py`; Playwright `layout.spec.ts`, `console.spec.ts`, `roles.spec.ts` |

## Coverage check
- Every docs/06 scenario AT-01…AT-34 appears at least once above; AT-61…AT-72 map to R-74…R-86 and AT-73…AT-80 to R-87…R-94 and amended rows. AT-35 is retired (ADR-0013).
- Every row has at least one test ID.
- **Extended Gate 2 set** (identical in `10_Build_Plan.md`):
  - docs/06 Gate 2 scenarios: AT-01–19, AT-32–34.
  - Phase 1 additions: AT-25, AT-26, AT-35 (retired 18 Nov 2026 by ADR-0013; replaced by AT-73/AT-74), AT-37, AT-38, AT-39, AT-42, AT-48 (database-role part), AT-49, AT-50 (simulated), AT-54, AT-55, AT-56, AT-57, AT-60, and AT-53/AT-59 limited to the live view.
- Everything else is Gate 3 or later.
