# Sallimha | سلّمها

WhatsApp-first valet operations: valets work entirely in WhatsApp; supervisors and management use a bilingual
(Arabic RTL / English LTR) web console for live monitoring, shift operations and exception handling.

**Status (branch `build/phase-0-2`):** Phases 0–2 built and tested locally. Nothing is deployed. All WhatsApp
behaviour runs through a **simulated** transport and simulator page; no real WhatsApp account has been
connected. Evidence: [docs/evidence/gate-2.md](docs/evidence/gate-2.md), [docs/evidence/gate-3.md](docs/evidence/gate-3.md).
Staging inputs: [docs/staging-inputs.md](docs/staging-inputs.md).

## Local demo

### Prerequisites
Docker (for PostgreSQL), [uv](https://docs.astral.sh/uv/) (installs Python 3.14 and the backend), Node.js 24,
`curl` and `make`. Free local ports: 55432 (PostgreSQL), 8100 (API), 5180 (console).

### Start
```bash
make demo
```
This starts PostgreSQL in Docker, installs dependencies, migrates, seeds **synthetic** data, runs the API and
the worker, builds the console and serves it at **http://127.0.0.1:5180**. `make demo` opens mid-event (tickets
being received, parked and retrieved, with alerts). For the walkthrough below, start from an empty event:
```bash
make demo-clean
```
Stop with Ctrl+C, then `make stop` to stop PostgreSQL. Each start reseeds the demo database.

### Accounts (synthetic, local-only)
| Username | Role | Second factor |
|---|---|---|
| `supervisor` | Supervisor | — |
| `manager` | Manager | `make demo-code WHO=manager` |
| `admin` | Admin | `make demo-code WHO=admin` |
| `owner` | Super admin | `make demo-code WHO=owner` |

Passwords are in `DEMO_PASSWORDS` in [services/api/ops/management/commands/seed_demo.py](services/api/ops/management/commands/seed_demo.py).
They exist only in local/test databases; the settings refuse the simulator outside local/test. Valets have no
console account: in the demo they are the simulated phones +966550000101 (ماجد), +966550000102 (سارة) and
+966550000103 (فهد).

### Walkthrough: registration to verified delivery
The console opens in Arabic; **English** in the top bar switches to English. Labels below are Arabic (English).
1. Sign in as `supervisor`. The live view shows *يحتاج انتباهك* (Needs your attention), the open requests and the
   team with three valets on shift. The header shows *واتساب: محاكاة* (WhatsApp: simulated).
2. Open **المحاكي** (Simulator). The banner states that no message reaches a real phone. Choose ماجد's phone
   (+966550000101) and send `مركبة جديدة`.
3. Send the guest number `0501234567`, tap **تأكيد الرقم**, then **نعم، استلمها** once the guest confirms in
   person that the ticket arrived (provider delivery status alone is never enough).
4. Send the plate and description, e.g. `ABC 1234 كامري بيضاء`, then press **صورة** (Photo) four times.
5. Tap **بدء الركن** (Start parking), send the location `A 12`, then the key hook `15`. The car is parked.
6. Open the guest phone (+966501234567) and tap **اطلب سيارتي** (Request my car).
7. Back in **التشغيل المباشر** (Live operations) the request appears with its wait time and the valet it was
   offered to. In that valet's simulator thread tap **قبول** (Accept), then **السيارة جاهزة** (Car ready).
8. The guest thread now shows a six-digit collection code. In the valet thread, type that code (the guest shows
   it at the stand), then tap **تم التسليم** (Delivered). The live counter *سلّمت* (Delivered) increases.

### Walkthrough: exception handling
1. As `supervisor`, register a second car with فهد (+966550000103) as above (plate `PLT 7788`, location `B 7`,
   hook `77`), without requesting it.
2. In the live view use **البحث عن تذكرة** (Find a ticket) with `PLT` and open the ticket.
3. **إيقاف سلامة** (Safety hold) with a reason: retrieval and handover are blocked and the hold shows on the
   ticket. **رفع الإيقاف** (Clear hold) with a reason releases it.
4. **فتح بلاغ** (Open incident), category *ضرر* (Damage). Follow the link to **البلاغات** (Incidents) and add a
   note. Supervisors cannot resolve.
5. **اقتراح غير مُستلمة** (Propose unclaimed) with a custodian and plan.
6. Sign out, sign in as `manager` (enter the code from `make demo-code WHO=manager`). In **البلاغات** (Incidents)
   resolve the incident with an outcome. In **المركبات المتبقية** (Carryover) open the proposed car and choose
   **اعتماد غير مُستلمة** (Approve unclaimed): the key stays on its hook. **تحرير المفتاح والمركبة** (Release key
   and car) later records how it left and frees the hook.
7. Also as manager: **المناسبات** (Events) to create or close an event and open its report and CSV export
   (no phone numbers); **الموظفون** (Staff) for the directory and role grants.
8. As `admin`: **الإعدادات** (Settings) for timings, retention (zero = never delete) and message wording;
   **التشغيل الفني** (Operations) for messages needing attention. As `owner`: **التكاملات** (Integrations) shows
   readiness flags only — credentials are never shown or entered in the console.

### Walkthrough: moving a car (relocation)
New valets added in **الموظفون** (Staff) are put on tonight's team from the live view: **إضافة فاليه إلى فريق الليلة**
(Add a valet to tonight's team) starts their shift.

1. As `supervisor`, find a parked car and choose **نقل المركبة** (Relocate car), pick an available valet and a
   reason. The ticket shows *نقل بانتظار القبول* (Move awaiting acceptance); its location does not change.
2. In the simulator, open that valet's phone, tap **قبول** (Accept), then **تم النقل** (Moved), send the new
   location (e.g. `C 3`) and the key hook. The console now shows the new location and hook; the valet is recorded
   as the mover.

### Walkthrough: WhatsApp outage and recovery
The outage is *declared*, not real: the simulated transport keeps delivering, so messages still appear in the
simulator. What this walkthrough shows is the relayed actions, their audit records and the reconciliation.
1. As `supervisor`: **الأعطال** (Outages) → **إعلان عطل واتساب** (Declare WhatsApp outage) with a reason. A red banner
   appears on the live view.
2. When a guest requests a car, the ticket shows *العرض لدى* (Offered to) the valet the system chose. Record their
   radio answer with **تسجيل قبول الموظف (مُرحَّل)**, then **تسجيل جاهزية السيارة (مُرحَّل)**, then finish with
   **تسليم بمساعدة المشرف**. In **الأعطال**, **استلام مركبة نيابة عن موظف** records a new arrival for a valet.
   **إنهاء العطل** ends the outage.
3. As `manager`: **الأعطال** → record a past whole-system outage (venue time), reconcile an intake made during it,
   then on that ticket **تسوية تسليم تم أثناء التوقف** with the actual time, the delivering valet, a different person
   as verifier, the evidence and a reason.

Other exceptions available on a ticket when its state allows: cancel before parking, withdraw a request (with or
without custody resolution), custody transfer, intake transfer, phone correction, supervisor-assisted request and
handover, and relocation. Runbooks: [docs/runbooks/](docs/runbooks/README.md).

## Development
| Command | What it does |
|---|---|
| `make test` | Backend suite (pytest against real PostgreSQL) |
| `make lint` | Ruff and TypeScript type check |
| `make e2e` | Playwright suite (desktop and 360 px mobile); set `PW_CHANNEL=chrome` to use an installed Chrome |
| `make contract` | Regenerate `contracts/openapi.yaml` (fails on any schema warning) and the console's TypeScript types |
| `docker build -t sallimha:local . && scripts/smoke-image.sh` | Build the deployable image and run it with staging settings and placeholder secrets (needs `make db` running) |
| `scripts/rehearse-restore.sh` | Backup and restore rehearsal on the local database, synthetic data (needs `make db` running) |

Django refuses to start unless `SALLIMHA_ENV` is `local`, `test`, `staging` or `production`; the Makefile and
scripts set `local` for you. For a manual command: `cd services/api && SALLIMHA_ENV=local uv run python manage.py …`.

CI (`.github/workflows/ci.yml`) runs the backend suite, the contract drift check, the web build and the
Playwright suite on every push.

---

## Specification pack (handoff v1.0)

Prepared 15 November 2026, Asia/Riyadh. A self-contained specification for Claude Code. The original PDFs and sketch are not required.

### Start here
1. Extract this folder into the root of the Sallimha repository. Keep its relative paths. If files already exist, merge deliberately instead of overwriting them.
2. Read `Sallimha_Final_Approach.pdf` for the operating model and `Sallimha_Brand_Identity.pdf` for the proposed visual identity.
3. Start a fresh Claude Code session from the repository root. Paste `Claude_Kickoff.md`.
4. Claude must first verify the supplied files, inspect any actual application code, and record remaining deployment inputs. It should not ask for the source PDFs.

### What is authoritative
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

### Scope
This pack specifies the product. (When written, it was not an implemented or deployed application; see Status above for what is now built.) No source repository was audited here. The user-provided Claude readiness report described an empty clone. No hosting provider, production domain, WhatsApp account, legal retention schedule, or operating capacity has been verified.

Keep the software deterministic: vehicle assignment, ticket transitions and ownership checks must not depend on an LLM. AI coding tools help build the product; they are not required in its operational request path.

