# Project Completion Roadmap

## Current assessment

The project is an existing Flask, SQLAlchemy, Pandas, React, and Vite application. Its Phase 1 upload, cleaning, visualization, chart export, and rule-based Q&A features and its Phase 2 data-quality and business-intelligence engines are implemented. The Phase 3 audit/remediation documents report the eight security findings as fixed; local regression testing confirms the current code continues to pass the Phase 3 suites.

The application now includes dedicated AI Analyst, root-cause analysis, forecasting, PDF reporting, and dataset-management workflows. These features have automated local test coverage, including a PostgreSQL integration run. Production deployment, managed services, external LLM behavior, and multi-instance storage remain unverified.

## Verified baseline (November 4, 2026)

| Area | State | Evidence |
|---|---|---|
| Phase 1 core application | Implemented | Existing upload, chart, insight, download, and data-processing routes and tests |
| Phase 2 quality and BI | Implemented | `backend/analytics/data_quality.py`, `backend/analytics/business_intelligence.py`, related routes and tests |
| Phase 3 security and lifecycle | Implemented locally | Remediation documents and Phase 3 regression tests |
| Phase 4 analytics, reports, and dataset management | Implemented and locally tested | Analytics, ownership, report lifecycle, and migration tests |
| Backend regression suite | Passes locally | 268 passed; 1 optional PostgreSQL test skipped in the latest audit run |
| PostgreSQL integration | Not repeated in latest audit | Earlier project notes record a temporary local database pass; current run skipped without `TEST_POSTGRES_DATABASE_URI` |
| Frontend regression suite | Passes locally | 15 Vitest tests passing |
| Frontend production build | Builds | `npm run build` succeeds; Vite reports a large-chunk advisory |
| Production deployment | Not verified | No deployment credentials or production environment were provided |

Passing local tests are not proof of production readiness. In particular, actual production secrets, allowed origins, proxy-derived client addresses, TLS/cookie behavior, managed PostgreSQL, storage durability, and multi-instance operation must be verified in the target environment.

## Completion stages

### Stage 1 — Preserve and verify the existing application

- Keep all Phase 1–3 APIs, tests, and behavior intact.
- Run backend and frontend regression suites and the production frontend build after related changes.
- Add regression tests for new APIs, ownership checks, failure paths, and user-facing flows.

**Exit criteria:** Existing suites remain green; no existing test is weakened or removed.

**Status:** Implemented and locally verified. The latest audit run passed 268 backend tests, 15 frontend tests, and the production frontend build.

### Stage 2 — Evidence-backed AI Business Analyst

- Add a dedicated analytics service that classifies supported questions into an allowlisted set of Pandas operations.
- Calculate results from the authenticated user's dataset; never execute generated Python or SQL.
- Return the interpreted question, calculation method, result, explanation, implications, recommended action, and chart-ready data when applicable.
- Explain unsupported questions rather than guessing.
- Keep any LLM integration optional and configuration-driven; deterministic calculations remain available without credentials.
- Do not send raw dataset contents or follow instructions embedded in data as trusted instructions.

**Exit criteria:** Unit and API tests prove supported operations use actual values, unsupported requests are explicit, prompt-like cell contents do not change the calculation plan, and cross-user dataset access remains denied.

**Status:** Implemented and locally tested. Deterministic calculations are available without credentials; optional external LLM responses were not verified against a live provider.

### Stage 3 — Root-cause analysis

- Compare the latest and immediately preceding comparable periods for a selected KPI.
- Attribute observed changes across available categorical dimensions and rank contributors by measured impact.
- Include supporting calculations and explicitly distinguish association from proven causation.
- Provide understandable limitations when dates, periods, or dimensions are insufficient.

**Exit criteria:** Deterministic fixtures verify period selection, signed contribution ranking, edge cases, and non-causal wording.

**Status:** Implemented and locally tested. Results describe measured contributors and do not claim causation.

### Stage 4 — Predictive analytics

- Validate dates, measures, history length, and requested horizon.
- Aggregate to explicit time periods, make missing-period treatment visible, and establish a simple baseline.
- Use a chronological holdout split; report MAE/RMSE and MAPE only where its denominator is valid.
- Return a forecast interval/uncertainty note and state when the data is unsuitable.

**Exit criteria:** Tests cover leakage-safe splitting, irregular/missing periods, zero-valued actuals, invalid horizons, and insufficient history.

**Status:** Implemented and locally tested as a last-observation baseline with chronological holdout metrics and explicit uncertainty limitations.

### Stage 5 — Business reports

- Generate a downloadable PDF with dataset overview, quality, KPIs, performance/trends, evidence-backed insights, and recommendations.
- Include root-cause and forecast sections only when calculated and suitable.
- Store report metadata with an owner and dataset association; authorize every download.
- Bound memory and work for larger datasets and do not reveal internal storage paths.

**Exit criteria:** PDF generation, ownership denial, missing-file/error handling, and report-content tests pass.

**Status:** Implemented and locally tested, including report metadata migration, ownership-scoped listing/download, and cleanup when an owned dataset is deleted.

### Stage 6 — Frontend workflows

- Preserve the existing React application and visual patterns.
- Add responsive AI Analyst, Root Cause, Predictive Analytics, and Reports views connected to the corresponding APIs.
- Include loading, empty, unsupported-data, and API error states; do not display fabricated results.
- Keep authentication, CSRF, expired-session handling, and dataset ownership behavior consistent.

**Exit criteria:** Component/API tests exercise the new flows, session expiry, and failure states; production build succeeds.

**Status:** Implemented and locally tested. The existing dashboard remains available alongside the new AI Analyst, Root Cause, Forecast, Reports, and Datasets tabs.

### Stage 7 — Storage, deployment, and operations

- Confirm configured storage is durable and available to every worker that must serve a dataset. The current Render disk example is suitable only within its documented service/instance constraints; horizontal scaling may require object storage.
- Document production environment variables, migrations, secrets, CORS, cookies, scheduled cleanup, backups, and operator recovery.
- Verify startup, migrations, restart persistence, and worker sharing against the actual target environment before claiming production readiness.

**Exit criteria:** A real target deployment passes documented smoke, migration, persistence, authorization, cookie, and recovery checks. Until then, deployment status remains unverified.

**Status:** Partially prepared, not production verified. A temporary local PostgreSQL integration passed and deployment configuration is documented, but no managed database, target hosting environment, multi-instance storage, or production cookie/proxy behavior was exercised.

### Stage 8 — Completion report

- Create `docs/FINAL_PROJECT_COMPLETION_REPORT.md` with architecture, completed work, security resolutions, tests, deployment evidence, limitations, and remaining work.
- Label each status distinctly as implemented, unit tested, integration tested, runtime verified, production deployed, or production verified.

**Exit criteria:** Every status is supported by evidence and no feature is marked complete solely because code exists.

**Status:** Complete. See [the final completion report](./FINAL_PROJECT_COMPLETION_REPORT.md).

## Known gaps and constraints

- The optional external LLM provider was not configured or tested live; deterministic analysis remains available.
- Forecasting is a simple baseline, not a validated advanced forecasting model; root-cause results are contributor associations, not causal findings.
- Dataset and PDF files use the local filesystem abstraction. The configured service disk is not evidence of shared storage or multi-instance durability.
- No production deployment, managed PostgreSQL operation, production cookie/proxy behavior, or backup/recovery drill was verified.
- The current large frontend bundle emits a Vite size advisory.
- External LLM, object-storage, managed-database, and hosting credentials are not present in the workspace; those integrations remain optional or externally unverified.
