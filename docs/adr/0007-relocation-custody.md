# ADR-0007 — Relocation custody

- Status: **Accepted 2026-11-16** (review finding; supersedes the Phase 2 relocation behaviour).
- Requirement basis: docs/02 ("Relocation is explicit with old/new location, mover and time"; "Key occupancy is
  released only by verified delivery, an audited relocation of the key, or an explicit carryover release"),
  docs/03 rule 2 (movement-blocking holds), CLAUDE.md custody rules.

## Problem found in review
Starting a relocation created the task already **ACCEPTED** with no action by the valet, and a supervisor could
record it **completed** while it was still only assigned. The record could therefore say a valet moved a car they
never touched, and the confirmed location could change before anything moved. Relocation offers also never
expired, and a movement-blocking safety hold did not stop a move.

## Decision
1. **Start = offer.** A supervisor chooses the valet (relocation is an exception action, not routine dispatch). The
   task is `OFFERED` with a deadline (`hard_limit_s`), counts as the valet's one live reservation, and the valet
   gets a WhatsApp offer with Accept / Decline. The ticket's location and key hook do not change. Refused when a
   hold blocks movement (`hold_active`) or the ticket is not parked.
2. **Accept = custody.** The valet's acceptance (WhatsApp, or a supervisor relaying it during a declared WhatsApp
   outage — ADR-0008) moves the task to `ACCEPTED`. Like a retrieval, the key's hook stays reserved for the car
   until the move completes.
3. **Complete = new confirmed location.** The mover taps "Moved" and sends the new zone/spot and hook, or a
   supervisor records it having confirmed it in person or by radio (`confirmed_via`). Completion is refused before
   acceptance (`not_accepted`). The mover is always the accepting valet; the recorder is stored separately. The old
   hook is released with reason `relocated` and the new one occupied by the mover.
4. **Decline / expiry** release the reservation and raise a `relocation_declined` alert. No automatic reassignment.
5. **Cancel.** An offered move is withdrawn freely. An accepted move requires the supervisor to confirm the car
   and key are back at the recorded location and hook (`custody_resolution_required` otherwise).
6. Retrieval waits while a move is live (unchanged).

## Consequences
New WhatsApp messages (`valet.relocation_offer`, `valet.relocation_accepted`, `valet.relocation_done`,
`valet.relocation_cancelled`) need approved utility templates for use outside the 24-hour window (staging input).
