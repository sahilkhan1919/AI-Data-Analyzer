# Audit Test Results

**Audit date:** 2026-11-04

## Automated suites

| Layer | Command | Result |
|---|---|---|
| Backend | `cd backend && python3 -m pytest -q` | **268 passed, 1 skipped** (269 collected; 39.77s) |
| Frontend | `cd frontend && npm test` | **15 passed** (1 Vitest file; 5.45s) |
| Frontend production build | `cd frontend && npm run build` | **Passed** |

The skipped test is the opt-in PostgreSQL integration in
`backend/tests/test_phase4_postgresql.py`; the final audit run did not have
`TEST_POSTGRES_DATABASE_URI` configured. The ordinary backend suite uses
isolated SQLite databases and temporary storage. The new tests cover malformed
registration/login payloads, duplicate column normalization and trends, and the
generated-report download callback.

The frontend suite emits a Vite CJS API deprecation warning. The build emits a
main-chunk size advisory: **638.85 kB minified / 193.12 kB gzip**. Both commands
otherwise pass.

No lint or separate type-check command is configured in the inspected package
scripts or backend manifests; none is claimed as run.

## Local runtime and browser checks

| Check | Result |
|---|---|
| Frontend `http://127.0.0.1:5173/` | HTTP 200 |
| Backend `http://127.0.0.1:5001/` | HTTP 200 |
| Credentialed CORS preflight from local frontend | HTTP 200 with exact origin and `Access-Control-Allow-Credentials: true` |
| Unauthenticated `/api/auth/me` | HTTP 401 |
| Registration and login | Passed with a generated temporary account |
| Immediate `/api/auth/me` after login | HTTP 200 |
| Browser refresh/session restore | Passed |
| Logout and replay/session check | Login screen restored; `/api/auth/me` returned 401 |
| Invalid credentials | Rejected with the expected invalid-credentials message |
| Sidebar navigation | All 10 non-overview modules showed their own heading and active state; Overview KPI region absent |
| Browser page-level JS exceptions during module navigation | None observed |
| CSV upload | 13 raw rows cleaned to 12 rows, 6 columns; 1 duplicate removed and 1 missing value handled |
| Chart generation | One Chart.js canvas rendered |
| AI Analyst | Actual API result matched independently calculated revenue sum |
| Root Cause Analysis | Contributor output rendered with non-causal limitation |
| Predictive Analytics | Baseline forecast and holdout metrics rendered |
| PDF report | Generated and immediate download returned HTTP 200, `application/pdf` |
| Temporary test data | Dataset/report deleted through the UI; temporary account removed |

Browser tests used synthetic audit data only. Expected 401 responses were
observed on unauthenticated checks; these are authorization behavior, not
unhandled JavaScript exceptions.

## Independent numerical check

`backend/tests/fixtures/audit_workflow.csv` contains 13 data rows and 6 columns.
Pandas independently reports one duplicate row and one missing cell. After
removing the duplicate and imputing the missing `Revenue` with the mean, the
12-row cleaned revenue sum is **20,181.8182**, matching the AI Analyst API
result. The fixture and expected calculation are reproducible locally.

## Not tested

- The final run’s optional PostgreSQL integration (skipped for lack of an
  explicit disposable database URI).
- A live production deployment, TLS termination, production CORS/cookie
  behavior, provider-managed database, or durable volume restart.
- The optional LLM provider against a live external service.
- Browser upload of a real XLSX (XLSX parsing and API behavior are covered by
  automated backend tests).
- A valid near-limit upload, password-protected/corrupt XLSX, and a formal
  memory/latency benchmark.
