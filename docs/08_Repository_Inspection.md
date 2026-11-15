# 08 — Repository inspection and tool readiness

Status: **Initial review, 15 November 2026 (Asia/Riyadh).** Read-only inspection; no application code written, nothing committed or deployed.

## Repository state
| Item | Finding |
|---|---|
| Remote | `https://github.com/M7mdknh/Sallimha.git` (public; authenticated user `M7mdknh` has ADMIN) |
| Branch / history | `main` tracking `origin/main`; one commit `fa018d5 first commit` containing only `README.md` (`# Sallimha`) |
| Uncommitted | `README.md` modified (replaced by the handoff README); every other pack file is untracked |
| Application code | **None.** No source, tests, CI workflows, containers, dependency manifests, `.gitignore`, `.env.example` |
| Project Claude config | None (`.claude/`, `.mcp.json` absent). Tooling is inherited from user scope (`~/.claude`, `~/.mcp.json`) |

Conclusion: this is a **new implementation**. No existing application has been audited because none exists. There is no unrelated work to preserve beyond the supplied pack.

## Supplied pack — verified contents
| Path | Verification |
|---|---|
| `CLAUDE.md`, `README.md`, `docs/01`–`07`, `DESIGN.md` | Read in full in the prescribed order |
| `Sallimha_Final_Approach.pdf` (8 pp.) | Text extracted; consistent summary of docs/01–06, no additional requirements |
| `Sallimha_Brand_Identity.pdf` (8 pp.), `Sallimha_Brand_Preview.png` (1632×1020) | Viewed; consistent with DESIGN.md (minor rounding noted in ADR-0005) |
| `brand/assets/*.svg` (8 files) | Valid XML; no `<text>`, scripts or external references; lettering outlined; render correctly in Chromium at 24–360 px |
| `brand/fonts/*.ttf` (4 files) | Noto Sans Arabic 400/700 and Noto Sans 400/700; SIL OFL notice in `LICENSE-Noto.txt`; all four load via `tokens.css` |
| `brand/tokens.json`, `brand/tokens.css` | Values agree with DESIGN.md. One starter-CSS defect found (ADR-0005 C9) |
| `brand/contrast-report.json` | All 12 ratios independently recomputed from tokens; 0 mismatches |
| `Claude_Kickoff.md` | **Referenced by README and PDF p.8 but not present.** Its content was pasted into the session; not recreated |

## Development tool readiness (checked in this session)
PASS means exercised with a real call in this session. Installation alone is not counted as PASS. **Where** says whether the check ran with this repository as the working directory or earlier in the session's temporary folder before the repository was opened. User-scope tools behave identically in both places, because this repo has no project-level tool config.

| Tool | Status | Where | Evidence | Follow-up |
|---|---|---|---|---|
| Superpowers | PASS (stale session) | Repo | Skills load and run. Installed 7.0.2; this session still runs 7.0.0 | Start a fresh session before Phase 0 |
| Impeccable skill + detector | PASS | Temp folder | v4.9.0 in `~/.claude/skills/impeccable`; `impeccable detect` scanned a sample page and returned findings | Re-run inside the repo once UI files exist |
| Impeccable hooks | UNVERIFIED | — | Registered in `~/.claude/settings.json` after this session started; no execution observed | Confirm in a fresh session |
| Playwright MCP | PASS | Repo | Rendered and measured the brand specimen at 1280 px and 360 px. Its output folder `.playwright-mcp/` was written into the repo root and removed | E2E suites will use `@playwright/test` in CI (test runner, not a duplicate tool). Add `.playwright-mcp/` to `.gitignore` in Phase 0 |
| Context7 MCP + skill | PASS | Repo | Used for the Django 6.1, DRF 3.18.3 and PostgreSQL 18 facts in ADR-0001 | — |
| Security Guidance — edit warnings | PASS | Temp folder (smoke test); repo (live hooks) | Pattern hook flagged `eval()`/`innerHTML` in an isolated smoke test. Live PostToolUse/UserPromptSubmit events logged while working in this repo | — |
| Security Guidance — LLM review | **UNVERIFIED** | — | Only Stop run so far was in a non-git folder (“empty review set”). Git baseline for this repo captured at prompt submit | Prove on the first code change in Phase 0 and record the log line |
| GitHub CLI | PASS | Repo | `gh repo view` from the repo root: `M7mdknh/Sallimha`, ADMIN, PUBLIC. Logged in as `M7mdknh` with scopes including `repo` and `workflow`; git credential helper is `gh` | — |
| Docker / Compose | PASS | Repo | Docker 29.7.2 daemon running; Compose v5.5.0; user in `docker` group | Local PostgreSQL 18 will run in Compose |
| Runtimes | PASS | Repo + temp folder | Claude Code 2.1.325, Node 24.18.0 / npm 11.16.0, Python 3.14.4, uv 0.11.26, git 2.53.0, gh 2.97.0, psql client 18.6 | Python 3.14 is supported by Django 6.1 |

No overlapping tools were installed. `ctx7` CLI is absent and unnecessary because the Context7 MCP route works.
