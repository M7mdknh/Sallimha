# Outage fixes and staging setup — plan

> Executed inline (superpowers:executing-plans). Spec: docs/01–07, ADR-0001–0009, the user's mandate of 2026-11-16 (second).

## Global constraints
- No purchases or deployment until the hosting option and costs are approved. No secrets in chat.
- Real WhatsApp and provider checks stay BLOCKED until exercised. Brand and scope unchanged.
- Failing test first for every fix; contract + TS regenerated for API changes; allowed_actions role/state-aware.

## Tasks
1. Real simulated transport failure and recovery (ADR-0010): persistent outage mode, send-time relevance and OBSOLETE,
   obsolete marking on offer release, degraded health, worker-step test over simulated time, simulator toggle.
2. Outage declaration/closure manager+; supervisors report an outage; ADR-0008 amended.
3. Live outage intake: RECEIVED via relayed steps (photos or explicit exception, confirmed parking with location, hook,
   responsible valet); retrospective reconciliation unchanged.
4. Hosting comparison (official sources, dated), recommendation, account/domain decisions.
5. WhatsApp onboarding checklist (testing vs production), template inventory.
6. Local preparation, evidence, CI on the final commit.
