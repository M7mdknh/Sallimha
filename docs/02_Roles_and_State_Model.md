# 02 — Roles, states and durable records

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

Supervisor cancellation is preserved; manager approval for unclaimed custody is a **proposed strengthening** of the original guide. Exception assistance must not make routine supervisor dispatch necessary. Audit impersonation, overrides, exports and credential changes.

## Separate dimensions
Do not overload one status column to represent physical custody, work assignment, message delivery and incidents.

### Vehicle ticket lifecycle
| State | Meaning | Normal exit |
|---|---|---|
| RECEIVED | Registered; intake/parking task holds a valet | PARKED |
| PARKED | Location and key hook recorded; ready for retrieval | RETRIEVING after acceptance |
| RETRIEVING | Accepted retrieval; assigned valet responsible | READY |
| READY | At the handover point; assigned valet still responsible | DELIVERED |
| DELIVERED | Verified physical handover completed | Terminal |
| CANCELLED | No vehicle was taken into custody; reason recorded | Terminal |
| UNCLAIMED | Operating session ended with manager-approved continuing custody | Separate carryover case |

Display queued/offered badges from request state while vehicle remains PARKED. RECEIVED may have an early request, but cannot be auto-dispatched yet. Never cancel a car already held by the operator merely to remove a ticket.

### Retrieval request lifecycle
WAITING_FOR_PARKING → QUEUED → OFFERED → ACCEPTED → COMPLETED.

An expired/declined OFFERED becomes QUEUED. Reassignment does not change `requested_at`. ACCEPTED stays active through READY. Only explicit custody resolution permits transfer of an accepted task. A superseded offer is invalid forever.

Withdrawal is an exceptional supervisor action before acceptance with a reason. V1 has no guest cancellation button. Preserve the withdrawal event and allow a later new request after withdrawal; the “one open request” constraint applies only to active states.

### Staff availability
Derived available = enabled staff + active event shift + available preference + no current live task/reservation. LIVE task statuses: RESERVED/OFFERED/ACCEPTED. A valet is busy during parking and from retrieval offer through physical handover. Break/unavailable requests are separate from task completion.

Intake reservation and retrieval reservation must contend on the same staff capacity constraint. A web dashboard or WhatsApp button cannot override a busy assignment without an explicit transfer.

### Contact and message state
Contact: UNCONFIRMED / CONFIRMED_IN_PERSON / CORRECTION_REQUIRED / ASSISTED_FALLBACK.
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
- State correction is a new authorized compensating action; never rewrite old history silently.
- Relocation is explicit with old/new location, mover and time. Proposed rule: supervisor initiates a relocation task; new retrieval waits until its custody is released.
- Disabling an employee blocks new access immediately but must open an unresolved-custody exception if they hold work. Preserve assignment history until a supervisor physically transfers responsibility. Do not silently mark them free.

## Minimum data model (proposed)
| Entity | Essential data |
|---|---|
| Organization / Venue | IDs, name, timezone, parking/key station configuration |
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
- At most one occupied active key slot per `(event_id, key_station_id, hook_number)`.
- Unique logical inbound operation per provider message/action; repeated processing yields the same effect.
- Foreign keys and same-event validation for assignments, staff, tickets, incidents and exports.
- Audit app role cannot UPDATE/DELETE audit rows. Database owners still have administrative power; describe history as application-append-only, not magically tamper-proof.

## Reporting definitions
Requested → accepted: includes queue time and unanswered offers. Accepted → ready: retrieval execution. Ready → delivered: guest/handover wait. Received → parked: intake/parking. Preserve original timestamps through reassignment.

Report median and p95 by event plus total/failed deliveries, oldest queued request, available staff and unresolved incidents. Hour reporting uses actual shifts, shows breaks separately, and requires a policy decision before deducting break time from paid hours. Keep a neutral rating silent in live notifications but visible to authorized reporting users.

