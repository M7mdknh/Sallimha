# Pilot usability improvements — plan and ledger (2026-11-18)

Source: user instruction of 18 Nov 2026 (seven points). Keeps ADR-0011/0012, three roles, brand, stack, safeguards.
Decisions go in ADR-0013. Executed inline (no subagents); TDD per task; ledger below survives compaction.

## Global constraints
- Server is the authority for phone and plate validation; frontend formats and hints only.
- No CONFIRMED_IN_PERSON set automatically; "sent" is never "delivered"; queued ≠ delivered.
- Photos before movement, explicit parking completion, task ownership, idempotency keys — unchanged.
- One customer number may have several tickets (no phone uniqueness on tickets).
- Maps: Google Maps JavaScript API via @vis.gl/react-google-maps, lazy-loaded; browser geolocation only; key served at
  runtime from server env (`GOOGLE_MAPS_BROWSER_KEY`, `GOOGLE_MAPS_MAP_ID`); missing key → "map not configured"
  label + structured fallback. No billing enabled, nothing purchased. Never invent coordinates.
- Plate: 17-letter Saudi set verified (Wikipedia, syarah.com): ا A, ب B, ح J, د D, ر R, س S, ص X, ط T, ع E, ق G, ك K,
  ل L, م Z, ن N, هـ H, و U, ى V; 3 letters + 1–4 digits. Letter correspondence in reading order is an assumption to
  confirm on a real plate (checklist); the plate is stored as entered; the other-script form is a search key/hint.
- No OCR, no continuous tracking, no new dispatch.

## Tasks
1. Phone: region selector + specific errors server-side (`guest_region`, possible-number reasons); PhoneField
   (libphonenumber-js) with SA default, country picker, as-you-type format, inline errors, input kept.
2. Plate: `core/plate.py` normalisation; Ticket `plate_kind` (SAUDI/OTHER/NONE), `plate_key`; migration; search by
   key; duplicate check (active tickets in the event) as a read + explicit confirm on register; PlateField.
3. Receipt removal: no receipt step for valets (endpoint removed), confirm_receipt not primary; message status
   (queued/sent/delivered/failed/unknown) from outbox on valet card and ticket detail; failure hook → one alert per
   ticket binding `guest_message_failed`; supervisor `resend_ticket`; phone-correction protection unchanged.
4. Location: Ticket floor/description/lat/lng/accuracy/source/captured_at; Venue lat/lng; park and relocation
   accept the pin; `GET /api/maps/config`; LocationPicker (geolocation states, lazy map, drag/tap, unconfirmed venue
   centre), retrieval display + Open in Google Maps; relocation keeps old until completion.
5. Intake in three stages: customer+vehicle (send), photos+start parking, location+hook.
6. Dashboards: admin overview (metrics row, hourly trend from real timestamps, team, problems, Add staff);
   supervisor Operations (queue by longest wait, problems first, plate/valet/elapsed, search, team, list/detail on
   tablet).
7. Docs/specs/walkthrough/ADR-0013/maps setup; e2e (mocked geolocation labelled SIMULATED); screenshots before/after;
   commit, push, CI.

## Ledger
- Before screenshots saved: docs/evidence/before-2026-11-18/ (from the bc7d8dd UI).
- bc7d8dd: CI 44092787216 success (backend, web, image, e2e). Inline security review of bc7d8dd: one finding (secrets to non-interactive output), fixed in 94dc893.
- 94dc893: review finding fixed (admin_access refuses non-interactive output).
- Tasks 1–5 backend done with tests (phone, plate, receipt/message status, location, dashboard data); ADR-0013 written.
- Ruling: plate cross-script display not shown (letter position correspondence unverified) — search key only — cost if
  wrong: a search in the other script may miss; nothing displayed is wrong.
- Ruling: Referrer-Policy changed same-origin → strict-origin-when-cross-origin (needed for website-restricted Maps
  key; origin only, never path) — cost if wrong: none for privacy of paths; covered by staging test.
- Ruling: chart is a 3-series line chart (hourly trend) not grouped bars (72 bars unreadable at 360 px); palette
  validated with the dataviz script, all pairs.
- Frontend: PhoneField, PlateField, Location (picker, view, lazy map), Register 3 stages, TaskCard, TicketPanel, Team
  form, Operations queue, Dashboard, venue centre form, simulator next-failure; e2e helper + intake-location spec.
