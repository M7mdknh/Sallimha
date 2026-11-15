# Sallimha project instructions

## Mission
Build سلّمها / Sallimha, a reliable Arabic-first valet operation. The guest provides a phone number at intake, receives a WhatsApp ticket, requests the car when ready, and receives it after verified handover. Retrieval prioritizes the original parking valet only when available. Supervisors monitor and resolve exceptions; they do not manually dispatch routine work.

## Read in this order
1. `README.md`
2. `docs/01_Final_Approach.md`
3. `docs/02_Roles_and_State_Model.md`
4. `docs/03_Dispatch_and_Reliability.md`
5. `docs/04_WhatsApp_and_Messages.md`
6. `docs/05_Architecture_and_Deployment.md`
7. `docs/06_Test_and_Release_Plan.md`
8. `docs/07_Decisions_and_Sources.md`
9. `DESIGN.md` and `brand/tokens.json`

The original PDFs are already consolidated. Do not ask for them. User-approved requirements outrank proposed technical defaults. If documents conflict, identify and resolve the conflict before implementing the affected behavior. Record new decisions in an ADR. Do not silently add a feature, change a permission, or reinterpret a state.

## Working method
- Inspect the actual repository first. An empty repository means a new implementation, not a completed code audit. Preserve unrelated work.
- Use Superpowers for planning, meaningful tests, debugging and review. Use Context7 for the exact installed library versions; verify provider-specific behavior in official documentation.
- Use Impeccable within DESIGN.md. Preserve the specified plum/gold identity; generic design rules must not replace approved brand colors. Do not add decorative dashboards at the expense of operational clarity.
- Use Playwright for browser review and maintain repeatable end-to-end tests in CI. Exercise Arabic, English, RTL/LTR, keyboard and narrow-screen layouts.
- Use Security Guidance; confirm its review actually runs. A plugin installation or green scanner is not proof of product correctness.
- Keep reviewable changes and a concise progress log. Run targeted checks per change, then release gates at milestones. Do not fabricate PASS results.
- Keep secrets outside source and prompts. Provide `.env.example` with placeholders and document secret names without their values.

## Non-negotiable implementation rules
- PostgreSQL or an equivalently transactional approved database is the durable source of truth. Use constraints and transactions for assignment; no in-memory-only locks or timers.
- Exactly one open retrieval request per ticket and at most one live operational task reservation per valet. Offers count as reservations. Recheck shift and permissions on every mutation.
- Authenticate webhook origin, deduplicate events, and use a durable outbox. Internal effects must be idempotent; do not promise exactly-once delivery from an external messaging provider.
- Preserve custody: a timed-out, unaccepted offer can be reassigned automatically; an accepted job cannot be handed to another person automatically without resolving custody.
- One person, one active event shift. Event and organization scope must be enforced server-side on every object lookup.
- A collection code is supplementary proof tied to the ticket and guest, not sole proof of vehicle ownership. Corrections revoke old guest credentials.
- Incidents are separate from vehicle states. A specific safety hold can block handover; merely opening an incident must not falsify vehicle location.
- An action acknowledged as complete must be durably committed. A queued message is not a delivered message.
- Do not create account-management or production-deployment side effects merely to test an integration. Use designated staging/test resources.

## Delivery sequence
First produce a repository inspection, a requirements traceability matrix, ADRs for the proposed stack and worker design, and a staged plan. Show the included brand identity for review before writing application UI. Foundational implementation may proceed once the user authorizes the build stage.

Implement vertical slices: registration → parking → guest request → atomic dispatch → ready → verified handover → rating; then incidents, administration, reporting and operational recovery.

Before production: demonstrate staging with the real WhatsApp integration, all critical acceptance tests, load results against declared targets, backup restoration and rollback. Report unresolved external inputs truthfully. Do not claim deployment until a live health check and smoke test pass on the exact released version.

