# Sallimha brand and interface system

Version 1.0 — 15 November 2026. **Proposed identity for review before UI implementation.** This refines the plum/purple and gold direction visible in the original guides. It is not a claim of an established registered identity or trademark clearance.

## Brand foundation
- Arabic name: **سلّمها**. Display wordmark may use **سَلِّمها**. Never split or letter-space Arabic lettering.
- English name: **Sallimha**. Keep this spelling in UI, repository and public content.
- Arabic descriptor: **خدمة صفّ المركبات**. English descriptor: **Valet, handled.**
- Proposed brand line: **وصلت، والباقي علينا.** English adaptation: **Arrive. We’ll take it from here.** This is a service promise in tone, not a guaranteed retrieval time.
- Positioning: a calm, accountable valet service with a clear handoff at every stage.
- Personality: composed, clear, attentive. Operational confidence without luxury clichés or technology jargon.
- Principles: one obvious next action; show real status; preserve accountability; respect the guest's time.

## Logo system
The supplied **handoff mark** uses two opposing rounded paths: one receives, the other returns. It references the service exchange without depicting a specific car brand or claiming to be an Arabic letter. The Arabic wordmark is the primary name; the English name supports mixed-language contexts.

Files in `brand/assets/`:
- `mark.svg`: plum/gold transparent vector.
- `mark-on-plum.svg`: white/gold on plum square for avatar/icon use.
- `mark-mono.svg` and `mark-white.svg`: single-color variants.
- `logo-ar.svg`, `logo-en.svg`, `logo-bilingual.svg`: outlined typography; no font installation needed to render the logos.
- `logo-bilingual-reversed.svg`: white/gold lettering for dark backgrounds.

Use at least one stroke-width of clear space around the mark; preferred clear space is 16 units on its 128-unit canvas. Minimum standalone mark: 24 CSS px, with monochrome preferred below 32 px. Arabic/English lockups: minimum 160 px wide; bilingual lockup: 220 px. At smaller sizes show the mark alone and a text accessible name.

Do not stretch, rotate, add shadows/glows, rebuild the Arabic wordmark in another font, recolor the brand to WhatsApp green, or place it on busy photos. Never mirror the logo when switching direction. Use a full light or reversed asset rather than applying CSS filters. For production app icons, export exact platform sizes from the vector and inspect small-size legibility.

## Color tokens
| Token | Hex | Role |
|---|---|---|
| plum | #251B35 | Brand anchor, navigation, primary text on gold |
| purple | #62429B | Primary action and focus accents |
| gold | #C6A15B | Handoff accent, small highlights; not small text on white |
| paper | #F7F4EE | Warm page background |
| surface | #FFFFFF | Cards, dialogs, forms |
| ink | #25202D | Main content |
| muted | #655D70 | Secondary text |
| border | #DCD5E3 | Decorative separators; not sufficient by itself for input/focus boundaries |
| control-border | #857990 | Input boundary where required |
| success | #216E53 | Completed/ready semantic state |
| warning | #8A5B00 | Waiting/late attention |
| danger | #B42332 | Error, critical delay, active safety hold |
| info | #245EA8 | Informational/in-progress state |

Prefer mostly paper/white with plum typography and restrained purple/gold accents. A large operations dashboard should remain light and readable under venue lighting. Use white text on purple/plum; plum text on gold; ink/muted on paper or white. Gold-on-white and white-on-gold are decorative-only, not normal text combinations. Exact computed ratios are in `brand/contrast-report.json`.

Target WCAG AA contrast: normal text ≥4.5:1 and large text ≥3:1. Relevant UI boundaries/focus indicators require adequate non-text contrast too. Pair colors with labels/icons; never distinguish parked, ready and delayed by color alone. Final component accessibility must be tested, not inferred from the palette.

## Typography
Self-host bundled **Noto Sans Arabic** for Arabic and **Noto Sans** for English. Use Regular 400 and Bold 700. Font files and their distribution copyright/license notice are included in `brand/fonts/`; preserve that notice when distributing them. Do not load fonts from an external CDN in production by default.

| Role | Size / line height | Weight |
|---|---|---|
| Brand display / marketing | 40–56 px / 1.35 Arabic, 1.15 English | 700 |
| Screen title | 28–32 px / 1.4 | 700 |
| Section title | 20–24 px / 1.45 | 700 |
| Body / forms | 16 px / 1.65 Arabic, 1.5 English | 400 |
| Supporting text | 14 px / 1.6 | 400 |
| Ticket/status metrics | 28–36 px / 1.2 | 700, tabular numerals |

No Arabic tracking. Do not shrink operational copy below 14 px to fit. Keep phone numbers, collection codes and machine identifiers in isolated LTR spans using `bdi`/`dir=ltr`; render Arabic prose RTL. Normalize input digits internally. Proposed UI default: 0–9 for operational identifiers to match WhatsApp, printed key labels and system exports. Dates/times localize to Asia/Riyadh; store UTC internally.

## Layout and components
- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64 px.
- Radius: 8 px inputs, 12 px cards, 16 px dialogs. Pills only for statuses and compact chips.
- Light border and restrained shadow; avoid glass panels, gradient-heavy backgrounds and decorative animation in operations.
- One primary action per panel, explicit destructive labels and confirmation for irreversible actions.
- Primary controls at least 44 × 44 CSS px; larger for mobile quick actions. Never put two dangerous/opposite actions tightly adjacent.
- Keyboard focus: visible 2 px purple outline with a light offset gap. On dark surfaces use a light contrasting focus ring.
- Motion: 120–180 ms subtle transitions; honor reduced motion. No auto-animated status that implies live data when disconnected.
- Empty states explain the next useful action. Loading, failed, stale and offline states are separate components.
- Prefer clear iconography plus labels. Never use a car illustration as the only action label.

## Console hierarchy
Supervisor home starts with attention: unaccepted/expired tasks, oldest queued request, failed guest contact, critical delays and safety incidents. Then show state counts, live requests and team availability. Scope the screen visibly to one event. No executive charts above urgent work.

Manager adds event setup, team directory, reports and incident closure. Admin adds timing/template/retention settings and restricted exports. Super admin controls integrations. Permission-specific navigation must agree with server authorization.

Each live request row includes ticket, vehicle identifier, elapsed wait, stage, assignee, location/key reference as authorized, and the relevant action. Show timestamp of last refresh and stale banner on connection loss. Full guest phone is revealed only for an authorized operational need and audited when appropriate.

## WhatsApp visual limits and tone
The PDF message cards are visual illustrations, not custom WhatsApp UI or guaranteed template layouts. Actual WhatsApp bubbles, typography, colors and buttons are controlled by WhatsApp. Brand the sender profile, logo and message wording; do not promise a purple chat interface.

Use concise Arabic: “استلمنا طلبك”، “طلبك في الانتظار”، “جارٍ إحضار مركبتك”، “مركبتك جاهزة”. Never say retrieval is underway when only queued. Use “تعذّر إرسال الرسالة. تحقّق من الرقم.” instead of technical provider errors. Staff messages identify the ticket and next action without jargon. See complete bilingual messages in `docs/04_WhatsApp_and_Messages.md`.

## Implementation assets and review
`brand/tokens.json` is the source of palette/spacing/type values; `brand/tokens.css` is the starter CSS mapping. Use semantic names, not scattered raw hex values. The included PDFs and PNG are review references, not app code. Approve the visual direction before creating screen implementations. Any change to the identity should update DESIGN.md, tokens and assets together.

