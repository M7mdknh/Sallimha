# Gate 3 — operational completeness evidence

- Build: `6938705` (last code change, branch `build/phase-0-2`). CI on the commit that adds this text is reported in
  the final hand-over. CI caught one defect on `0a4705c` (run 43762749318: the ticket panel offered a manager-only
  approval to supervisors); fixed test-first in `6938705`.
- Commands: `cd services/api && uv run pytest` → **360 passed**; `cd tests/e2e && PW_CHANNEL=chrome npx playwright test`
  → **27 passed, 5 skipped** (desktop 1280 px + mobile 360 px; the 5 skips are desktop-only flows not repeated on
  mobile: full journey, exception flow, manager unclaimed release, design-QA width matrix, event create/close).
- Security Guidance commit review ran on every code commit of Phase 2 after `bc323d6`; findings on earlier
  commits were fixed test-first (see PROGRESS.md); the last nine code commits reported no security issues.
- Environment: as Gate 2 (Django 6.1.3, DRF 3.18.3, Python 3.14, PostgreSQL 18.7 in Docker, Node 24, Chrome 152 as the
  local Playwright channel; CI uses the PostgreSQL 18 service and Playwright Chromium).
- Labelling: WhatsApp results use the local fake transport and are **PASS (SIMULATED)**. No real WhatsApp evidence
  exists; that is Gate 4 work and is BLOCKED until a staging sender is supplied ([../staging-inputs.md](../staging-inputs.md)).
- Gate 3 file set (`uv run pytest` over the 17 files cited below) → **156 passed**.

| ID | Result | Evidence |
|---|---|---|
| AT-20 | PASS | test_incidents_holds.py::test_supervisor_creates_and_annotates_but_cannot_resolve_incident; test_reports.py::test_manager_export_has_no_phones, test_guest_phone_export_admin_only_and_audited; test_phase2_api.py::test_incident_lifecycle_role_matrix, test_exports_and_reports (direct API calls) |
| AT-21 | PASS | test_console_api.py::test_cross_event_ticket_denied, test_media_streams_only_within_scope; test_phase2_api.py::test_event_create_rejects_another_orgs_venue_as_not_found, test_ticket_finder_by_number_or_plate_is_event_scoped; test_security_regressions.py (cross-org dead-letter replay) |
| AT-22 | PASS | test_incidents_holds.py::test_incident_alone_does_not_block_hold_does |
| AT-23 | PASS (SIMULATED) | test_guest_flow.py::test_ratings_routing |
| AT-24 | PASS | test_carryover.py::test_unclaimed_requires_manager_approval_named_custodian; Phase 1 cancellation tests (test_intake.py); e2e phase2.spec.ts (propose → approve → release in the UI) |
| AT-27 | PASS (SIMULATED) | test_outbox.py::test_status_out_of_order_no_regression |
| AT-29 | PASS | test_reports.py::test_manager_export_has_no_phones; test_phase2_api.py::test_exports_and_reports, test_ticket_export_neutralises_spreadsheet_formulas; e2e phase2.spec.ts (manager sees no phone export; CSV has no phone numbers) |
| AT-30 | PASS | test_config_retention.py::test_retention_skips_held_evidence_and_audits; test_phase2_api.py::test_admin_operations_round_trip (apply over HTTP) |
| AT-31 | PASS | test_outage.py::test_db_failure_no_false_success; tests/recovery/test_worker_process.py (SIGKILL + restart); runbooks [whatsapp-outage](../runbooks/whatsapp-outage.md), [backup-restore](../runbooks/backup-restore.md) |
| AT-36 | PASS (SIMULATED) | test_valet_flow.py::test_photo_outside_intake_requires_explicit_incident |
| AT-40 | PASS | test_config_retention.py::test_timing_change_audited_and_live_offer_keeps_deadline |
| AT-41 | PASS | test_incidents_holds.py::test_assisted_handover_supervisor_only_records_reason |
| AT-43 | PASS | test_carryover.py::test_key_hook_reserved_across_events_until_explicit_release; test_intake.py::test_hook_collision_rejected_across_events |
| AT-44 | PASS | test_config_retention.py::test_opening_check_degraded_when_worker_stale; test_phase2_api.py::test_opening_check_and_dead_letters |
| AT-45 | PASS | test_staffdir.py::test_manager_cannot_grant_manager_or_above, test_last_super_admin_protected, test_deactivate_not_delete_keeps_history, test_cannot_change_own_role |
| AT-46 | PASS | test_mfa.py (7 tests: enforcement, admin-issued enrolment, replay, lockout, session invalidation); test_login_throttle.py (14 tests: concurrency, targeted lockout abuse, expiry, success) |
| AT-47 | PASS (SIMULATED) | test_config_retention.py::test_template_wording_change_keeps_action; test_phase2_api.py::test_admin_operations_round_trip (override and reset over HTTP) |
| AT-51 | PASS (SIMULATED) | test_outbox.py::test_permanent_failure_goes_dead_and_replay_is_once; test_phase2_api.py::test_admin_operations_round_trip, test_unknown_outcome_sends_are_visible_and_resent_only_on_explicit_replay |
| AT-52 | PASS | test_reports.py::test_stage_durations_survive_reassignment |
| AT-53 | PASS | e2e phase2.spec.ts "management pages hold their layout at every width in both languages": 8 pages × 1280/768/640 (200% zoom)/360 px × Arabic/English with no sideways scroll; visible keyboard focus. Every Playwright test also runs on the 360 px mobile project. Visual review screenshots taken at 1280 and 360 px. |
| AT-58 | PASS | test_carryover.py::test_key_hook_reserved_across_events_until_explicit_release; test_phase2_api.py::test_hold_relocation_and_unclaimed_actions (non-manager release denied), test_manager_only_carryover_actions_are_not_offered_to_supervisors |
| AT-59 | PASS | e2e phase2.spec.ts role matrix (supervisor, manager, admin, super admin: links present/absent; direct URL above role shows the forbidden state); test_console_api.py::test_no_manual_dispatch_endpoint, test_valet_has_no_console_access; test_phase2_api.py role matrices |

## Also delivered in Phase 2
- Ticket finder (number or plate) so parked cars without an open request are reachable for holds, relocation and unclaimed handling.
- Operations shows unknown-outcome sends next to dead letters; resending one needs an explicit confirmation (docs/03).
- Draft runbooks for all 13 docs/05 situations: [../runbooks/](../runbooks/README.md). Owners are not yet named.
- Local demo: `make demo` / `make demo-clean`, walkthrough in the README, verified by running the journey and Phase 2
  specs against the `make demo-clean` stack (9 passed).

## Not covered here
- Real WhatsApp delivery, templates and webhooks (Gate 4, BLOCKED on inputs).
- Rotation of `FIELD_ENCRYPTION_KEY` and `HASH_KEY` (no re-encryption command yet; see the secret-rotation runbook).
- Backup restore rehearsal (needs the hosting provider).
