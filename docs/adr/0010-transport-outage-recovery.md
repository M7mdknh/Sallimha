# ADR-0010 — Messaging through a provider outage and its recovery

- Status: **Accepted 2026-11-16** (user mandate: test an actual simulated transport failure and recovery).
- Requirement basis: docs/03 ("keep state, show outage, queue allowed messages"; "a queued message is not a
  delivered message"), ADR-0002 (outbox), ADR-0008 (relayed actions).

## Problems found
- Transient failures gave up after 6 attempts (about two minutes): any longer outage silently turned every queued
  message — including guests' tickets — into a dead letter.
- After recovery the worker would have delivered every queued message, including offers that had expired unseen and
  a collection code for a car already handed over with supervisor assistance — misleading valets and guests.
- The console showed WhatsApp as "simulated/connected" during an outage: no cue for staff.
- The demo "outage" was only declared; messages kept flowing, so recovery was never exercised.

## Decision
1. **Queue through outages.** A transiently failing message stays queued with backoff capped at five minutes for
   `OUTBOX_TRANSIENT_RETRY_WINDOW_S` (default 6 hours), then becomes a dead letter for an operator. Permanent and
   unknown outcomes are unchanged.
2. **Only true messages are delivered late.** Each message kind can register a *still relevant* check that runs just
   before sending; a message that is no longer true ends `OBSOLETE` and is never delivered: offers no longer open,
   "assigned" for a task no longer held, "accepted" when the car is no longer being retrieved, the collection code
   once it is consumed or revoked, "parked" once the car has moved on, the ticket once the ticket is closed.
3. **Superseded at the source.** When an offer is released (expired, declined, superseded), its queued or dead offer
   messages are marked `OBSOLETE` immediately, so Operations never lists stale offers to replay. A message already
   being sent at that moment may still arrive; its buttons are revoked, so tapping it changes nothing.
4. **Degraded health.** WhatsApp health is "degraded" while a message has failed at least twice and nothing has been
   sent since it was queued (or while the simulated outage is on). The live view shows it; supervisors report it;
   a manager declares the outage (ADR-0008 as amended).
5. **Simulated outage.** In local/test only, the simulator can take the simulated provider down: every send fails
   transiently and simulated inbound messages are refused until it is switched back on.

## Evidence
tests/recovery/test_transport_outage.py (six simulated minutes of outage through the worker's own steps, then
recovery), tests/messaging/test_outbox.py::test_transient_failures_keep_a_message_queued_through_a_long_outage,
tests/console/test_simulator_api.py::test_simulated_outage_refuses_inbound_and_reports_degraded.
