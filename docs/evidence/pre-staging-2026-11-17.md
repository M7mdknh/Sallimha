# Evidence: pre-staging fixes (ADR-0012), 17 Nov 2026

Branch `build/phase-0-2`. These are local runs plus CI on the pushed commit. Nothing is deployed. Every WhatsApp
result is **PASS (SIMULATED)**.

## What changed
| Point | Change | Proof |
|---|---|---|
| 1. Admin credentials | No setup code or second factor for an admin from the app. The `/api/staff/<id>/mfa` endpoint and its button are removed, and setup codes for admins are refused with `admin_access_procedure`. A pending code is cancelled whenever a role change involves ADMIN. Admin access goes through a controlled procedure (`manage.py admin_access`, `staffdir.grant_admin_access`): a requesting admin, a different approving supervisor or admin, a reason and the operator's name, with password and second factor reset together and all sessions ended. The Team page shows the last use on each admin's row. The old `issue_mfa` command is removed. | `tests/app/test_admin_access.py` (12 tests): direct refusal, no second-factor endpoint, routine valet and supervisor reset kept, code cancelled on promotion, **demote → reset → promote detour refused**, two-person rules, full reset and sessions ended, lock cleared, first admin only when alone, Team-page record, command. `tests/console/test_mfa.py` and `test_phase2_api.py` were updated to match. Playwright `roles.spec.ts`: a promoted admin's row has no setup-code button and shows the note. |
| 2. My work without side effects | `GET /api/valet/work` only reads. `POST /api/valet/tasks/<id>/shown` (signed-in valet, CSRF, Idempotency-Key, own retrieval offer only) starts the window once, at the earlier of now + 30 s and the hard limit. Repeats answer `already_shown` with the same deadline; after acceptance or the hard limit the answer is `stale` and nothing changes. The task card sends it while the page is visible and retries after the next poll if it was lost. | `tests/app/test_offer_shown.py` (7 tests): **no write SQL during repeated GETs**; a single start, with refresh, a second session and a later acknowledgement unchanged; capped at the hard limit; after the hard limit nothing changes; a polled but unacknowledged offer still lapses at 60 s; accepting before the acknowledgement works; CSRF, other valet, signed out, console role and missing key all refused. The Playwright valet journey runs through the real acknowledgement. |
| 3. Docs | docs/06 (AT rows amended, AT-61–AT-72 added, gates), docs/07 (approvals dated 17 Nov, superseded items), docs/09 (rows amended in place, R-74–R-86, AT-61–AT-72 with their evidence); ADR-0012; runbook admin-access; account-compromise, secret-rotation, staging-inputs, README and SYSTEM_OVERVIEW updated | — |
| 4. Decisions | docs/decisions-needed.md A1–A6 with recommendations, plus the new A7 and A8 | — |

## Results
| Check | Result |
|---|---|
| Backend suite (`pytest`, staff channel = app) | **521 passed** |
| Retired valet-WhatsApp channel (`-m whatsapp_staff`, `SALLIMHA_TEST_ALL_LEGACY=1`) | **82 passed** |
| Browser suite (`npx playwright test`, installed Chrome, desktop 1280 px + mobile 360 px projects) | Full run: **37 passed, 1 failed, 8 skipped** (the 8 desktop-only tests set their own device sizes). The failure was `console.spec.ts` "a supervisor signs in and sees Operations problems-first", which read the headings before the page rendered (`undefined`, first data page after a cold start). It was fixed with a waiting assertion, and `console.spec.ts` was rerun: **10 passed**. CI reruns everything. |
| Ruff, TypeScript type check | PASS |
| Contract regenerated (`make contract`, `--fail-on-warn`); committed copy matches (`test_schema`) | PASS |
| CI on the pushed commit | reported in the hand-over message |

## Not verified here
- Real WhatsApp: **BLOCKED** until staging.
- Real phones and tablets: **NOT RUN**. Checklist: [../staging/real-device-checklist.md](../staging/real-device-checklist.md).
- The admin access procedure on the staging host (container shell): **NOT RUN** until hosting is approved.
- Load, provider-level backup restore and rollback: **NOT RUN** (staging).
