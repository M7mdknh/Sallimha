# 02 — Roles, states and durable records

> **Roles after [ADR-0011](adr/0011-staff-app-and-three-roles.md):** VALET, SUPERVISOR, ADMIN. Every capability listed below for Manager, Admin or Super admin belongs to ADMIN (migrated with an audit record per person); nothing a manager could do moved to supervisors. Valets act in the staff app on their own task only. The current permission map is in ADR-0011; states and records are unchanged.

## Permission model
All console actions require authenticated staff, role permission and event scope. UI hiding is not authorization. Managers/admins inherit lower-role permissions unless specifically restricted. Valets operate through registered WhatsApp identity; they are not console administrators.

| Capability | Valet | Supervisor | Manager | Admin | Super admin |
|---|---|---|---|---|---|
| Intake, park, accept assigned work, ready, handover | Own task | Exceptional assistance | Exceptional assistance | Exceptional assistance | Exceptional assistance |
| Live event operations | Own work/status | Assigned events | All organization events | All | All |
| Add existing staff to event / start/end shifts | No | Assigned events | Yes | Yes | Yes |
| Create/edit events | No | No | Yes | Yes | Yes |
| Create/read/annotate incidents | Own task context | Assigned events | All | All | All |
| Resolve/close incidents | No | No | Yes | Yes | Yes |
| Exceptional request or verified handover | No | Assigned events; reason required | Yes | Yes | Yes |
| Cancel empty ticket | No | Assigned events; reason | Yes | Yes | Yes |
| Declare unclaimed and approve custody | No | Propose | Approve | Approve | Approve |
| Reports and filtered export | No | Live operational view only | Yes, no guest-phone bulk export | Yes | Yes |
| People directory / role grants | No | No | Only below manager | Only below admin | All; protect last super admin |
| Timings, templates, retention, public content | No | No | No | Yes | Yes |
| Guest-phone / subject data exports | No | No | No | Yes | Yes |
| WhatsApp credentials and connection | No | No | No | No | Yes |

Supervisor cancellation is preserved, limited to abandoned intakes before parking starts (see Transition rules). Manager approval for unclaimed custody is a **proposed strengthening** of the original guide. Supervisors monitor live operations, run shift operations and handle exceptions; they have no control for manually dispatching routine retrieval work. Exception assistance must not make routine supervisor dispatch necessary. Audit impersonation, overrides, exports and credential changes.

## Separate dimensions
Do not overload one status column to represent physical custody, work assignment, message delivery and incidents.

### Vehicle ticket lifecycle
| State | Meaning | Normal exit |
|---|---|---|
| RECEIVED | Registered; intake/parking task holds a valet. `parking_started_at` marks when the car first moves | PARKED (or CANCELLED only before parking starts) |
| PARKED | Location and key hook recorded; ready for retrieval | RETRIEVING after acceptance |
| RETRIEVING | Accepted retrieval; assigned valet responsible | READY |
| READY | At the handover point; assigned valet still responsible | DELIVERED |
| DELIVERED | Verified physical handover completed | Terminal |
| CANCELLED | Abandoned intake before parking started; staff confirmed the guest has vehicle and keys; reason recorded | Terminal |
| UNCLAIMED | Operating session ended with manager-approved continuing custody | Separate carryover case |

Display queued/offered badges from request state while vehicle remains PARKED. RECEIVED may have an early request, but cannot be auto-dispatched yet. Never cancel a car already held by the operator merely to remove a ticket.

### Retrieval request lifecycle
WAITING_FOR_PARKING → QUEUED → OFFERED → ACCEPTED → COMPLETED, with terminal WITHDRAWN reachable from any open state.

An expired/declined OFFERED becomes QUEUED. Reassignment does not change `requested_at`. ACCEPTED stays active through READY. Only explicit custody resolution permits transfer of an accepted task. A superseded offer is invalid forever.

Withdrawal (approved 15 Nov 2026) is an exceptional supervisor action with a reason. V1 has no guest cancellation button.
- From WAITING_FOR_PARKING / QUEUED / OFFERED: request → WITHDRAWN; any live offer is superseded and its reservation released; the vehicle stays PARKED (or continues parking) and the ticket stays open.
- From ACCEPTED: allowed only together with a supervised custody resolution that records the car and key location (or a named receiving valet) and is acknowledged. The retrieval task then closes with reason `custody_resolved`, the ticket returns to PARKED at the recorded location/hook, and only then is the valet released.
- Ticket cancellation (allowed only before parking starts) withdraws any open request with reason `ticket_cancelled`, cancels the intake task, releases its reservation, and revokes guest action references and collection credentials.
Preserve the withdrawal event and allow a later new request after withdrawal; the “one open request” constraint applies only to open states.

### Staff availability
Derived available = enabled staff + active event shift + available preference + no current live task/reservation. LIVE task statuses: RESERVED/OFFERED/ACCEPTED. A valet is busy during parking and from retrieval offer through physical handover. Break/unavailable requests are separate from task completion.

Intake reservation and retrieval reservation must contend on the same staff capacity constraint. A web dashboard or WhatsApp button cannot override a busy assignment without an explicit transfer.

### Contact and message state
Contact: UNCONFIRMED / CONFIRMED_IN_PERSON / CORRECTION_REQUIRED / ASSISTED_FALLBACK. CONFIRMED_IN_PERSON is set only by an explicit staff confirmation that the intended guest received the ticket. Since [ADR-0013](adr/0013-pilot-usability-intake-location-dashboards.md) no transition asks for it: UNCONFIRMED is the normal state, and a supervisor records CONFIRMED_IN_PERSON only after a phone correction. The staff app shows the ticket message's provider status instead; a failed or dead customer message raises `guest_message_failed` (one per ticket and binding).

### Vehicle identification and parking place (ADR-0013)
Plate kind SAUDI (three letters, one to four digits, stored as entered), OTHER (as typed) or NONE (description and reason required); `plate_key` is an internal search key, never displayed. Place: zone and spot (required), floor and a short description, and an optional confirmed pin (latitude, longitude, source `gps` or `pin`, accuracy for gps, device-reported capture time, server time recorded). The pin is whole or absent (database constraint) and is set or cleared with every write of zone and spot.
Message: PENDING / SENDING / SENT / DELIVERED / READ / FAILED / DELIVERY_UNKNOWN.
These do not substitute for the vehicle state. Provider “delivered” is not proof that the intended car owner controls the phone. Read receipts are optional; do not block operations awaiting READ.

### Incidents and safety holds
Incident: OPEN / IN_REVIEW / RESOLVED. Resolution requires manager+ and an outcome.
Safety hold: active reason, affected actions, author, clearance author/time. A hold may block dispatch or handover. Not every notification problem is a custody hold. An incident can remain open after an otherwise safe delivery.

## Transition rules
- All mutations include actor, scoped ticket ID, expected state/version and idempotency key.
- READY requires current accepted assignee. DELIVERED requires READY, identity verification, no active handover hold and actual delivery confirmation.
- A late “ready” from a superseded assignee fails cleanly; do not mutate or duplicate the audit event.
- `parked_by` is the valet who completes parking, not necessarily the registering employee.
- CANCELLED requires: ticket RECEIVED, `parking_started_at` empty, supervisor+ actor (or the intake valet before the ticket was sent), a reason and an explicit confirmation that the guest has the vehicle and keys. After parking starts the vehicle leaves only by DELIVERED or UNCLAIMED.
- Key occupancy is released only by verified delivery, an audited relocation of the key, or an explicit audited carryover release.
- State correction is a new authorized compensating action; never rewrite old history silently.
- Relocation is explicit with old/new location, mover and time. Proposed rule: supervisor initiates a relocation task; new retrieval waits until its custody is released.
- Disabling an employee blocks new access immediately but must open an unresolved-custody exception if they hold work. Preserve assignment history until a supervisor physically transfers responsibility. Do not silently mark them free.

## Minimum data model (proposed)
| Entity | Essential data |
|---|---|
| Organization / Venue | IDs, name, timezone, parking zones, key stations (venue-owned) |
| KeyOccupancy | key station, hook, ticket, occupied/released time, release actor and reason |
| Event | ID, venue, name, start/end, status, configuration snapshot |
| Staff / RoleGrant | ID, username if console user, normalized phone, enabled, roles, audit |
| EventAssignment / Shift | person/event, actual start/end, breaks/unavailable periods |
| Ticket | internal ID, event display sequence, vehicle details/raw description, guest binding revision, state/version, registered_by, parked_by, current location/hook |
| GuestBinding | ticket, encrypted/minimized contact data, provider identity if supplied, consent/confirmation metadata, revision |
| Media | object key, ticket/incident, actor, receipt time, capture time if supplied, hash, retention/hold metadata |
| Task | type intake/retrieval/relocation, ticket, assigned valet, generation, reservation expiry, acceptance/completion |
| RetrievalRequest | ticket, original requested_at, eligible_at, request state, latest task ID |
| AssignmentAttempt | candidate, offer generation, deadline, response, release reason |
| CustodyTransfer | from/to, vehicle/key responsibility, acknowledgements, reason, timestamps |
| Incident / Hold | category, ticket/event, evidence, status, assigned reviewer, resolution |
| Rating | ticket, delivering valet, rating, optional comment, deduplicated source |
| WebhookInbox / MessageOutbox | provider message/event IDs, payload hash/minimized data, status, attempts, next run, provider correlation |
| AuditEvent | immutable event ID, actor/channel, scope, entity, before/after summary, timestamp, correlation ID |
| CarryoverCase | unclaimed ticket, vehicle location, key location, custodian, recovery/release history |

## Database-enforced invariants
- Unique `(event_id, display_number)`; never use display number for authorization.
- At most one open shift per person.
- At most one live capacity-consuming task per valet and one live movement task per vehicle.
- At most one active retrieval request per ticket.
- At most one unreleased key occupancy per `(key_station_id, hook_number)`; key stations belong to the venue, so the constraint spans events and carryover cases.
- Unique logical inbound operation per provider message/action; repeated processing yields the same effect.
- Foreign keys and same-event validation for assignments, staff, tickets, incidents and exports.
- Audit app role cannot UPDATE/DELETE audit rows. Database owners still have administrative power; describe history as application-append-only, not magically tamper-proof.

## Reporting definitions
Requested → accepted: includes queue time and unanswered offers. Accepted → ready: retrieval execution. Ready → delivered: guest/handover wait. Received → parked: intake/parking. Preserve original timestamps through reassignment.

Report median and p95 by event plus total/failed deliveries, oldest queued request, available staff and unresolved incidents. Hour reporting uses actual shifts, shows breaks separately, and requires a policy decision before deducting break time from paid hours. Keep a neutral rating silent in live notifications but visible to authorized reporting users.

