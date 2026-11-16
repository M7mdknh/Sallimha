# Decisions needed from the owner (2026-11-16)

Each item blocks staging (S), production (P) or only fine-tunes behaviour (T). Nothing here needs a secret value in
chat; secrets go straight into the hosting provider's secret store.

## Hosting
| # | Decision | Blocks | Notes |
|---|---|---|---|
| H1 | Hosting provider and account owner | S | Must run one container image as web + always-on worker + release job, managed PostgreSQL 16+ with point-in-time recovery, a private S3-compatible bucket, HTTPS (infra/staging/README.md) |
| H2 | Region / data location for guest phones and vehicle photos | S | A legal/business owner decides whether Saudi data-protection rules require in-Kingdom storage (ADR-0004 makes no legal determination) |
| H3 | Staging and production domain names | S | Staging host for `DJANGO_ALLOWED_HOSTS`; DNS control for TLS |
| H4 | Recovery targets: RPO (proposed ≤ 15 min) and backup retention | P | Retention of backups also sets how long retired encryption keys must be kept (ADR-0009) |
| H5 | Monitoring, alert recipients and on-call owner | P | Uptime check on `/readyz`, worker heartbeat, queue age, failed messages |
| H6 | HSTS for the whole domain (subdomains, preload) | P | Staging starts at 1 hour, subdomains/preload off |

## WhatsApp
| # | Decision / input | Blocks | Notes |
|---|---|---|---|
| W1 | Meta Business portfolio verified; WhatsApp Business Account for Sallimha | S | Owner action in Meta Business Manager |
| W2 | Dedicated staging sender number (test) and later the production number | S | Valets and guests message this number |
| W3 | Display name and business profile (Arabic/English) | S | Shown to guests |
| W4 | Approval of utility templates (AR + EN) for messages sent outside the 24-hour window, incl. the new move messages (relocation offer/accepted/done/cancelled) | S | List in docs/04 and ADR-0007 |
| W5 | Test handsets: at least 3 valets and 3 guests (synthetic people, real phones) | S | For the Gate 4 rehearsal |

## Operations
| # | Decision | Blocks | Notes |
|---|---|---|---|
| O1 | Named business owner and on-call technical owner for each of the 13 runbooks | P | docs/runbooks/README.md |
| O2 | Approve the paperless continuity procedure for a whole-system outage (offline log on staff phones, supervisor verification before any handover) | P | docs/runbooks/whatsapp-outage.md; ADR-0008 |
| O3 | ~~Who may declare a WhatsApp outage~~ — **decided 2026-11-16: managers and above declare and end; supervisors report** | — | ADR-0008 amendment |
| O4 | Whether reconciliation after a system outage must include a photo (currently text evidence + offline log reference, verified by a second person) | T | ADR-0008 |
| O5 | Retention periods for guest phones, intake photos and resolved-incident evidence (currently 0 = never delete) | P | Settings → Data retention |
| O6 | Time zone per venue (all current venues Asia/Riyadh) | T | Venue setting; the console enters and shows times in it |
| O7 | Maximum length of a recordable system outage (24 h) and how far back reconciliation is allowed (30 days) | T | ADR-0008 |
