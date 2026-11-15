# ADR-0005 — Specification gaps and conflict resolutions

- Status: **Accepted 2026-11-15** (user decisions recorded below; docs/01, 02, 04, 06, 07 updated to match)
- Date: 2026-11-15

## C1 — Venue-owned key hooks (accepted)
Key stations belong to the venue. Occupancy is unique on `(key_station_id, hook_number)` while unreleased, across events. It survives event closure and remains reserved for an unclaimed vehicle until an explicit, audited release. Release paths: verified delivery, audited key relocation, explicit carryover release (manager+). Tests: AT-33, AT-43, AT-58.

## C2 — Withdrawal and cancellation cascade (accepted)
- Retrieval request gains terminal `WITHDRAWN` (actor, reason, time).
- Withdrawal from WAITING_FOR_PARKING/QUEUED/OFFERED: request withdrawn, live offer superseded (its action references die), reservation released; vehicle stays PARKED and the ticket open; the guest may request again.
- Withdrawal after ACCEPTED: only with supervised custody resolution — recorded car/key location (back to a location and hook, or handed to a named valet) plus acknowledgement — after which the task closes as `custody_resolved`, the ticket returns to PARKED, and the valet is released explicitly. Never silent.
- Ticket cancellation (C4 conditions) withdraws any open request (`ticket_cancelled`), cancels the intake task and releases its reservation, revokes action references and codes, and informs the guest if a ticket was sent.
Tests: AT-54, AT-56, AT-57.

## C3 — Explicit receipt confirmation (accepted)
After the ticket is sent the intake conversation asks “هل ظهرت التذكرة على جوال الضيف؟” — [نعم، استلمها] / [لم تصل]. Only “yes” sets CONFIRMED_IN_PERSON. Provider delivery/read never does. “No” or no answer keeps the visible exception; intake continues. Test: AT-35.

## C4 — Cancellation cutoff (accepted, user wording)
Use actual operations as the cutoff. The intake conversation has an explicit “بدء الركن” operation (recorded as `parking_started_at`) before the car moves. An abandoned intake may be cancelled only **before parking starts** and **after confirming the guest has their vehicle and keys**. Once parking begins, returning the vehicle requires the normal retrieval and verified handover process. Withdrawing a retrieval request is a separate action (C2). Who may cancel: supervisor+ with reason; the intake valet may abandon a draft only before the ticket was sent, with the same confirmation. Tests: AT-24, AT-55.

## C5 — Valet WhatsApp contract
Accepted as ADR-0006.

## C6 — Shift start (accepted)
Supervisor activates the shift in the console; the valet's “جاهز” sets availability and opens a service window. A valet cannot start their own shift.

## C7 — Collection-code delivery
The READY message is sent as a session message when the guest's window is open (a request tap is an inbound user message). If a template is needed, its category is settled at template submission in staging. See `11_WhatsApp_Platform_Verification.md`.

## C8 — WhatsApp media
“Original media” = the file as received from the provider, hashed; `capture_time` null unless supplied.

## C9 — Font inheritance fix (accepted; identity unchanged)
`tokens.css` stacks become cross-script (`"Noto Sans Arabic","Noto Sans",sans-serif` and the reverse) and language rules apply from `html[lang]`, so Arabic never falls back to a system font. Verified on mobile and desktop widths with Playwright.

## C10 — Brand nits
DESIGN.md governs line heights; type scale and status tints are added to tokens at UI build with contrast checks; `logo-en.svg` label left unchanged for now (asset change deferred to the identity owner).

## C11 — Minimal console in Phase 1; supervisor clarification
The supervisor console supports live monitoring, shift operations and exception handling. It has no manual routine-dispatch control (AT-59).

## C12 — Kickoff file
Not recreated.
