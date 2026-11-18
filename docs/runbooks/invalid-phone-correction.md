# Invalid guest phone number

**Owner:** business — _to be named_.

## Signs
- The guest says they did not receive the ticket, or the valet typed the number wrong.
- The ticket shows its message as *not delivered*, and Problems shows "A customer message was not delivered" (one
  per ticket at a time; ADR-0013).

## Steps (supervisor)
1. Find the ticket (**Find a ticket**, by number or plate) and open it.
2. Confirm the right number **with the guest in person**. Never accept a correction from a phone call or a
   message from another number.
3. Use **Correct guest number**, enter the number and the reason. The old link and collection code are revoked
   and a new ticket message is sent to the new number.
4. If the number was right but the message failed or is unconfirmed, use **Resend the ticket** instead (for
   *unconfirmed*, ask the guest first: it may have arrived). A failed collection-code message is fixed by
   correcting the number, which issues a new code.
5. Once the guest shows the ticket on their phone, you may record **Confirm the guest received the ticket** (only
   offered after a correction). There is no routine receipt question for valets (ADR-0013).

## Notes
- A request arriving from an unbound number raises "Request from an unbound number". Treat it as a possible
  identity issue ([identity-dispute.md](identity-dispute.md)), not as a phone correction.
- The phone is stored encrypted and shown masked; only the admin export includes it, and it is audited.
