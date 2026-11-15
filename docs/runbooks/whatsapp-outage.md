# WhatsApp outage

**Owner:** business — _to be named_; on-call technical — _to be named_.

## Signs
- Live view header shows WhatsApp other than "running/connected", or the opening check lists WhatsApp.
- Attention items "Offer not sent yet" or "Repeated unaccepted offers"; guests report no ticket message.
- Operations fills with "Not delivered" or "Delivery unknown" rows.

## What still works, and what does not
- **Works:** the console (live view, ticket finder, holds, incidents, notes), supervisor-assisted requests (the
  request keeps its place in the queue), supervisor-assisted handover for a car already marked ready, and
  withdrawal with custody resolution.
- **Does not work:** valets cannot receive or accept offers, mark a car ready, or confirm a custody transfer;
  guests receive no ticket or collection code. There is no manual dispatch control, by design. Messages are kept
  and retried; the queue keeps each request's original age, so offers resume in order when WhatsApp returns.

## Immediately (supervisor)
1. Tell the team by radio that WhatsApp is degraded. Every car and key stays with a named person.
2. Short outage: keep cars parked and tell waiting guests there is a short delay. Requests stay queued.
3. Guests who cannot request by WhatsApp: **Find a ticket** → **Supervisor-assisted request** (reason: "WhatsApp
   outage").
4. Longer outage with guests waiting: switch to the **agreed human continuity procedure** (to be written and
   agreed by the business owner before launch; docs/03): the supervisor dispatches by radio and keeps a paper log
   per car — ticket number, valet, key hook, time out, who verified the guest and how.

## Technical (on call)
1. Check provider status *(provider)* and `/readyz` (`whatsapp` field); check the worker is running (live view).
2. Transient failures retry with backoff on their own. Permanent failures become dead letters.
3. Never bulk-resend. Messages marked **Delivery unknown** may already have arrived.

## After recovery
- Admin opens **Operations**: replay "Not delivered" rows that still matter; for "Delivery unknown", check with the
  recipient first and only then use **Send again anyway**.
- Reconcile the paper log. **Open item:** the console has no action yet to record a delivery that happened on
  paper during an outage. Until it exists, record each such car as an incident (category "Notification failure")
  with the log line, and keep the ticket open for a manager decision. This needs a product decision before launch.
