# Hosting options for staging (and production) — 2026-11-16

**Status: proposal for approval. Nothing purchased, nothing provisioned.** Prices were read from the providers' own
pages on 2026-11-16 (USD, before tax; Saudi VAT 15 % would apply to a KSA entity). "List price" = read from the
official page. "Estimate" = my arithmetic on list prices for the footprint below; the provider's calculator in your
own account is the confirmation step.

## What Sallimha needs (ADR-0004, infra/staging/README.md)
One container image run as: an always-on **web** process, an always-on **worker** (not request-triggered), a one-off
**release job**; managed **PostgreSQL** with point-in-time recovery; a **private S3-compatible bucket** (photos);
**HTTPS** on a custom domain; **backups**; **monitoring/alerts**. Staging footprint: 1 small web + 1 worker, the
smallest managed PostgreSQL, ~20 GB of photos, negligible traffic.

## Region facts that shape the choice
| Provider | In Saudi Arabia? | Source |
|---|---|---|
| Oracle Cloud (OCI) | **Yes** — Riyadh (`me-riyadh-1`) and Jeddah (`me-jeddah-1`), paired for disaster recovery; managed PostgreSQL available in both | [OCI regions](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm), [OCI PostgreSQL FAQ](https://www.oracle.com/sa/cloud/postgresql/faq/) |
| Google Cloud | **Yes** — Dammam (`me-central2`), but customers with a Saudi billing address must buy through the partner CNTXT; others need invoiced billing. List prices may not be what you pay | [Dammam region access](https://docs.cloud.google.com/docs/dammam-region-access) |
| AWS | **Not yet** — the Saudi region is announced for December 2026 | [SPA announcement](https://www.spa.gov.sa/en/w2665748) |
| DigitalOcean | **No** Middle East region; nearest Frankfurt (FRA) or Bangalore (BLR) | [DigitalOcean regional availability](https://docs.digitalocean.com/platform/regional-availability/) |

## The two options compared

### Option A — Oracle Cloud, Riyadh (`me-riyadh-1`), in-Kingdom
| Need | Service | List price (official) | Staging estimate / month |
|---|---|---|---|
| Web | Container Instance `CI.Standard.E4.Flex`, 1 OCPU / 2 GB | E4: $0.025 per OCPU-hour, $0.0015 per GB-hour | $20.44 |
| Worker (always on) | Same, 1 OCPU / 2 GB | as above | $20.44 |
| PostgreSQL + PITR | OCI Database with PostgreSQL, 1 OCPU / 16 GB (the E4 database shape's minimum memory), 50 GB | $0.098 per OCPU-hour service fee on top of compute; $0.072 per GB-month storage; PITR up to 35 days | $110.91 |
| Private photos + backups | Object Storage (S3-compatible API — already supported by the app) | $0.0255 per GB-month; $0.0034 per 10,000 requests | ~$1 |
| HTTPS entry | Flexible Load Balancer, 10 Mbps | $0.0113 per hour + $0.0001 per Mbps-hour | $8.98 |
| Monitoring | OCI Monitoring | first 500 million datapoints free | $0 |
| Outbound data | — | first 10 TB per month free (Middle East) | $0 |
| **Total** | | | **≈ $162 / month (estimate)** |

Production estimate (2 web, worker, two-node PostgreSQL): **≈ $295 / month**.
Sources: [Oracle Cloud price list](https://www.oracle.com/cloud/price-list/) (compute, object storage, load balancer,
monitoring, data transfer), [PostgreSQL pricing](https://www.oracle.com/cloud/postgresql/pricing/), [Container
Instances shapes](https://docs.oracle.com/en-us/iaas/Content/container-instances/container-instance-shapes.htm) (the
E4 shape has no region restriction; only E5 does).
Not confirmed: container instances carry no surcharge over compute; the PostgreSQL minimum storage; whether the
always-free load balancer applies. TLS: the load balancer needs an imported certificate (renewal must be automated).

### Option B — DigitalOcean App Platform, Frankfurt (`fra1`), outside the Kingdom
| Need | Service | List price (official) | Staging / month |
|---|---|---|---|
| Web | App Platform service `apps-s-1vcpu-1gb` | $12.00 / month | $12 |
| Worker (always on) | App Platform worker, same size (workers billed like services) | $12.00 / month | $12 |
| PostgreSQL + PITR | Managed PostgreSQL, single node 1 GiB | $15.00 / month; daily backups + WAL, restore to any point in the previous 7 days | $15 |
| Private photos | Spaces Object Storage (S3-compatible) | $5.00 / month incl. 250 GiB and 1,024 GiB transfer | $5 |
| HTTPS | Built into App Platform (managed certificates on custom domains) | included | $0 |
| Monitoring | Built-in metrics and alerts | included (not priced separately in the pages read) | $0 |
| **Total** | | | **$44 / month (list prices)** |

Production: 2 web, worker, PostgreSQL with standby ($30 + $30), Spaces ≈ **$101 / month**.
Sources: [App Platform pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/),
[PostgreSQL pricing](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/),
[PostgreSQL features (PITR)](https://docs.digitalocean.com/products/databases/postgresql/details/features/),
[Spaces pricing](https://docs.digitalocean.com/products/spaces/details/pricing/).
Not confirmed: encryption-at-rest wording for Spaces (not stated on the pricing page); storage included in the
$15 database plan.

## Recommendation: Option A, Oracle Cloud Riyadh — conditional on two checks
Why: guest phone numbers and vehicle photos are Saudi personal data. Hosting in Riyadh satisfies an in-Kingdom
requirement **if** your legal review asks for one, and still works if it does not; Option B would force a second
migration before production in that case. Oracle publishes one price list for all regions, managed PostgreSQL has
point-in-time recovery up to 35 days, Object Storage speaks the S3 API the app already uses, and Jeddah is the paired
disaster-recovery region. Staging and production on the same provider also makes the provider-level restore test
meaningful.

Costs more and needs more setup than Option B (certificate handling, load balancer, networking). If your legal review
confirms that hosting outside the Kingdom is acceptable and cost matters more, choose Option B.

Before provisioning, in your own Oracle account: confirm Container Instances and PostgreSQL service limits in
`me-riyadh-1`, and price the footprint in Oracle's cost estimator.

## Decisions I need before provisioning (no secrets in chat)
1. **Approve the option and a monthly ceiling** (e.g. staging ≤ $200 including VAT) with a budget alert.
2. **Legal entity and billing for the cloud account** (company name, KSA address/VAT); the account owner adds the
   payment method in the provider's console — I never handle payment details.
3. **Tenancy home region = Riyadh** (an Oracle home region cannot be changed later).
4. **Who gets console access** (named people, MFA required) and who receives billing and incident alerts.
5. **Domain:** which domain, who controls DNS, and the staging host name (e.g. `staging.<domain>`); certificate
   approach (imported certificate with automated renewal vs a purchased certificate).
6. **Point-in-time recovery window** (7–35 days) and backup retention, which also fixes how long retired encryption
   keys are kept (ADR-0009).
7. **Data-location sign-off** from your legal reviewer (docs/decisions-needed.md H2).
