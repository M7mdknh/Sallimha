# Outages: customer WhatsApp, a staff device, the whole system

**Owner:** business — _to be named_; on-call technical — _to be named_.

Since ADR-0011 staff work in the web app and only customers use WhatsApp. Three different failures, three procedures.

## 1. Customer WhatsApp down (the staff app works)
**Signs:** Operations shows "customer messages are not getting through"; valets' screens say customer messages are
delayed; customers say they have no ticket or code; Settings → Advanced → Message delivery fills with "not delivered"
or "delivery unknown".

1. Staff **keep working in the app** as usual: registering, parking, accepting offers, car ready all work.
2. The supervisor uses Operations → **Outages → Report** (admins get a critical alert) and tells the team by radio.
3. An **admin** checks the provider status page and Message delivery, then **Declare** with the reason. Everyone sees
   the banner. Only an admin ends it.
4. A customer at the stand without their ticket: open the car (search by plate) → **Assisted request**.
5. A ready car whose customer has no code: **Assisted handover**, recording how you verified the customer.
6. **Contact customer** opens the number for a call from your phone if needed (audited; the call is outside Sallimha).
7. When messages flow again an admin **Ends** the outage. Queued messages go out by themselves; anything no longer true
   (an expired offer, a code for a car already handed over, a ticket for a delivered car) is never sent (ADR-0010).
   In Message delivery replay what still matters; for "delivery unknown", check with the customer first.

## 2. One valet's device not working
**Signs:** the valet tells you; "offer not yet shown on the valet's device" in Problems for that valet.

1. **Team** → the valet → **Device not working**, with the reason (battery, lost phone…). The team row shows
   "supervisor records for them".
2. On that valet's ticket the primary action becomes the record you need, each asking how you confirmed it
   (in person / radio): **Record the valet's acceptance** (the system still chose the valet — never pick someone
   else), **Record car ready**, **Record custody received**, **Add intake photo**, **Record parked for the valet**.
3. A new arrival for that valet: Team → **Register a car for a valet whose device is down**. The car is registered in
   their custody, not parked; add the photos on the ticket (or an intake exception with the reason), then record
   parked with zone, spot and hook.
4. Customer handover without the valet's phone: **Assisted handover**.
5. When the device works again: **Device working again**. The valet carries on in the app from the server's state.

## 3. Whole system down (app unreachable) — continuity procedure
_The business owner must approve this procedure before launch._ Proposed, paperless:
1. The supervisor announces "system down" by radio with the time.
2. Each valet keeps an **offline log on their own phone** (notes app), one line per action:
   `time · ticket number (or plate if new) · action (received / parked / handed over / moved) · zone spot · hook ·
   who verified the customer and how`.
3. Nothing is handed over without a supervisor verifying the customer in person (plate, description, photos they can
   still see, the WhatsApp ticket on the customer's phone).
4. Keys stay on the board; a key off the board is always with a named person.

### After the system recovers (admin)
1. Operations → **Outages → Record outage window**: start and end in venue time (Asia/Riyadh for Saudi venues), in the
   past, at most 24 hours long and within 30 days.
2. For each car *received* during the window: **Reconcile an intake made during the outage** with the actual received
   and parked times, the valet, the evidence (the log line) and a reason.
3. For each car *handed over* during the window: open the ticket → **Reconcile a handover made during the outage**:
   actual time, the valet who handed over, the supervisor who verified the customer (someone other than you), method,
   evidence and reason. A safety hold must be cleared first, with its reason.
4. The system refuses conflicts: times outside the window or before parking, a second reconciliation, or a ticket
   already delivered. Raise an incident only for genuine problems — never to stand in for the delivery record.
5. Check the readiness check and Message delivery before resuming normal work.
