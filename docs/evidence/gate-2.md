# Gate 2 — core correctness evidence

- Build: `54c4aba` (branch `build/phase-0-2`); CI run [43730626346](https://github.com/M7mdknh/Sallimha/actions/runs/43730626346) — backend, web, e2e **success**.
- Local environment: Django 6.1.3, DRF 3.18.3, Python 3.14.4, PostgreSQL 18.7 (Docker), Node 24.18, Chrome 152 (Playwright channel); CI uses Ubuntu 26.04, PostgreSQL 18 service, Playwright Chromium.
- Commands: `cd services/api && uv run pytest` → **287 passed**; `cd tests/e2e && PW_CHANNEL=chrome npx playwright test` → **15 passed** (desktop 1280 px + mobile 360 px).
- Labelling: WhatsApp results use the local fake transport and are **PASS (SIMULATED)**. No real WhatsApp evidence exists (BLOCKED until a staging sender exists).

| ID | Result | Evidence (test) |
|---|---|---|
| AT-01 | PASS | tests/core/test_phone.py (Arabic/Persian digits, international, masking); test_intake.py::test_phone_never_confused_with_hook |
| AT-02 | PASS (SIMULATED) | test_intake.py::test_ticket_sent_before_parking_remains_received |
| AT-03 | PASS | test_intake.py::test_parking_requires_photos_or_exception, test_vehicle_identifier_required, test_parked_after_location_and_hook_releases_valet |
| AT-04 | PASS (SIMULATED) | test_guest_flow.py::test_early_request_waits_for_parking; test_intake.py::test_early_request_becomes_queued_on_parking |
| AT-05 | PASS | test_dispatch.py::test_original_parking_valet_gets_offer |
| AT-06 | PASS | test_dispatch.py::test_original_busy_other_free_offered_immediately |
| AT-07 | PASS | test_dispatch.py::test_everyone_busy_queue_keeps_age |
| AT-08 | PASS (real concurrency) | test_concurrency.py::test_two_dispatchers_one_reservation |
| AT-09 | PASS (real concurrency) | test_concurrency.py::test_intake_vs_retrieval_capacity |
| AT-10 | PASS (SIMULATED + real concurrency) | test_guest_flow.py::test_repeat_tap_single_request; test_concurrency.py::test_concurrent_request_taps_single_request; test_webhook.py::test_duplicate_webhook_single_inbox_row |
| AT-11 | PASS (real concurrency) | test_concurrency.py::test_accept_races_expiry_single_winner |
| AT-12 | PASS | test_dispatch.py::test_timeout_requeues_preserves_age_cooldown_alert, test_decline_requeues_and_releases, test_send_failure_releases_reservation |
| AT-13 | PASS | test_dispatch.py::test_accepted_not_reassigned_alert_only; test_handover.py::test_transfer_custody_revokes_old_tokens_requires_ack |
| AT-14 | PASS | test_handover.py::test_late_ready_from_superseded_assignee_rejected; test_dispatch.py (stale accept) |
| AT-15 | PASS (SIMULATED) | test_handover.py::test_ready_code_handover_closes_once_releases_all; e2e journey.spec.ts |
| AT-16 | PASS (SIMULATED) | test_handover.py::test_wrong_code_five_attempts_then_review; test_guest_flow.py::test_forwarded_button_other_sender_rejected, test_display_number_text_not_credential |
| AT-17 | PASS (SIMULATED) | test_guest_flow.py::test_correction_revokes_old_tokens; test_handover.py::test_ready_code_revoked_on_phone_correction |
| AT-18 | PASS (SIMULATED) | test_guest_flow.py::test_multi_ticket_phone_requires_selection |
| AT-19 | PASS | test_shifts.py::test_end_shift_refused_with_live_task, test_break_pending_until_release; test_dispatch.py::test_break_pending_until_handover |
| AT-25 | PASS (real process) | tests/recovery/test_worker_process.py (SIGKILL + restart); test_outbox.py::test_outbox_sent_after_restart |
| AT-26 | PASS (SIMULATED) | test_outbox.py::test_lost_response_marks_delivery_unknown, test_crashed_send_lease_becomes_delivery_unknown; test_outbox_real_transactions.py |
| AT-32 | PASS | test_dispatch.py::test_fairness_beats_affinity |
| AT-33 (collision) | PASS | test_intake.py::test_hook_collision_rejected_across_events; test_constraints.py |
| AT-34 | PASS | test_console_api.py::test_repeat_submit_same_key_single_effect; e2e console.spec.ts (stale banner disables actions) |
| AT-35 | PASS (SIMULATED) | test_intake.py::test_receipt_confirmation_only_by_staff |
| AT-37 | PASS | test_intake.py::test_intake_transfer_sets_parked_by |
| AT-38 | PASS (SIMULATED) | test_guest_flow.py::test_queued_message_never_claims_retrieval; catalogue contract tests |
| AT-39 | PASS | test_dispatch.py::test_offer_has_no_code_or_phone |
| AT-42 | PASS | test_constraints.py::test_second_open_shift_rejected_by_db; test_shifts.py |
| AT-48 (DB part) | PASS | test_audit.py::test_audit_update_blocked_by_trigger, test_audit_delete_blocked_by_trigger |
| AT-49 | PASS | tests/core/test_masking.py (17 cases, incl. Security Guidance regressions) |
| AT-50 | PASS (SIMULATED) | test_webhook.py::test_invalid_signature_rejected_before_persist, test_previous_secret_accepted_during_rotation |
| AT-53 (live view subset) | PASS | e2e brand-fonts.spec.ts, console.spec.ts at 360 px and 1280 px (RTL/LTR, no overflow) |
| AT-54 | PASS (SIMULATED) | test_guest_flow.py::test_withdraw_queued_keeps_parked |
| AT-55 | PASS | test_intake.py::test_cancel_before_parking_with_confirmation, test_cancel_refused_after_parking_started, test_cancel_refused_without_confirmation |
| AT-56 | PASS (SIMULATED) | test_intake.py::test_cancel_cascade_withdraws_request_revokes_tokens |
| AT-57 | PASS | test_handover.py::test_withdraw_accepted_requires_custody_resolution |
| AT-59 (live view subset) | PASS | test_console_api.py::test_valet_has_no_console_access, test_no_manual_dispatch_endpoint; e2e |
| AT-60 | PASS (SIMULATED) | test_dispatch.py::test_duplicate_accept_no_second_effect; test_valet_flow.py::test_duplicate_button_tap_has_no_second_effect |

Gate 2 verdict: **PASS for local/simulated scope.** Real-provider scenarios (AT-28 template path against Meta, AT-50 real signatures) remain BLOCKED until staging.
