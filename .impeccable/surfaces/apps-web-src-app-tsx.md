---
version: 1
slug: "apps-web-src-app-tsx"
primary_target: "apps/web/src/App.tsx"
related_targets: []
---

Scope: supervisor console (login, live operations, ticket exceptions, dev simulator). Mode: Operate.
Audience and task: supervisors of one live event on phone/tablet/laptop; spot exceptions, act on them, run shifts; no routine dispatch.
Constraints: DESIGN.md and brand tokens are fixed; Arabic-first RTL, English LTR; 360 px to desktop; stale banner and disabled actions when disconnected; masked phones only.

## Direction contract
seed: none (pinned) — pinned by DESIGN.md "Console hierarchy" and the approved brand guide page 06 sample console.
THESIS: Attention first, everything else below: the screen answers "what needs me now?" before "how is the night going?".
FIRST VIEWPORT: event name and freshness line; attention list (critical first, each with its next action); then compact state counts; then open requests oldest-first with elapsed time, stage and owner; team availability last.
SIGNATURE INTERACTION: selecting a request or alert opens the ticket panel in place with its masked contact, location, key hook, timeline and only the exception actions its state allows, each with an explicit reason field.
MATERIAL: paper ground, white surfaces, plum navigation band, purple primary actions, gold only as small handoff accent; light borders, no gradients or glass.
TYPE: Noto Sans Arabic / Noto Sans per DESIGN.md scale; tabular numerals for counts, ticket numbers and timers; identifiers isolated LTR.
RISK: density on 360 px phones; keep attention items and requests as stacked rows, never a horizontal-scrolling table.
