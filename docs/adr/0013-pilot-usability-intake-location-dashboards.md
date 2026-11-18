# ADR-0013 — Shorter intake, message status instead of a receipt question, phone and plate entry, parking location, dashboards

- Status: **Accepted 2026-11-18** (user instruction "usability improvements to the existing Sallimha pilot").
- Supersedes: the staff receipt confirmation as a normal intake step (ADR-0005 C3 as applied to intake, AT-35,
  R-05) and the six-step valet registration of ADR-0011 decision 6's app flow.
- Unchanged: ADR-0011 and ADR-0012 (three roles, controlled admin access, side-effect-free My work), photos before
  movement, explicit parking completion, task ownership, idempotency keys, custody, verified handover, holds, and the
  protection when a number is changed after a ticket was sent (supervisor correction revokes the old credentials).

## Decisions
1. **No receipt question.** The valet no longer asks whether the customer received the WhatsApp ticket, and no
   transition waits for that answer. `CONFIRMED_IN_PERSON` is never set automatically. A supervisor may still
   record it explicitly when it matters (after a phone correction); it is not a primary action on every ticket.
2. **Message status from the provider, not from staff.** The ticket shows the customer ticket message as queued,
   sent, delivered, read, failed or unknown, taken from the outbox row and the provider's status events (queued is
   not sent; sent is not delivered; DELIVERY_UNKNOWN is neither sent nor failed). A failed or dead customer message
   raises one supervisor issue per ticket and phone binding (`guest_message_failed`), deduplicated across the
   webhook failure and the outbox dead letter, with two actions: correct the number (existing, audited, revokes the
   old credentials) or resend the ticket message (supervisor, audited; refused unless the last attempt failed or is
   unknown). A ready-code message is never replayed: a new code is issued by the existing correction path.
3. **Phone entry.** The server stays the authority (`phonenumbers`), now with an explicit region (`guest_region`,
   ISO 3166 alpha-2, default SA) from a country selector, and specific refusals (too short, too long, invalid for
   the region, unknown country code). Arabic-Indic and Persian digits, spaces, hyphens, brackets and a `00` prefix are
   accepted; nothing is guessed or truncated; the canonical E.164 number is stored. The app formats as the valet
   types (libphonenumber-js), never blocks submission on its own opinion and shows the server's refusal inline with
   the input kept. A valid number is not claimed to be on WhatsApp or to belong to the customer. One number may have
   several tickets.
4. **Plate entry.** Saudi plates: three letters from the 17-letter set and one to four digits, entered as typed
   (Arabic or Latin letters; digit shapes normalised). Letter set and Arabic↔Latin equivalents were verified
   (Wikipedia "Vehicle registration plates of Saudi Arabia"; syarah.com plate guide): ا A, ب B, ح J, د D, ر R, س S,
   ص X, ط T, ع E, ق G, ك K, ل L, م Z, ن N, هـ H, و U, ى V. Neither source states how the letter positions of the two
   rows correspond, so **the preview shows only the script the valet entered** and the cross-script form is used only
   as an internal search key (reading order); a wrong order assumption can only miss a search match, never change
   the plate. Keyboard variants (أ إ آ → ا, ي → ى, ه → هـ) are normalised into the set; other letters are refused with
   a pointer to **Other plate**. Other plates (international, diplomatic, temporary) are stored as typed (spaces
   collapsed, Latin upper-cased). A missing or unreadable identifier is an explicit choice with a required
   description and reason. A possible duplicate (same plate key, still active in the same operation) is shown before
   registering, with the existing ticket number; registering anyway needs an explicit confirmation. Delivered or
   cancelled tickets never count, so later visits are not blocked.
5. **Parking location.** Zone and spot stay required; floor and a short description ("B1, beside pillar 12") are
   added. A pin is optional and only ever a confirmed one: from the browser's geolocation (with reported accuracy)
   or from the valet tapping or dragging the map. The venue centre is shown as "venue centre — not the car" and is
   never saved. Stored with the parking record: latitude, longitude, source (`gps` or `pin`), accuracy in metres
   (gps), the device-reported capture time and the server time it was recorded. Proposed defaults: a fix older than
   30 s is stale; accuracy above 50 m is shown as approximate (check the pin); above 150 m the fix is not saved
   unless the valet places the pin. Every writer of zone and spot sets or clears the pin (park, relayed park, move
   completion, custody resolution, outage reconciliation), so an old pin never outlives its place. A pin never claims
   a floor or indoor navigation.
6. **Maps.** Google Maps JavaScript API through `@vis.gl/react-google-maps`, loaded only on the parking stage and
   when the retrieval map is expanded. The browser key and Map ID come from the server at run time
   (`GOOGLE_MAPS_BROWSER_KEY`, `GOOGLE_MAPS_MAP_ID`, unset by default); without them the app says "map not configured"
   and the structured location, geolocation capture and Open in Google Maps link still work. Markers carry no
   customer identifier. No Geolocation API, billing or purchase. Real-map use stays BLOCKED until a key exists.
7. **Intake in three stages.** Customer and vehicle (Send ticket, with the formatted number beside the button);
   photos then Start parking; location, description and key hook then Parked. One primary action per stage.
8. **Dashboards.** Admin: the selected operation's period, four counts (parked, waiting, delivered, request-to-ready
   median), an hourly activity trend from real timestamps, team and unresolved problems, Add staff. Supervisor: the
   queue ordered by longest wait with problems first, plate, valet and elapsed time on each row, search and team at
   hand, list and detail side by side on tablets, stacked on phones. Technical checks move off the main view.

## Consequences
- AT-35 and R-05 are retired; new acceptance scenarios AT-73–AT-80 cover message status, phone, plate, duplicates,
  location fallback, retrieval and relocation with the pin, and the three-stage intake.
- The real-device checklist gains plate letter order, geolocation accuracy in the car park and Maps with a real key.
