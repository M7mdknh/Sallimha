# ADR-0011 — Staff web app, customer-only WhatsApp and three roles (small-team pilot)

- Status: **Accepted 2026-11-17** (user mandate "focused redesign for a small-team pilot").
- Supersedes: the requirement that valets work only in WhatsApp (docs/01, ADR-0006) and the five-role ladder
  (docs/02). ADR-0006 remains as the record of the retired valet WhatsApp contract; ADR-0007, 0008 and 0010 keep
  their rules with the channel changes below.
- Unchanged: PostgreSQL as the source of truth, the worker, the outbox, private media, one open request per ticket,
  one live task per valet (offers count), key-hook occupancy, atomic assignment and lock order, idempotency, audit,
  object scope, explicit custody transfer, verified handover, safety holds, separate vehicle / request / task /
  message states.

## Decisions
1. **Channels.** Customers use WhatsApp only (ticket, request button, status, collection code, rating, help).
   Valets and supervisors use the web app on a phone or tablet. No staff action depends on a WhatsApp message being
   sent, delivered or answered.
2. **One implementation.** The valet app calls the same `ops.services` functions the WhatsApp flow called
   (`intake`, `dispatch`, `handover`, `relocation`, `custody`, `shifts`). Token-free entry points sit beside the
   token ones and share the same state changes and locks.
3. **`STAFF_CHANNEL`** (`app` by default, `whatsapp` = the retired flow). In `app` mode: no message is queued to a
   staff member, no staff action token is issued, every inbound WhatsApp message is treated as a customer's, and an
   offer's response window starts when the valet's app first shows it (it used to start when WhatsApp accepted the
   message). The hard limit from reservation is unchanged, so an unseen offer is still released and reassigned.
   The retired flow stays in the code, covered by its existing tests, until the pilot confirms it can be deleted.
4. **Roles: VALET, SUPERVISOR, ADMIN.** MANAGER, ADMIN and SUPER_ADMIN become ADMIN through a data migration that
   also writes one audit record per person. Everything that needed manager or above now needs ADMIN; nothing that
   needed a manager becomes available to supervisors. The second factor is required for ADMIN. The framework
   superuser flag is never set or read by the product.
5. **Valet access.** A valet signs in to `/api/valet/*` only: their own shift, their own task and the ticket it
   belongs to, with the customer's number masked. Every console endpoint still requires SUPERVISOR or ADMIN.
6. **Onboarding without shared credentials.** An admin adds a person (name, mobile, role) and receives a one-time
   setup code (shown once, stored hashed, 72 hours, five attempts). The person sets their own password with it.
   Re-issuing a code is also the password reset. Admins still need the admin-issued second factor.
7. **Staff connectivity loss** replaces "WhatsApp outage" as the reason for relayed actions. A supervisor marks one
   valet's device as not working (reason recorded); only then may the supervisor record that valet's acceptance,
   car ready, custody receipt, intake photos and parking, each with how it was confirmed (ADR-0008 rules otherwise
   unchanged: the system still chooses the valet).
8. **Customer WhatsApp outage** no longer changes how staff work. Admins declare and end it, supervisors report
   it; while it is open the app tells staff that customers are not receiving messages, and supervisors use the
   existing assisted request and assisted handover. Queued customer messages follow ADR-0010.
9. **Whole-system outage**: unchanged (offline log, recorded window, reconciliation by an admin).
10. **Customer contact.** A customer's free-text message raises a "customer needs help" item for the event team
    and is stored on the ticket. "Contact customer" in the ticket view reveals the number to a supervisor or admin
    for a call or a WhatsApp chat from their own device; the reveal is audited. That contact happens outside
    Sallimha and is labelled so. Sallimha does not offer a typed reply: WhatsApp allows free text only inside the
    24-hour window, and that needs real-provider verification first.
11. **Not in the pilot:** offline sync, push notifications, supervisors doing valet work from the same account,
    manual dispatch.

## Screens: current → new
| Current | New | Who |
|---|---|---|
| Valet WhatsApp conversation | **My work** (`/work`): current task card, availability, recent work | VALET |
| "New car" WhatsApp flow | **Register car** (`/register`): number + vehicle → confirm and send ticket → 4 photos → receipt → start parking → zone, spot, hook | VALET |
| Offer / ready / code / delivered buttons in WhatsApp | The task card on My work: accept → car ready → code → delivered; moves and custody acknowledgements too | VALET |
| Events list, Live operations | **Operations** (`/operations`): opens the active operation; waiting, retrieving and ready cars with elapsed time, search, problems | SUPERVISOR, ADMIN |
| Ticket panel (all actions listed) | **Ticket detail**: one primary next action, the rest under More actions, Contact customer | SUPERVISOR, ADMIN |
| Incidents, Carryover, Outages (top-level) | Tabs inside Operations | SUPERVISOR, ADMIN (approvals: ADMIN) |
| Team card on Live; Staff page | **Team** (`/team`): tonight's shifts, availability and workload; device-not-working; admins also add, activate, deactivate and assign people | SUPERVISOR, ADMIN |
| Report page | **Dashboard** (`/dashboard`): parked, waiting, delivered, request-to-ready time, delayed, problems, team; full report and exports | ADMIN |
| Events (management), Settings, Operations (messages), Integrations | **Settings** (`/settings`): operation and venue, timings, wording, retention; Advanced: message delivery, WhatsApp status, simulator (development only) | ADMIN |

## Permissions: current → new
| Action | Was | Now |
|---|---|---|
| Register, photograph, park, accept, ready, verify code, deliver, move, acknowledge custody | Valet in WhatsApp | VALET in the app (own task only) |
| Availability / break | Valet in WhatsApp | VALET in the app |
| Start / end shift, add an organisation valet to tonight's team | Supervisor | SUPERVISOR |
| Cancel before parking, intake exception, intake transfer, correct number, assisted request / handover, withdraw, custody transfer, relocate, hold, incident, propose unclaimed | Supervisor | SUPERVISOR |
| Mark a valet's device as not working; relay for that valet | Supervisor during a declared WhatsApp outage | SUPERVISOR, for a marked valet |
| Contact customer (reveal number) | — | SUPERVISOR (assigned events), ADMIN; audited |
| Report a customer WhatsApp outage | Supervisor | SUPERVISOR |
| Declare / end the outage, record a system outage, reconcile | Manager+ | ADMIN |
| Approve unclaimed, release carryover, resolve incident | Manager+ | ADMIN |
| Create / close event, reports, ticket export | Manager+ | ADMIN |
| Add people, roles, deactivate, setup codes | Manager+ (by rank) | ADMIN |
| Second-factor issue, settings, retention, message replay, phone export | Admin+ | ADMIN |
| WhatsApp integration status | Super admin | ADMIN |
| See all events of the organisation | Manager+ | ADMIN (supervisors and valets: assigned events only) |

## Consequences
- **People who were managers gain what only admins or the super admin could do**: settings, data retention, message
  replay, the customer-number export and WhatsApp status. That is what consolidating the roles means; the migration
  records each person's previous role, and the list of admins should be reviewed after it runs.
- Valet passwords need 8 characters or more (supervisors and admins keep 12): they are typed on a phone at the
  start of a shift. Sign-in attempts are limited for every role.
- Valets need a signed-in phone with the app open during the shift; an assignment appears on the task card (with an
  optional sound) and is never delivered only by a notification.
- WhatsApp message volume and template count drop to the customer set (docs/staging/whatsapp-onboarding.md).
- A supervisor who also parks cars needs a second, valet account in this pilot.
