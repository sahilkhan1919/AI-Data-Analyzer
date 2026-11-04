# End-to-End Project Audit Report

**Audit date:** 2026-11-04  
**Project:** AI Data Analyzer / CSV Dashboard

## Executive status

The application is a working local React/Vite + Flask analytics product with
authentication, file persistence, data-quality and BI calculations, an
evidence-backed AI analyst, descriptive contributor analysis, baseline
forecasting, and protected PDF reports. The audit ran the complete available
backend and frontend suites, the production build, and a browser workflow using
a temporary account and a reproducible synthetic CSV.

Three runtime/code defects were confirmed and fixed during the audit:

1. A newly generated PDF’s download button passed the click event where the
   report ID was expected, so the endpoint received `[object Object]` and
   returned HTTP 400. The callback now invokes the downloader without an event;
   a frontend regression test and browser download both pass.
2. Column whitespace normalization could turn distinct headers into duplicate
   names. A trend calculation then raised `ValueError: cannot assemble with
   duplicate keys` and returned HTTP 500. Cleaning now assigns deterministic
   suffixes to collisions; direct and upload-to-trends regressions pass.
3. Non-object JSON or non-string email/password fields in registration/login
   could trigger attribute/type errors and HTTP 500. These now return
   structured HTTP 400 errors; regression cases cover both endpoints.

No unresolved critical or high-severity software defect was found in the
workflows exercised. Production readiness is **not established**: the
application was not deployed, current PostgreSQL integration was skipped, and
production storage, proxy, CORS, and cookie behavior remain unverified.

## Architecture summary

- React 18 and Vite provide the SPA; Axios sends credentialed requests and the
  existing charts use Chart.js.
- Flask exposes the local API and applies explicit CORS, origin/CSRF checks,
  cookie authentication, and ownership checks.
- Signed HTTP-only cookies are verified against a stable `SECRET_KEY`; logout
  revocation is persisted.
- SQLAlchemy uses SQLite locally and supports PostgreSQL through psycopg.
- Raw/cleaned CSVs and generated PDFs are stored on disk; production requires
  durable storage shared by the serving process(es).
- Pandas analytics power data quality, KPIs, trends, deterministic AI
  calculations, root-cause contribution analysis, and forecasts.

See `PROJECT_AUDIT_INVENTORY.md` for the detailed component inventory and
architecture diagram.

## Verified findings and fixes

| ID | Severity | Finding and reproduction | Root cause | Fix and verification |
|---|---|---|---|---|
| AUD-01 | HIGH | Generate a report, then click the immediate “Download PDF” button. Before the fix, the request was `.../[object Object]/download` and returned 400. | React passed the click event as the first argument to a function whose optional first argument is `reportId`. | `AdvancedAnalytics.jsx` wraps the call in `() => downloadReport()`. Frontend regression test verifies the exact report URL; local browser received HTTP 200 `application/pdf`. |
| AUD-02 | MEDIUM | Upload CSV headers `Date, Date ,Revenue`, then request trends using `Date`. Before the fix, cleaned columns contained duplicate `Date` labels and Pandas raised `cannot assemble with duplicate keys`. | `clean_data` stripped whitespace without resolving name collisions. | Assign unique stable suffixes (`Date`, `Date_2`); direct-cleaning and upload-to-trends regression tests pass. |
| AUD-03 | MEDIUM | POST a JSON array or non-string email/password to register/login. Before the fix, non-empty arrays and numeric email values raised uncaught exceptions and returned 500. | Routes assumed an object payload and string-valued fields. | Validate object shape and field types; malformed-auth regression tests now verify structured 400 responses. |
| AUD-04 | MEDIUM | Follow the local README setup from a clean `.env.example` and start Flask. | `SECRET_KEY` is now required in development, but README previously documented a development default and omitted key provisioning. | README now explains one-time key generation, secure persistence, and session invalidation if rotated. |
| AUD-05 | LOW | Run `npm run build`. | Main JS chunk exceeds Vite’s 500 kB advisory threshold. | No code-splitting change was made during this reliability audit. Bundle optimization remains a follow-up. |

## Functional evidence

- Temporary browser user registered and authenticated; the next protected
  `/api/auth/me` request returned 200. Refresh restored the session, and logout
  returned the browser to the auth screen; the old session then returned 401.
- Invalid browser credentials were rejected with the expected message.
- A 13-row CSV fixture uploaded and cleaned to 12 rows and 6 columns, removing
  one duplicate and imputing one missing value.
- Overview rendered actual KPI values; Chart.js produced a canvas.
- Ten non-overview sidebar destinations displayed their own headings, became
  active, and did not render the Overview KPI block. No page-level JavaScript
  exceptions occurred in that navigation check.
- Data quality, BI, trends, AI, root-cause, forecast, dataset management, and
  report pages rendered with the uploaded data. AI total revenue was
  20,181.8182, matching an independent Pandas calculation.
- The latest two periods’ revenue comparison was 2,300 to 2,200 (-4.35%); the
  forecast page displayed holdout metrics and baseline values. Labels clearly
  identify the forecast as a simple baseline and contributor analysis as
  association rather than causation.
- PDF creation, immediate download, and history download were exercised.
  The immediate download returned HTTP 200 with `application/pdf`.
- The temporary dataset/report and account were removed after the live test.

## Test and build status

- Backend: 268 passed, 1 skipped.
- Frontend: 15 passed.
- Production frontend build: succeeded; 638.85 kB minified main chunk
  (193.12 kB gzip) with a Vite size advisory.
- Local backend root health: HTTP 200. Protected profile without a session:
  HTTP 401.
- The optional PostgreSQL integration was skipped in this final run because
  `TEST_POSTGRES_DATABASE_URI` was not configured. Older project documentation
  records a previous temporary local PostgreSQL integration run; it was not
  repeated here.

Exact commands and limitations are in `TEST_RESULTS.md`.

## Module summary

| Module | Local status | Notes |
|---|---|---|
| Overview & Charts | PASS | Real uploaded data, KPIs, and Chart.js render checked |
| Data Quality & Profile | PASS | Module rendering and backend tests; fixture includes missing/duplicate data |
| Business Intelligence | PASS | Live module rendering and API tests |
| Trends & Comparisons | PASS | Live calculated monthly trend and period comparison; duplicate-header bug fixed |
| AI Analyst | PASS | Live deterministic result matches independent Pandas value |
| Root Cause Analysis | PASS | Live contributor output labels association, not causation |
| Predictive Analytics | PASS (baseline scope) | Live last-observation forecast and holdout metrics; not an advanced model |
| Business Reports | PASS | Generation and secure download checked after callback fix |
| Upload Dataset | PASS | Live CSV workflow; XLSX covered by backend tests |
| Dataset Management | PASS | Live listing/deletion cleanup and frontend open test |
| Settings | PASS | Live rendering and navigation state |

No production module status is implied by these local checks. See
`MODULE_VERIFICATION_REPORT.md`.

## Resume-readiness review

These are evidence-based portfolio impressions, not a hiring guarantee.

| Category | Rating / 10 | Basis |
|---|---:|---|
| Technical complexity | 7 | Full-stack app, authenticated multi-tenant data, analytics, persistence, reports |
| Real-world relevance | 8 | Data cleaning, profiling, BI metrics, trends, and downloadable reports |
| Backend engineering | 7 | Flask APIs, SQLAlchemy, validation, ownership, migrations, lifecycle handling |
| Database design | 7 | User/dataset/report ownership and migration support; production DB not verified here |
| Analytics correctness | 8 | Transparent calculations, independent fixture check, broad tests |
| AI implementation | 6 | Deterministic supported calculations with optional explanation provider; not a general agent |
| Security | 8 | Signed cookies, CSRF, rate limiting, revocation, and ownership controls tested locally |
| Testing | 8 | 268 backend and 15 frontend tests plus live local workflow checks |
| Deployment | 4 | Example configuration exists; no production deployment verification |
| Documentation | 8 | Setup, API, phases, security, and audit records; several prior reports predate this audit |
| GitHub presentation | 4 | No Git repository metadata was available to assess commits, issues, or release history |

**Role fit:** Software Engineer 7/10; Python Developer 7/10; Data Analyst 8/10;
AI Engineer 6/10; BI Developer 7/10.

**Accurate resume description:** Built a full-stack CSV/Excel analytics
dashboard with secure multi-user data persistence, explainable data-quality and
BI metrics, deterministic dataset Q&A, baseline forecasting, and protected PDF
reports.

**Resume bullets**

- Implemented Flask APIs for authenticated CSV/XLSX ingestion, data cleaning,
  ownership-scoped dataset persistence, and secure report downloads.
- Built Pandas data-quality, KPI, segment, trend, and period-comparison
  calculations, with regression tests for edge cases such as duplicate headers.
- Integrated a constrained dataset Q&A workflow, descriptive contributor
  analysis, and a holdout-evaluated naive forecast into a React/Chart.js UI.

**Two-minute interview outline:** Explain the upload-to-clean-and-persist flow,
then how user ownership is enforced on every dataset/report access. Walk
through one calculation (quality score or period change) and how its result is
validated against a known fixture. Describe why the AI analyst calculates from
data in Pandas instead of allowing an LLM to invent values, and why root-cause
outputs are associations. Finish with testing/security controls and candidly
state that PostgreSQL and deployment still need target-environment verification.

**Likely interview questions**

1. How do you validate and clean a CSV without losing the raw representation?
2. How are session cookies, CSRF tokens, and logout revocation implemented?
3. How do you enforce tenant ownership for datasets and generated reports?
4. How would you verify a BI metric and handle zero denominators or missing data?
5. Why is the current forecast a baseline, and how would you evaluate a more
   advanced model without leakage?

**Demonstrated skills:** React, Vite, JavaScript, Axios, Chart.js, Flask,
Python, Pandas, SQLAlchemy, SQLite/PostgreSQL support, Alembic, pytest, Vitest,
authentication, CSRF, CORS, authorization, file processing, data profiling,
business analytics, time-series validation, PDF generation, and deployment
configuration.

## Final recommendation

**Local application: verified with fixes. Production deployment: NOT TESTED and
not yet ready to claim as deployed or production-ready.** Next steps are to
configure a staging PostgreSQL instance and durable storage, execute migrations,
test the production origin/TLS/cookie setup, and run browser workflows against
that deployment.
