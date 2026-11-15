# 07 — Decisions, assumptions and sources

## Approved business direction
Paperless WhatsApp guest ticket; phone captured during registration; no required guest QR/app; location and parking-valet tracking; original valet priority only when available; automatic alternative assignment; supervisor monitoring/exception role; immediate ticket; receipt check; automatic availability; acceptance timeout; queue; collection verification; preserved photos/audit; one request/assignee at a time.

## Preserved from original operating documentation
Events and separate shift activation; one active shift/person; WhatsApp valet channel; role hierarchy; manager incident closure; admin-only guest-phone export; super-admin WhatsApp connection; stage timing; server-held photos; ratings; filtered reports; configurable messages; retention zero means never delete; honest cancellation and unclaimed outcomes.

## Proposed defaults requiring review, not misrepresented as prior approval
| Choice | Recommendation / reason |
|---|---|
| Brand | Refined plum/gold Sallimha identity in DESIGN.md; visual proposal for review |
| Stack | React/TypeScript + Django/DRF + PostgreSQL + worker + private object storage |
| Scope | One organization, multiple venues/events; no public SaaS billing/onboarding |
| Staff surface | Preserve WhatsApp; web registration app is not a V1 prerequisite |
| Offer timeout | 30 s instead of old guide's 90 s; pilot-configurable |
| Dispatch | Oldest eligible request; original-valet affinity then longest-idle fallback |
| Phone correction | Supervisor verification after a ticket has already been sent |
| Vehicle identity | Require plate/usable identifier or reasoned exception; old shortcut allowed no description |
| Unclaimed | Manager approves custody before close; stronger than original supervisor guide |
| Handover code | Six digits; limited attempts; keyed verifier; created at ready |
| Busy definition | Intake and offered/accepted retrieval through handover consume capacity |
| Audit | Application-append-only with operational controls; no absolute immutability claim |
| Recovery/load goals | Pilot targets in architecture document, not demonstrated SLAs |

## Original inconsistencies resolved
- Journey deck placed guest linking after intake in its overview; valet guide issued QR immediately. Final user instruction replaces mandatory scan with phone capture and immediate ticket.
- Opening a ticket was described as “any number” in one guide and “any message” in another. New structured interaction uses an explicit new-vehicle action and field context.
- Valet guide broadly said non-excellent ratings go to supervisors; journey deck explicitly recorded neutral silently. This pack uses neutral silent, poor immediate alert.
- A summary line implied parking before photos, while detailed instructions required photos before movement. This pack consistently requires photos first.
- Original immutable-record wording is treated as a product control objective, not proof that a database administrator cannot alter storage.

## Inputs still needed before production
Repository/source availability; hosting accounts/budget and approved region; WhatsApp Business sender/provider, template approvals and credentials; actual venue parking/key layout; forecast peak traffic; retention/legal policy owner; operational support contacts; domain; backup/monitoring ownership. These are deployment inputs, not reasons to ask for old PDFs again.

## Source provenance
User-provided operational guides were read in full: `رحلة-المركبة.pdf` (14 pages), `١-الفاليت.pdf` (19), `٢-المشرف.pdf` (11), `٣-المدير.pdf` (14), `٤-الأدمن_.pdf` (8). User sketch `Notes_261115_042845.pdf` has one substantive diagram and a blank second page. This handoff consolidates their content; they are not dependencies and are not bundled.

The 42-tool guide was used only for tool selection. Its install/pricing claims are not product requirements. The user pasted a readiness report; it is not an independent audit performed by this pack's author.

## External implementation references
Checked 15 November 2026. Reverify time-sensitive provider behavior at implementation.
- WhatsApp Business Messaging Policy: https://business.whatsapp.com/policy
- WhatsApp incoming messages and outgoing status webhook reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages
- PostgreSQL locking: https://www.postgresql.org/docs/current/explicit-locking.html
- Django transactions: https://docs.djangoproject.com/en/stable/topics/db/transactions/
- W3C text contrast: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- Noto Arabic font project/license: https://github.com/notofonts/arabic
- Superpowers: https://github.com/obra/superpowers
- Impeccable: https://github.com/pbakaus/impeccable
- Playwright MCP: https://github.com/microsoft/playwright-mcp
- Context7: https://github.com/upstash/context7
- Security Guidance: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance

These links support platform facts and tooling. Dispatch policy, brand identity, data design and deployment targets are this pack's design proposals implementing the agreed business intent. No trademark clearance, compliance certification or production performance certification has been performed.

