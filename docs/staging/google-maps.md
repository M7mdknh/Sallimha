# Google Maps for the parking map (ADR-0013) — status: **BLOCKED** (not configured)

The app works without a map: valets record zone, floor, spot and a short description, and can still save a
browser-geolocation pin, with its accuracy. A map adds two things. The valet can check or place the pin while
parking, and the valet who later retrieves the car sees it on a map. Nothing here has been set up. No Google account,
billing or key was created or used.

## What the app uses
- **Maps JavaScript API** only, loaded in the browser through `@vis.gl/react-google-maps`. It loads only when a valet
  opens the map while parking, or opens the map on a retrieval or move card.
- **Map ID** for the advanced marker (the pin).
- **Not used:** the Geolocation API (positions come from the phone's own browser geolocation), Places, Directions,
  Routes and Street View. Do not enable them.
- **Open in Google Maps** is a plain link, `https://www.google.com/maps/search/?api=1&query=LAT%2CLNG`. It needs no
  key and carries the coordinates only.

## Steps (after the owner approves billing and a monthly ceiling)
1. In Google Cloud, create a project for Sallimha staging, owned by the business account, not a personal one.
2. Link a billing account. Google requires one for the Maps JavaScript API. **This needs the owner's approval
   first**: check the current Maps JavaScript API price list and free allowance on Google's pricing page at the time.
   Set a budget alert on the billing account.
3. Enable **Maps JavaScript API**, and nothing else.
4. Quotas: set a daily cap on Maps JavaScript API map loads, so a fault cannot run up cost.
5. Create a **Map ID** (Maps management → Map IDs, type JavaScript) for staging.
6. Create an **API key**, then restrict it:
   - Application restriction: **Websites**, with the staging origin only (`https://<staging-host>/*`). Production
     gets its own key later.
   - API restriction: **Maps JavaScript API** only.
7. Put the values in the hosting provider's secret store (never in the repository or in chat):
   `GOOGLE_MAPS_BROWSER_KEY`, `GOOGLE_MAPS_MAP_ID`. Restart the app. The browser fetches them at run time from
   `/api/maps/config`, so no rebuild is needed.
8. As an admin, set the venue's map centre (`POST /api/venues/<id>/map-centre`, Settings). The map opens there and
   labels it "venue centre — not the car".

## Check
- Open a valet's parking stage on staging → **Map: check or place the pin**. The map loads at the venue centre;
  tapping places the pin, and dragging moves it.
- If the key is refused (wrong site, API not enabled, billing off), the app shows "The map could not load" and parking
  continues with the description. The browser console names the cause (`RefererNotAllowedMapError`,
  `ApiNotActivatedMapError`, `BillingNotEnabledMapError`).
- The served app sends `Referrer-Policy: strict-origin-when-cross-origin`. Google sees the origin, which a
  website-restricted key needs, but never the page path (which holds ticket ids). This is checked by
  `tests/staging/test_console_serving.py`.

## Privacy
- Markers carry no customer identifier, plate or ticket number.
- Coordinates are saved only when confirmed: a geolocation fix of 150 m or better, or a pin the valet placed.
- Google receives map-tile requests for the area being viewed, which is inherent to showing a map.

## Real-device rehearsal (with the key)
Use [real-device-checklist.md](real-device-checklist.md), items 15–18: accuracy in the car park, the map with a real
key, placing and dragging the pin, and Open in Google Maps on iPhone and Android. Until that has run, real-map
results stay **BLOCKED**. Results without a key, or with emulated positions, are **SIMULATED**.
