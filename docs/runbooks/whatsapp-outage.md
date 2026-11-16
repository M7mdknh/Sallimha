# WhatsApp outage

**Owner:** business — _to be named_; on-call technical — _to be named_.

## Signs
- Live view header shows WhatsApp other than "running/connected", or the opening check lists WhatsApp.
- Attention items "Offer not sent yet" or "Repeated unaccepted offers"; guests report no ticket message.
- Operations fills with "Not delivered" or "Delivery unknown" rows.

## Report, then declare
1. The live view shows WhatsApp as **failing** when messages keep failing. The supervisor uses **Outages → Report a
   WhatsApp problem** (managers get a critical alert) and tells the team by radio. Every car and key stays with a
   named person.
2. A **manager** checks (provider status page, Operations) and uses **Outages → Declare WhatsApp outage** with the
   reason. Everyone sees a red banner; every open event gets a critical alert. Only a manager ends it.
3. While declared, the ticket panel offers **relayed** actions. Each asks how you confirmed it (in person / radio):
   - **Record valet's acceptance (relayed):** the system still chooses the valet ("Offered to: …"); radio that
     valet, and record their answer. You cannot pick someone else — that would be manual dispatch.
   - **Record car ready (relayed):** the accepted valet reports the car at the stand. Then use
     **Supervisor-assisted handover** and record how you verified the guest.
   - **Record custody received (relayed):** for a custody transfer the receiving valet confirmed in person.
   - **Record valet's acceptance** also applies to a move (relocation) offer.
4. New arrivals: **Outages → Record an intake for a valet** (valet, guest phone, plate, zone, spot, hook, how
   confirmed, reason). The car is recorded as parked by that valet; photos are excepted with your reason; the
   guest's WhatsApp ticket is queued and goes out when WhatsApp returns; their handover uses supervisor
   verification.
5. Guests who cannot request: **Supervisor-assisted request** (unchanged).
6. When messages flow again: a manager uses **Outages → End outage**. Queued messages go out by themselves; anything no
   longer true (an expired offer, a code for a car already handed over) is never sent (ADR-0010). Then, in **Operations**, replay
   messages that still matter; for "Delivery unknown", check with the recipient first.

## Whole system down (console unreachable) — continuity procedure
_The business owner must approve this procedure before launch._ Proposed, paperless:
1. The supervisor announces "system down" by radio with the time.
2. Each valet keeps an **offline log on their own phone** (notes app), one line per action:
   `time · ticket number (or plate if new) · action (received / parked / handed over / moved) · zone spot · hook ·
   who verified the guest and how`.
3. Nothing is handed over without a supervisor verifying the guest in person (photos/plate/description they can
   still recall or see on the car, the WhatsApp ticket on the guest's phone).
4. Keys stay on the board; a key off the board is always with a named person.

## After the system recovers (manager)
1. **Outages → Record outage window**: start and end in venue time (Asia/Riyadh for Saudi venues), in the past,
   at most 24 hours long and within 30 days.
2. For each car *received* during the window: **Reconcile an intake made during the outage** with the actual
   received and parked times, the valet, the evidence (the log line) and a reason.
3. For each car *handed over* during the window: open the ticket (**Find a ticket**) → **Reconcile a handover made
   during the outage**: actual time, the valet who handed over, the supervisor who verified the guest (someone
   other than you), method, evidence and reason. The ticket becomes Delivered at the actual time; the request and
   tasks close and the key hook is released at that time. A safety hold must be cleared first, with its reason.
4. The system refuses conflicts: times outside the window or before parking, a second reconciliation, or a ticket
   already delivered. Raise an incident only for genuine problems (damage, disputes) — never to stand in for the
   delivery record.
5. Check the opening check and **Operations** before resuming normal work.
