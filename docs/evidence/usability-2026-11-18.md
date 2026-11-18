# Evidence: pilot usability (ADR-0013), 18 Nov 2026

Branch `build/phase-0-2`. These are local runs plus CI on the pushed commit; nothing is deployed.
- **WhatsApp results:** PASS (SIMULATED), from the development simulator.
- **Location results:** SIMULATED. Positions come from Playwright's emulated geolocation or a scripted stub, and
  no Google Maps key was configured. This is not a real-device Google Maps rehearsal; that is BLOCKED (see below).

## Review of `bc7d8dd` (outstanding from 17 Nov)
- **CI:** run 44092787216 passed (backend, web, image, e2e).
- **Commit hook:** the automatic security review did not run (HTTP 429). Commit and push were one command, so a later
  push does not re-check it.
- **Inline review:** one finding. `manage.py admin_access` printed the setup code and second-factor link even when its
  output was not a terminal (a one-off job or a pipe can keep that output in logs). Fixed in 94dc893: it now refuses
  unless `--allow-non-interactive` is passed, with a test and a runbook line. No other findings.
- **Visual check:** the admin row note on Team renders correctly in Arabic.

## What changed, and the proof
| # | Change | Automated proof |
|---|---|---|
| 1 | **Dashboards.** Admin: the operation and its period; one band of four counts (parked, waiting with the oldest wait, delivered, request-to-ready median with its definition); activity by hour from recorded times, with a stated empty state; problems; team; Add staff. Supervisor: search at the top; problems first; one queue ordered by the longest wait, with plate, description, valet, place and hook, and *late* / *very late* in words; stage filters; team in the header; counts in one line; the opening check shown only when something needs attention. | `tests/app/test_dashboards.py` (queue fields, hourly series, empty state); Playwright `console.spec.ts`, `layout.spec.ts`, `roles.spec.ts`; before and after screenshots below |
| 2 | **No receipt question.** The ticket message's provider status (queued, sent, delivered, read, failed, unknown) is shown to the valet and the supervisor. A failed or dead message raises one issue per ticket and binding, with *correct number* and *resend*. `CONFIRMED_IN_PERSON` is never set automatically. | `tests/app/test_message_status.py` (7); Playwright `intake-location.spec.ts` test 3 (simulated failure, issue, resend) |
| 3 | **Phone entry.** A country selector (Saudi Arabia by default). The app formats as the valet types (libphonenumber-js 1.13.15), and the server decides (`phonenumbers`), with specific refusals and the input kept. One number may have several tickets. | `tests/core/test_phone.py` (+16 cases); `tests/app/test_intake_entry.py`; Playwright test 1 (refusal keeps the input; Arabic digits with a space and a hyphen read as +966 50 123 9881) |
| 4 | **Plate entry.** Saudi plates are kept as entered (verified 17-letter set). Other plates are kept as written. No readable plate needs a description and a reason. Search uses a normalised key in either script, and a possible duplicate is flagged before registering. | `tests/core/test_plate.py`; `tests/app/test_intake_entry.py`; Playwright tests 1 and 2 (letter order right-to-left in Arabic and left-to-right in Latin; a duplicate typed in the other script is caught before anything is registered) |
| 5 | **Parking place.** Zone and spot are required; floor and a short description are added. An optional confirmed pin is saved with its accuracy, source, device time and server time. The venue map centre is set by an admin. The Maps JavaScript API is lazy-loaded with a run-time key. The referrer policy sends the origin only. | `tests/app/test_parking_location.py` (13); `tests/staging/test_console_serving.py`; Playwright tests 1–3 (denied, too coarse at ±400 m, stale cached fix, good fix at ±12 m, map not configured, retrieval link `…query=24.764712%2C46.640312`) |
| 6 | **Intake in three stages.** Customer and car (send); photos then Start parking; place, description and key hook. | Playwright `valet-app.spec.ts` (journey, double tap, second tab), `registerAndPark` in every spec |

## Results
| Check | Result |
|---|---|
| Backend (`pytest`, staff channel = app), final | **592 passed** |
| Retired valet-WhatsApp channel (`-m whatsapp_staff`, `SALLIMHA_TEST_ALL_LEGACY=1`) | **82 passed** |
| Browser, full suite (Playwright, installed Chrome, desktop and mobile projects), run 6 after the review fixes | **42 passed, 0 failed, 12 skipped** (desktop-only tests with explicit device sizes) |
| After run 6 (chart scroll and tooltip only) | A one-off check against `make demo` (synthetic hours): no page overflow at 390/768/1024; the tooltip stays inside the card at both ends in Arabic and English. CI runs the full suite on the final commit. |
| Earlier runs, for the record | Run 2: 31 passed, 10 failed (old selectors and knock-on effects). Run 3: 39 passed, 2 failed (the layout test's offer lapsed during its slow screenshot loop: the test now lengthens the offer window through the admin timings API and restores it; one knock-on). All fixed before run 4. |
| Ruff, TypeScript type check, production build, contract regenerated (`--fail-on-warn`) | PASS |
| Bundle | Entry chunk 579 kB → 317 kB (gzip 160 → 99 kB) after splitting at the role boundary; the map chunk (49 kB) loads only when a map is opened |

## Screenshots
- Before: [before-2026-11-18/](before-2026-11-18/) (the bc7d8dd interface: `<lang>-<width>-<screen>.png`).
- After: [screens/](screens/) (`<lang>/<width>-<screen>.png`, 360/390/768/1024 px, Arabic and English), including the
  parking stage (`valet-park`). The chart with data (`*-admin-dashboard-activity.png`) was taken from `make demo`,
  whose synthetic seed spreads arrivals over three hours; the test database starts empty, so the chart there shows
  its empty state. The layout test
  lengthens the offer window for itself, so the valet offer screenshots show a longer countdown than the 30 s default.

## Interface review
- **Web Interface Guidelines** (vercel-labs, fetched 18 Nov) on the new files: three findings, all fixed. Add staff is
  now a real link; the chart's keyboard focus is visible; the pin's Remove button has a specific name.
- **React performance guidance:** bundle split at the role boundary and the map lazy-loaded. Nothing else applied:
  polling only re-renders small lists, and no component is defined inside another.
- **Visual review** at 360–1024 px in both languages found and fixed:
  - a status pill overflowing at 360 px;
  - stage filters wrapping onto three lines on phones;
  - a cut-off search placeholder;
  - an uneven metrics band;
  - Arabic times whose AM/PM word was misplaced inside left-to-right identifiers (times are now 24-hour in both
    languages).

## Fixed after the advisor's final review (before the last runs)
- **Repeat failures:** a ticket message that fails again after a resend now raises a new issue; one open issue per
  ticket. Test: `test_a_message_that_fails_again_after_a_resend_raises_a_new_issue`.
- **Copy:** "unconfirmed" says "tell the supervisor", since no issue is raised for it. The issue label says
  "check the number", since a failed collection code is fixed by a correction, not a resend.
- **Lazy loading:** the valet app, the console and the map are wrapped in an error boundary; a failed download shows
  the retry state. Playwright aborts the valet chunk and checks the retry.
- **Stale positions:** judged once, when the position arrives. An accepted pin no longer turns "old" on screen.
- **Team form:** a possible duplicate shows the existing ticket with Open and "a different car — register it".
  Server test `test_the_team_form_for_a_valet_without_a_device_catches_duplicates_too`. The panel itself is not
  browser-tested.
- **Map load failure:** browser-tested with a dummy key and Google's address blocked. Nothing was sent to Google
  (SIMULATED).
- **Seed and runbook:** the demo seed no longer answers the receipt question. The phone-correction runbook was updated.

## Not verified here
- Tapping or dragging the pin on a real map: NOT RUN (needs a key; checklist item 17).
- **Google Maps with a real key:** BLOCKED. Billing and a key need the owner's approval (decision M1;
  docs/staging/google-maps.md).
- **Real phones in a real car park** (accuracy, permission prompts, plate letter order on real plates): NOT RUN
  (docs/staging/real-device-checklist.md items 15–18).
- **Real WhatsApp delivery and failure statuses:** BLOCKED until staging.
