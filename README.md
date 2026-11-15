# Sallimha | سلّمها — build handoff v1.0

Prepared 15 November 2026, Asia/Riyadh. A self-contained specification for Claude Code. The original PDFs and sketch are not required.

## Start here
1. Extract this folder into the root of the Sallimha repository. Keep its relative paths. If files already exist, merge deliberately instead of overwriting them.
2. Read `Sallimha_Final_Approach.pdf` for the operating model and `Sallimha_Brand_Identity.pdf` for the proposed visual identity.
3. Start a fresh Claude Code session from the repository root. Paste `Claude_Kickoff.md`.
4. Claude must first verify the supplied files, inspect any actual application code, and record remaining deployment inputs. It should not ask for the source PDFs.

## What is authoritative
The user-approved process is specified in `docs/01_Final_Approach.md`. The other documents make it implementable. All newly selected implementation details, target metrics, and brand assets are explicitly proposed defaults. They have not been approved separately or validated in production.

| File | Purpose |
|---|---|
| `CLAUDE.md` | Repository instructions and working rules |
| `docs/01_Final_Approach.md` | Product scope and complete operating process |
| `docs/02_Roles_and_State_Model.md` | Permissions, states, entities and invariants |
| `docs/03_Dispatch_and_Reliability.md` | Fair assignment, concurrency and recovery |
| `docs/04_WhatsApp_and_Messages.md` | Registration, messaging and bilingual copy |
| `docs/05_Architecture_and_Deployment.md` | Proposed architecture and deployment requirements |
| `docs/06_Test_and_Release_Plan.md` | Acceptance scenarios and release gates |
| `docs/07_Decisions_and_Sources.md` | Approved versus proposed choices, sources and open inputs |
| `DESIGN.md` | Brand and UI specification |
| `brand/` | Vector identity assets, design tokens and licensed fonts |
| `Claude_Kickoff.md` | Ready-to-paste starting prompt |

## Scope
This pack specifies the product; it is not an implemented or deployed application. No source repository was audited here. The user-provided Claude readiness report described an empty clone. No hosting provider, production domain, WhatsApp account, legal retention schedule, or operating capacity has been verified.

Keep the software deterministic: vehicle assignment, ticket transitions and ownership checks must not depend on an LLM. AI coding tools help build the product; they are not required in its operational request path.

