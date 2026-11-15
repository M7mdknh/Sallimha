# 01 — Final operating approach

## Status and intent
The business workflow below consolidates the five original operating guides, the user's sketch, their clarifications, and the process enhancements they approved. Detailed controls marked **Proposed default** are implementation choices for review, not claims about the old system.

Sallimha makes vehicle intake, parking, retrieval and handover traceable without paper tickets. Guests and valets primarily use WhatsApp. Supervisors and management use a responsive web console. A guest does not need an account, app installation or QR scan.

The service is organized around a venue/event and its active shifts. A venue may be a restaurant or a hall; an event represents an operating session at that venue. V1 is one operating organization with many venues/events, not a public multi-tenant SaaS marketplace.

## Approved changes from the documented baseline
| Area | Final intent |
|---|---|
| Guest identification | Ask for the guest's phone during registration; verify entered number and receipt |
| Guest ticket | Send WhatsApp ticket immediately after registration; QR is not required |
| Location | Record parking location as well as key-hook number |
| Retrieval | Automatically offer the task to the original parking valet if available, otherwise another available valet |
| Unanswered offer | Reassign after a configurable acceptance timeout |
| Fully busy team | Queue fairly and dispatch when capacity becomes available |
| Availability | Derived from tasks, shifts and break/unavailable state |
| Handover | Verify a collection code, with an audited supervisor fallback |
| Supervision | Monitor routine work and intervene on exceptions |
| Durability | Keep photos, audit history, duplicate protection and reliable recovery |

## 1. Prepare the operating session
The manager creates an event: name, venue/location, start time, time zone and team. A supervisor activates the assigned team's shifts. Assignment is planning; shift start is attendance. The employee may be assigned to future events but can have only one active shift at a time.

Proposed default: supervisors activate the shift, and valets mark themselves ready/unavailable without needing approval for each routine change. Break requests take effect only after current custody is released. The dashboard highlights assigned employees who have not started or who are unavailable.

At opening, check connectivity, WhatsApp integration health, parking-zone configuration, key-hook inventory and unresolved carryover vehicles. Do not present a healthy status if the worker or notification integration is down.

## 2. Receive and register the vehicle
The receiving valet starts “مركبة جديدة” while on shift and available. The system reserves that valet for intake and creates an internal ticket ID plus a short event-specific display number. It prompts for the guest phone explicitly; a phone number must never be mistaken for a key-hook number.

Normalize Arabic/Persian digits, preserve country code, validate format and show a masked confirmation. The guest is told that the number will receive their service ticket and updates; record the service messaging permission. International numbers are supported; do not force every guest into +966.

Proposed default: collect a plate identifier, optional make/color description and four intake photos. Require useful vehicle identification before ordinary intake completion; provide a reasoned supervisor exception for unusual cases rather than invented values. This tightens the old optional-description shortcut and is a proposed safety control.

The WhatsApp ticket is dispatched immediately after phone confirmation, without waiting for parking. At the counter, confirm the guest actually received the correct event/ticket. Provider delivery alone is not ownership verification. Store both messaging delivery status and staff-confirmed guest receipt separately.

Take front/right/rear/left photos before moving the car. Each photo records ticket, uploader and server receipt time. Store original media privately. A timestamp establishes receipt time, not cryptographic proof that the vehicle had not moved; staff workflow and training are also necessary.

If notification delivery is delayed, retain a visible “Guest contact unconfirmed” exception. Do not silently send personal details to a guessed number. Follow the documented contact exception flow without forcing the supervisor to intervene in every normal intake.

## 3. Park and confirm location
The valet parks, records a configured zone/row/space or venue-appropriate location, hangs the key on its numbered hook, and confirms “تم الركن”. Only then is the parking task complete and the valet available again.

The system remembers the actual parking valet as `parked_by`, separately from `registered_by`. The happy path uses the same person. If intake or parking is handed to another valet, record an explicit custody transfer so retrieval priority points to the person who actually parked.

Parking location and key-hook number are different fields. A proposed uniqueness constraint prevents two active tickets at the same event/key station from occupying the same key hook. Space-occupancy constraints depend on the venue layout; do not assume tandem parking is impossible.

Send a parked confirmation. If the guest requested the car before parking finished, retain the request as waiting for parking. Do not lose the request or dispatch a second valet to an unparked car. The ticket must reach a safe returnable state before normal retrieval starts.

## 4. Request the vehicle
The guest taps “اطلب سيارتي” in their WhatsApp ticket. Authenticate the sender against the ticket's guest binding and validate the opaque action reference. A display ticket number is never a credential.

One request is created. Repeat taps return its current status. If several cars share one phone number, use the selected ticket; a generic “my car” message must offer a choice rather than guess.

Confirm the actual state: “طلبك في الانتظار” when queued; “جارٍ إحضار مركبتك” only after a valet accepts. Do not claim retrieval has begun merely because the guest pressed a button. Avoid invented arrival estimates.

## 5. Assign and retrieve
Process eligible requests by oldest original request time. Select an available valet from the same active event: the original parking valet first, otherwise a fair alternative. A proposed fallback is longest-idle qualified valet with a stable tie-breaker.

Reserve the request and valet atomically, then send one targeted offer. This replaces the old all-valets broadcast. The offer contains ticket, vehicle identifier, location, key hook, acceptance control and expiry.

If declined or not accepted, release the reservation and requeue without resetting the guest's wait time. Temporarily exclude the nonresponding candidate from that request. Repeated failure raises a supervisor alert. If everyone is busy, wait in the queue.

After acceptance, the valet takes custody of the retrieval task, fetches the key and car, and marks “السيارة جاهزة” at the delivery point. The assigned valet remains busy through handover in V1. Separate handover attendants are out of scope unless later approved.

## 6. Verify and hand over
The guest receives the ready notification and a short collection code. The valet asks the guest to show or provide it, verifies it in the ticket's active handover interaction, and confirms physical delivery.

Proposed default: six random digits, ticket-bound, rate-limited, stored as a keyed verifier, invalid after successful delivery or credential reset. Verify guest/ticket/car together. A forwarded code or display number alone is insufficient when identity is disputed.

If the phone is unavailable, the supervisor conducts human ownership verification and records the reason, verifier and outcome. Do not collect identity-document photos as a routine requirement. If a hold or identity dispute remains unresolved, do not release the vehicle.

Close only after actual handover. Record actor/time, consume credentials, release valet/key hook/location occupancy and send the rating request.

## 7. Feedback and incident handling
Excellent: record and notify the delivering valet. Neutral: record silently. Poor: immediately alert the event supervisor and create a complaint incident linked to the ticket. Management can review all ratings; no poor-rating reprimand is automatically sent to the valet.

Incidents include missing vehicle, key issue, damage, identity dispute, notification failure and operational delay. Keep vehicle state truthful while investigating. Supervisors can create, view and annotate incidents; only manager or higher resolves/closes them with a written outcome. Safety holds are explicit and audited.

## 8. End the event
Supervisors end shifts only when active tasks and custody are cleared or explicitly transferred. Managers close the operating session after reconciliation. Cancelled empty tickets, delivered vehicles, and unclaimed vehicles are distinct outcomes; never simulate delivery to clear a dashboard.

Proposed default: unclaimed vehicles require a manager-approved custody plan and named custodian before shift/event closure. They remain visible in a carryover register. Closing the operating ticket does not mean the operator has ceased holding the car.

## Preserved administrative capabilities
- Unified people directory; deactivate rather than delete historical staff records.
- Username/password console login; WhatsApp staff identity uses a registered number. Protect privileged console accounts with MFA as a proposed security requirement.
- Working hours measured from actual shift start/end, not assignment. This is a payroll input report, not a payroll processing engine.
- Event, shift, wait-time, incident and satisfaction reports; exports respect active filters.
- Admin configuration of timings, message copy, public information and retention. Changing button wording must not change its operation.
- Guest-phone exports restricted to admin or super admin. Media exports are separate from CSV and remain access-controlled.
- WhatsApp account/credential management restricted to super admin.

## V1 boundaries
No payments, tipping, subscriptions, customer app, dynamic pricing, plate-recognition AI, route optimization, GPS staff surveillance, marketing campaigns or public SaaS onboarding. A simple informational page may be included after operational flows. Core processing must work without generative AI.

