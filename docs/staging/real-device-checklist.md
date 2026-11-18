# Real-device acceptance checklist (AT-72) — status: NOT RUN

Run this in the staging rehearsal (Gate 4) with the actual staff phones and tablets and the venue's Wi-Fi or mobile
data. Browser emulation has already been tested; this checklist covers only what emulation cannot show.

**Setup:**
- At least 2 valet phones (one iPhone and one Android if both are in use) and 1 supervisor tablet.
- 1 customer handset with real WhatsApp.
- Each valet signed in to the app, with screen auto-lock as decided in A5.

Write the device model, OS and browser version next to every line, and record each line as PASS, FAIL or BLOCKED.

## Camera capture
1. Register car → photos: **Take photo** opens the rear camera directly, on each phone model.
2. Take four photos in daylight and four at night or under car-park lighting. The count goes 1→4 and each upload
   finishes within 10 s on venue data. The supervisor sees the four photos on the ticket.
3. Deny camera permission once and note what the phone does instead (a file picker, or nothing). No photo is counted.
   After allowing the camera in the phone's settings, **Take photo** works.
4. Switch to another app mid-upload, then come back. The photo either finishes or shows as failed with a retry.
   It is never shown as saved when it wasn't.

## Locked screens and missed offers
5. Lock the screen of the valet who parked a car, then have the customer request the car. The offer is **not**
   acknowledged. The supervisor sees "offer not yet shown" after about 15 s. At about 60 s the offer goes to the next
   available valet, and the customer's waiting time is not reset.
6. Unlock within 20 s. The offer appears, the countdown shows the 30 s window (never more than the 60 s hard limit),
   and accepting works.
7. Leave an unlocked phone untouched with an offer showing. It lapses after its window and goes to the next valet;
   the first valet's card clears by itself.
8. Have the same valet open the app in a second tab, or refresh during an offer. The countdown does not restart.
9. With the optional sound turned on, check that it plays on each phone model, and note whether it plays with the
   screen locked. The task card stays the way an offer is found.

## Connectivity loss and recovery
10. Turn on airplane mode on a valet phone that has an accepted task. The "connection lost" banner appears at once,
    the task stays as it was, and a tap on **Car ready** is not shown as done.
11. Turn airplane mode off. The banner clears by itself and the app resumes at the server's step. A tap made while
    offline is either applied once or clearly not applied, never twice.
12. Walk from Wi-Fi to mobile data, and through any dead spots, between the key board and the car park. Note where
    the connection drops and for how long.
13. Supervisor tablet offline for 1 minute. Operations shows that it is stale, and nothing can be submitted until
    the tablet reconnects.
14. A valet phone runs out of battery mid-task. The supervisor marks **Device not working**, records that valet's
    next action, then marks the device working again once it is back. The valet's app resumes at the server's step.

## Location, plate and map (ADR-0013)
15. Beside a parked car at ground level, basement and multi-storey: **Use my location** → note the reported accuracy
    and how long it takes. The pin is kept only at 150 m or better, and an old fix is refused.
16. Deny location permission on one phone. Parking still completes with zone, floor, spot and description.
17. With the real Maps key (docs/staging/google-maps.md): open the map, tap and drag the pin, and check that the venue
    centre is labelled as not the car. **Open in Google Maps** opens the right spot on iPhone and Android.
18. Photograph three real Saudi plates. Enter each in Arabic and in Latin, and check that the preview matches the plate.
    Confirm with the owner how the letter positions of the two rows correspond before any cross-script display is
    added (it is used only as a search key today).

## Sign-in on real devices
19. A new valet sets their password with a setup code on their own phone, then signs in with the mobile number typed
    the local way (05…).
20. An admin's sign-in goes through the controlled procedure (runbooks/admin-access.md): the second-factor link is
    scanned into an authenticator app on that admin's phone, and sign-in succeeds.

**Exit:** every line PASS, or a FAIL with an owner and a decision before go-live. Record the results in
docs/evidence/ with the date, the devices and the build.
