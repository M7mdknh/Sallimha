# Dead-letter replay

**Owner:** on-call technical — _to be named_; admin on duty.

## Signs
- Opening check counts messages needing attention.
- **Operations** lists rows marked **Not delivered** (permanent failure) or **Delivery unknown** (the request
  reached the provider but the answer was lost).

## Steps (admin)
1. Open **Operations**. Each row shows the message type, ticket, recipient (staff name or "guest") and the
   failure class.
2. **Not delivered:** fix the cause first (for example a template not approved, or a number that cannot
   receive WhatsApp). Only customers receive messages; staff work in the app. Then **Send again**. The same message row is re-queued once; a second replay does nothing.
3. **Delivery unknown:** ask the recipient whether it arrived. Only if it did not, choose **Send again**, then
   **Send again anyway**. This may duplicate a message, which is why the worker never does it automatically.
4. If the message is no longer relevant (the guest already left), leave it and note it in an incident.

## Evidence
Each replay is audited (`outbox.replay`, with the previous status). Replays only affect your organisation's
messages.
