# Review and staging preparation — implementation plan

> Executed inline (superpowers:executing-plans). Spec: docs/01–07, ADR-0001–0006, the user's 2026-11-16 mandate.

**Goal:** verify Phases 0–2 against the specs, fix confirmed defects with regression tests, close the outage,
relocation and remaining gaps, and prepare staging without deploying.

## Global constraints
- Do not merge or deploy. No purchases, no secret values in chat. Real WhatsApp/infrastructure stays BLOCKED until exercised.
- Every fix: failing test first. Every new endpoint: serializer → `--fail-on-warn` contract → TS regen → drift test.
- `allowed_actions` stays role- and state-aware. Safety holds are never bypassed. No routine manual dispatch.
- Brand and scope unchanged. Findings appended to docs/evidence/review-2026-11-16.md as they are found.

## Tasks
1. Review probes (custody, permissions, concurrency, webhook replay, auth, demo isolation); fix defects.
2. Relocation (ADR-0007): offer → valet accept → completion by mover; supervisor completion only after acceptance; cancel.
3. Outage (ADR-0008): declared WhatsApp outage window with proxy actions; system-outage continuity; reconciliation.
4. Gaps: settings versioning; venue time zone; per-row queries; browser zoom; mobile flows.
5. Key rotation (ADR-0009): multi-key encryption and hashing, rotation command, recovery procedure.
6. Staging: image, deploy checks, S3-compatible private media, backup/restore rehearsal.
7. Evidence, runbooks, decisions needed, CI on the final commit.
