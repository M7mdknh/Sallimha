# WhatsApp outage

**Owner:** business — _to be named_; on-call technical — _to be named_.

## Signs
- Live view header shows WhatsApp other than "running/connected", or the opening check lists WhatsApp.
- Attention items "Offer not sent yet" or "Repeated unaccepted offers"; guests report no ticket message.
- Operations page fills with "Not delivered" or "Delivery unknown" rows.

## Immediately (supervisor)
1. Tell the team by radio that WhatsApp is degraded. Valets keep custody rules unchanged: every car and key
   stays with a named person.
2. Guests who cannot request by WhatsApp: open the ticket with **Find a ticket** and use
   **Supervisor-assisted request** (reason: "WhatsApp outage"). The request joins the normal queue.
3. At handover without a working code: **Supervisor-assisted handover**, choose how the guest was verified and
   write the reason. A valet cannot do this alone.
4. If an offer cannot reach a valet, assign work in person and record it with **Transfer custody** when a car
   or key changes hands.

## Technical (on call)
1. Check provider status *(provider)* and `/readyz` (`whatsapp` field). Check that the worker is running
   (live view "Worker").
2. Transient failures retry with backoff on their own. Permanent failures become dead letters.
3. Never bulk-resend. Messages marked **Delivery unknown** may already have arrived.

## After recovery
- Admin opens **Operations**: replay "Not delivered" rows that still matter; for "Delivery unknown", check with the
  recipient first and only then use **Send again anyway**.
- Open an incident (category: notification failure) summarising the window and affected tickets.
