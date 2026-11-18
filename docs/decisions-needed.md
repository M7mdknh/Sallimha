# Decisions needed from the owner (2026-11-16, updated 2026-11-17 for ADR-0011)

Each item blocks staging (S), production (P) or only fine-tunes behaviour (T). Nothing here needs a secret value in
chat; secrets go straight into the hosting provider's secret store.

## Hosting
| # | Decision | Blocks | Notes |
|---|---|---|---|
| H1 | Hosting provider and account owner — **proposal: Oracle Cloud Riyadh (≈ $162/month staging, estimate); alternative DigitalOcean Frankfurt ($44/month list)**, see docs/staging/hosting-options.md | S | Approve the option and a monthly ceiling; tenancy home region Riyadh is permanent |
| H2 | Region / data location for guest phones and vehicle photos | S | A legal/business owner decides whether Saudi data-protection rules require in-Kingdom storage (ADR-0004 makes no legal determination) |
| H3 | Staging and production domain names | S | Staging host for `DJANGO_ALLOWED_HOSTS`; DNS control for TLS |
| H4 | Recovery targets: RPO (proposed ≤ 15 min) and backup retention | P | Retention of backups also sets how long retired encryption keys must be kept (ADR-0009) |
| H5 | Monitoring, alert recipients and on-call owner | P | Uptime check on `/readyz`, worker heartbeat, queue age, failed messages |
| H6 | HSTS for the whole domain (subdomains, preload) | P | Staging starts at 1 hour, subdomains/preload off |

## WhatsApp
| # | Decision / input | Blocks | Notes |
|---|---|---|---|
| W1 | Meta Business portfolio and app with WhatsApp; WhatsApp Business Account (verification needed for production, not for testing) | S | docs/staging/whatsapp-onboarding.md A1–A2, B1 |
| W2 | Staging sender: Meta's test number (allow-listed recipients only) or a dedicated staging number; later the production number | S | Recommended: dedicated staging number for the real journey |
| W3 | Display name and business profile (Arabic/English) | S | Shown to guests |
| W4 | Approval of utility templates (AR + EN) for **customer** messages sent outside the 24-hour window (7 templates; staff templates are no longer needed after ADR-0011) | S | docs/staging/whatsapp-onboarding.md section C |
| W5 | Test devices: 3 customer handsets (real WhatsApp) and 3 staff phones or tablets for the web app | S | For the Gate 4 rehearsal |

## Operations
| # | Decision | Blocks | Notes |
|---|---|---|---|
| O1 | Named business owner and on-call technical owner for each of the 13 runbooks | P | docs/runbooks/README.md |
| O2 | Approve the paperless continuity procedure for a whole-system outage (offline log on staff phones, supervisor verification before any handover) | P | docs/runbooks/whatsapp-outage.md; ADR-0008 |
| O3 | ~~Who may declare a WhatsApp outage~~ — **decided: admins declare and end; supervisors report** (managers became admins, ADR-0011) | — | ADR-0008 amendment |
| O4 | Whether reconciliation after a system outage must include a photo (currently text evidence + offline log reference, verified by a second person) | T | ADR-0008 |
| O5 | Retention periods for guest phones, intake photos and resolved-incident evidence (currently 0 = never delete) | P | Settings → Data retention |
| O6 | Time zone per venue (all current venues Asia/Riyadh) | T | Venue setting; the console enters and shows times in it |
| O7 | Maximum length of a recordable system outage (24 h) and how far back reconciliation is allowed (30 days) | T | ADR-0008 |

## Staff app pilot (ADR-0011, ADR-0012)
| # | Decision | Blocks | Notes | Recommendation |
|---|---|---|---|---|
| A1 | Confirm that every former manager should become an admin (the migration grants them settings, retention, message replay, the customer-number export and WhatsApp status) | P | Review the admin list after the migration; demote anyone who should be a supervisor | **Do not assume it.** Nothing is deployed, so no real manager accounts exist yet: this is "who is named admin at pilot setup". Name exactly two admins (the owner and one operations lead) so admin-only work (incident resolution, carryover, outages) never waits on one person; every other former manager starts as a supervisor. Optionally, before staging, change the migration so MANAGER becomes SUPERVISOR (SUPER_ADMIN and ADMIN stay ADMIN) — on your approval only |
| A2 | Valet password minimum (proposed 8 characters; supervisors and admins keep 12) | T | Typed on a phone at the start of a shift; sign-in is throttled | Accept 8 for valets: throttled sign-in, no access beyond their own task, and a setup-code reset is quick |
| A3 | How setup codes reach people (in person by the admin is the default; never sent by message) | P | Codes last 72 hours, five attempts | In person only, by the admin, for valets and supervisors. Admins get theirs from the technical owner through the controlled procedure (ADR-0012), also in person |
| A4 | Supervisors who also park cars need a separate valet account in the pilot | T | One account per role keeps valet and console permissions apart | **Supervisors do not park in the pilot.** A second account needs a second mobile number (one account per number per organisation) and would let one person hold two open shifts, which breaks "one person, one active shift". If supervisors must park, that is a follow-up design |
| A5 | Staff devices: personal phones or venue phones/tablets; whether the app stays open on screen during a shift | P | Offers are shown in the app; a closed or locked phone lets the offer lapse to the next valet after 60 s | Venue phones if available, otherwise personal phones. Either way: the app open in the browser with the screen on during a shift (auto-lock 5 min or more), a charger at the stand, one tablet for the supervisor. Confirm in the real-device rehearsal (docs/staging/real-device-checklist.md) |
| A6 | Optional alert sound is off by default; push notifications are not in the pilot | T | The task card is always the way an assignment is discovered | Keep it: sound off by default, each valet may turn it on; no push in the pilot. Revisit after the rehearsal using the count of "offer not yet shown" alerts |
| A7 | Who holds server access and runs the admin access procedure (technical owner) | S | Names given to the procedure are the operator's attestation; server access is outside the app's roles (ADR-0012) | One named technical owner and one backup, neither of them a pilot admin if the team allows; otherwise record that overlap as an accepted risk |
| A8 | Who may approve an admin's access | S | Implemented: any enabled supervisor or admin other than the requester and the target | Keep it as implemented, so a pilot with two admins can still recover either one; the approver checks identity in person |

## Pilot usability (ADR-0013)
| # | Decision | Blocks | Notes | Recommendation |
|---|---|---|---|---|
| M1 | Approve a Google Cloud billing account and a monthly ceiling for the Maps JavaScript API (staging, then production) | S (map only) | Without it the app runs with the text place and "map not configured"; docs/staging/google-maps.md | Approve a small staging ceiling with a daily quota cap; decide production after the rehearsal |
| M2 | Location thresholds: stale after 30 s; approximate above 50 m; not saved above 150 m | T | Proposed defaults in ADR-0013 | Keep them for the rehearsal; adjust from real car-park readings (checklist item 15) |
| M3 | Saudi plate: how the letter positions of the Arabic and Latin rows correspond | T | The 17 letters are verified; positions are not stated by the sources. Today only the entered script is shown | Confirm from real plates in the rehearsal (checklist item 18) before showing the other script |

