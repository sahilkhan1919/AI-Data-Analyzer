# 📊 AI-Data-Analyzer — CSV Analytics Dashboard

A full-stack AI-powered data analytics and business intelligence platform for analyzing CSV and Excel files, with automated data quality auditing, statistical profiling, dynamic business intelligence KPIs, time-series trends, rule-based Q&A, secure backend authentication, multi-tenant dataset ownership, and SQLAlchemy database persistence.

---

## Features

### Phase 1 — Validation & Core Hardening
- **File Upload** — Secure CSV and Excel (.xlsx) parsing up to 10 MB (configurable).
- **Data Cleaning** — Automatic removal of duplicate rows and handling of missing values.
- **Interactive Charts** — Bar, Line, Pie, Scatter, and Histogram visualizations via Chart.js.
- **Chart Export** — Download high-resolution charts as PNG images.
- **Statistical Insights** — Sums, averages, minimums, maximums, and top category contributors.
- **Ask Your Data** — Rule-based natural-language Q&A interface.
- **Download Cleaned CSV** — Export cleaned dataset.

### Phase 2 — Data Quality & Business Intelligence Engines
- **Data Quality Health Score (0–100)** — Transparent, explainable scoring based on missing cell ratio, row duplication, and IQR outlier volume.
- **Deep Column Profiling** — Semantic data type detection, missing counts & %, unique values, constancy, high-cardinality flags, quartiles (Q1, Q3), median, std deviation, and safe example values.
- **Missing-Value Action Strategies** — Evidence-based, non-destructive recommendations (imputation vs investigation vs removal).
- **Potential Outlier Detection** — Interquartile Range (IQR) method flags statistical extremes without mutating raw data.
- **Dynamic Business KPI Discovery** — Discovers candidate metrics and excludes non-additive IDs, postal codes, and phone numbers.
- **Dynamic Business KPI Calculations** — Total Revenue, Total Profit, Profit Margin (%), Total Quantity, Distinct Orders, Average Order Value (AOV), and Average Discount.
- **Group-Wise Performance Analysis** — Segment comparison with interactive bar charts, highest/lowest performer rankings, and % contribution breakdown.
- **Time-Based Trend Analysis** — Chronological time-series aggregation across Daily, Weekly, Monthly, Quarterly, and Yearly granularities.
- **Period-over-Period (PoP) Comparisons** — Automatically computes absolute and percentage growth/decline between the latest and preceding periods with zero-denominator safety.
- **Deterministic Insights** — Mathematically grounded observations across Performance, Trend, Anomaly, and Data Quality categories.

### Phase 3 — Persistence, Authentication, Lifecycle & Reliability
- **SQLAlchemy Database Persistence** — SQLite for local development and PostgreSQL support through SQLAlchemy and psycopg; deployment readiness still depends on environment verification.
- **Secure Backend Authentication** — User registration and login powered by NIST-approved `scrypt` password hashing and tamper-proof HTTP-only session cookies.
- **Multi-Tenant Dataset Ownership** — Datasets are strictly isolated per user. Cross-tenant access is rejected with `403 Forbidden`.
- **Process Restart Survival** — Datasets and both raw & cleaned representations survive backend process restarts and multi-worker worker pools.
- **Safe Dataset Lifecycle & Expiration** — Configurable expiration (default: 24h) and retryable administrator/scheduler cleanup that keeps failed deletions pending.
- **Cookie CSRF Defense** — Signed per-session CSRF tokens and trusted-origin checks protect cookie-authenticated unsafe methods.
- **Login Throttling** — Database-backed attempt windows are shared by workers and recover automatically after the configured window.
- **Frontend Automated Test Suite** — Comprehensive Vitest and React Testing Library automated test suite verifying forms, auth error handling, session persistence, and tab navigation.
- **Chart.js Filler Plugin Fix** — Properly registered `Filler` plugin to render filled line and trend charts without runtime warnings.

### Phase 4 — Advanced Business Analytics
- **AI Business Analyst** — `/api/ai/analyze` maps supported questions to a limited set of Pandas calculations and returns the interpreted request, method, measured result, explanation, implications, and next action. Unsupported questions are rejected instead of guessed.
- **Optional LLM Explanations** — Set `LLM_API_KEY`, `LLM_API_BASE_URL`, and `LLM_MODEL` to enable an OpenAI-compatible explanation provider. Without a key, deterministic explanations are used. The provider receives the question and calculated result, not the full dataset; configure it only if sending those values to that provider is acceptable.
- **Root-Cause Contributor Analysis** — Compares the latest two observed periods and ranks measured changes across selected dimensions. Results explicitly report association, not causation.
- **Predictive Analytics** — Provides a last-observation baseline with a chronological holdout, MAE/RMSE/MAPE, documented missing-period treatment, and approximate uncertainty bounds. Forecasts are not guarantees.
- **Business Reports** — Generates a user-owned PDF report with data quality, available KPIs, segment performance, deterministic insights, and trend/root-cause/forecast sections when the dataset supports them. Downloads are authorized per user and dataset.
- **Advanced Analytics UI** — Adds AI Analyst, Root Cause, Forecast, and Reports tabs connected to these APIs.

---

## Tech Stack

- **Frontend:** React 18, Vite, Axios, Chart.js, react-chartjs-2, html2canvas, Vitest, React Testing Library
- **Backend:** Python 3.11+, Flask 3.x, SQLAlchemy 2.x, Flask-CORS, Pandas, openpyxl, ReportLab, Gunicorn
- **Testing:** Pytest, pytest-flask, Vitest, JSDOM

---

## Installation & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Set up environment variables locally:
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

`SECRET_KEY` is required in development and production. Generate a strong key
once and store it in `backend/.env` (do not commit it):
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Copy the printed value into `.env` as `SECRET_KEY=<generated-value>`. Keep the
same key across restarts; generating a new key invalidates existing sessions.

Start the backend:
```bash
python app.py
```
*Backend runs at: `http://127.0.0.1:5001` by default. `PORT` in `backend/.env` controls the port.*
For local cookie authentication, open the frontend at `http://localhost:5173` and use the matching API hostname `http://localhost:5001` (or use `127.0.0.1` for both). Mixing `localhost` and `127.0.0.1` makes the browser treat the session cookie as cross-site.

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
*Frontend runs at: `http://localhost:5173`*

For production, leave `VITE_API_URL` unset. Vercel serves the frontend and
proxies its relative API requests to Render using `frontend/vercel.json`, so
browser authentication cookies remain same-origin. Do not put API keys or
other secrets in `VITE_*` variables.

---

## Database Configuration

### Local Development (SQLite)
Default setup requires zero configuration:
```env
DATABASE_URI=sqlite:///csv_dashboard.db
```
Development and test tables are initialized on startup. Production schema changes use Alembic migrations; `create_all()` is not used in production.

### Production Deployment (PostgreSQL)
For Neon, copy the PostgreSQL connection URI from the Neon dashboard and add
`sslmode=require` if it is not already present. The application accepts
`postgresql://`, `postgres://`, and `postgresql+psycopg://` URIs and normalizes
the first two to psycopg 3. Keep the URI in Render's environment settings, not
in the repository:
```env
FLASK_ENV=production
DATABASE_URI=postgresql://<user>:<password>@<host>/<database_name>?sslmode=require
SECRET_KEY=<high-entropy-secret-of-at-least-32-bytes>
ALLOWED_ORIGINS=https://<your-frontend-origin>
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=None
STORAGE_BACKEND=supabase
SUPABASE_S3_ENDPOINT=https://<project-ref>.supabase.co/storage/v1/s3
SUPABASE_S3_REGION=<project-region>
SUPABASE_S3_ACCESS_KEY_ID=<server-side-s3-access-key>
SUPABASE_S3_SECRET_ACCESS_KEY=<server-side-s3-secret-key>
SUPABASE_BUCKET_NAME=<private-bucket-name>
```
Use your existing Supabase project and private bucket. Copy the S3 endpoint,
region, and generated S3 access key pair from the Supabase Storage S3 settings.
The endpoint should include `/storage/v1/s3`; do not include credentials in it.
Keep the bucket private. The application uses server-side S3 credentials and
authenticated backend download routes; it does not create public URLs or expose
credentials to the frontend. Store the access key, secret key, database URI, and
session secrets only in Render's environment settings.

`render.yaml` configures the Render service, Supabase environment variables, a
pre-deploy migration, Gunicorn, and `/api/health`. It does not create the Neon
database, Supabase bucket, or credentials. Existing datasets in an R2 bucket,
local SQLite database, or filesystem are not automatically copied to Neon or
Supabase Storage; migrate/re-upload them separately before switching an existing
deployment.

Run schema migrations against the target database before starting production
workers:
```bash
cd backend
alembic -c alembic.ini upgrade head
```
For an existing database whose tables were created before Alembic was introduced, the initial migration reconciles missing migration-managed tables/columns and records the revision. Back up the database before its first production migration.

### Manual deployment steps (after review)
1. **Neon:** create a PostgreSQL project/database. Copy its connection URI
   (prefer the pooled URI when offered), keep `sslmode=require`, and add it to
   Render as `DATABASE_URI`.
2. **Supabase Storage:** use the existing private bucket and S3 credentials.
   Add `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`,
   `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY`, and
   `SUPABASE_BUCKET_NAME` to Render, and set `STORAGE_BACKEND=supabase`. Keep the
   S3 credentials server-side; never add them to frontend settings.
3. **Render:** connect the reviewed GitHub repository and create the web service
   from `render.yaml` (or configure the same values manually). Set
   `DATABASE_URI`, the Supabase S3 settings, a persistent random `SECRET_KEY`,
   `ALLOWED_ORIGINS`, and `SESSION_COOKIE_SECURE=true`; keep
   `SESSION_COOKIE_SAMESITE=None`. The configured pre-deploy command runs
   `alembic -c alembic.ini upgrade head`; the start command runs Gunicorn and
   the health check uses `/api/health`.
4. **Vercel same-origin API proxy:** deploy the repository on Vercel with
   `frontend` as the root directory, `npm run build` as the build command, and
   `dist` as the output directory. [frontend/vercel.json](./frontend/vercel.json)
   rewrites the frontend's API paths to the Render backend while keeping the
   browser URL on the Vercel origin. Leave `VITE_API_URL` unset in Vercel so
   Axios uses relative same-origin paths. The proxy preserves methods, request
   bodies, and response headers, including the backend's HttpOnly `Set-Cookie`;
   the host-only cookie is then stored for the Vercel domain and sent on later
   API requests. Do not expose the session token to JavaScript or make protected
   routes public.
5. **Browser authentication:** use exact HTTPS origins, never a wildcard.
   Keep Render's production cookie settings `SESSION_COOKIE_SECURE=true` and
   `SESSION_COOKIE_SAMESITE=None`. Keep `ALLOWED_ORIGINS` set to the exact
   frontend origin (for example `https://ai-data-analyzer-sooty.vercel.app`);
   Flask's CORS and trusted-Origin/CSRF checks remain enabled.
6. **Verify:** check `https://<render-service>/api/health`, then use the deployed
   browser to register/login, retrieve `/api/auth/csrf`, upload a CSV, download
   raw and cleaned CSVs, create/download a PDF report, and delete the dataset.
   Confirm the login response sets `csv_session` for the Vercel host and the
   subsequent `POST /upload` uses that cookie and returns 200. Also confirm
   another account cannot access the dataset or report. These steps must be run
   after deployment by the operator; no cloud resources are created by local
   tests.

---

## Environment Variables (Backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` or `production` |
| `PORT` | `5001` | Backend HTTP port |
| `DATABASE_URI` | Local SQLite path | SQLAlchemy URI; PostgreSQL `postgres://` and `postgresql://` URIs are normalized to psycopg 3 |
| `SECRET_KEY` | Required (no default) | Stable, environment-provided secret of at least 32 bytes with high entropy; required in every environment |
| `DATASET_CLEANUP_TOKEN` | Unset (cleanup disabled) | Private scheduler/admin Bearer credential for global expired-dataset cleanup |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Login attempts allowed in a window |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `900` | Login rate-limit window in seconds |
| `DATASET_EXPIRATION_HOURS` | `24` | Dataset expiration lifetime in hours |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` in production with HTTPS |
| `SESSION_COOKIE_SAMESITE`| `Lax` | SameSite cookie policy |
| `MAX_UPLOAD_BYTES` | `10485760` (10 MB) | Maximum upload size in bytes |
| `UPLOAD_FOLDER` | `uploads` | Local filesystem storage root; used when `STORAGE_BACKEND=local` |
| `STORAGE_BACKEND` | `local` | `local` or `supabase`; production requires `supabase` |
| `SUPABASE_S3_ENDPOINT` | Unset | HTTPS S3 endpoint from Supabase Storage; includes `/storage/v1/s3` |
| `SUPABASE_S3_REGION` | Unset | Region shown in the Supabase project's S3 settings |
| `SUPABASE_S3_ACCESS_KEY_ID` | Unset | Server-side Supabase S3 access key; secret |
| `SUPABASE_S3_SECRET_ACCESS_KEY` | Unset | Server-side Supabase S3 secret key; secret |
| `SUPABASE_BUCKET_NAME` | Unset | Existing private Supabase Storage bucket name |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated CORS allowed origins |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LLM_API_KEY` | Unset | Optional API key for an OpenAI-compatible explanation endpoint |
| `LLM_API_BASE_URL` | OpenAI-compatible chat-completions URL | Optional provider endpoint; set only when using an LLM |
| `LLM_MODEL` | `gpt-4o-mini` | Optional model identifier used by the configured provider |

---

## API Endpoints

### Authentication Endpoints (Phase 3)
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/api/auth/register` | Register a new user (email, password) & set session cookie |
| `POST` | `/api/auth/login` | Log in with credentials & set HTTP-only session cookie |
| `POST` | `/api/auth/logout` | Log out and invalidate session cookie |
| `GET` | `/api/auth/me` | Retrieve profile of currently authenticated user |
| `GET` | `/api/auth/csrf` | Retrieve the current session's CSRF token |
| `GET` | `/api/datasets` | List the authenticated user's active datasets |
| `DELETE` | `/api/datasets/{dataset_id}` | Safely delete one owned dataset and its generated reports |

### Lifecycle & Maintenance Endpoints
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/api/datasets/cleanup` | Trigger retryable cleanup using `Authorization: Bearer <DATASET_CLEANUP_TOKEN>` |

### Health Check Endpoints (Public)
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Root status endpoint |
| `GET` | `/api/health` | Render health-check endpoint; reports process liveness |

### Core & Analytical Endpoints (Protected by `@login_required`)
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/upload` | Upload and clean CSV/Excel with database metadata persistence |
| `POST` | `/chart-data` | Generate chart data (Bar, Line, Pie, Scatter, Histogram) |
| `POST` | `/insights` | Basic statistical insights for selected columns |
| `POST` | `/ask` | Rule-based natural-language Q&A |
| `GET` | `/download/<dataset_id>` | Stream cleaned CSV dataset |
| `GET` | `/download/<dataset_id>/raw` | Stream the original raw CSV for its owner |
| `GET/POST` | `/api/data-quality` | Full data quality report (health score, profiling, outliers) |
| `GET/POST` | `/api/data-profile` | Structural overview and column-level profiling |
| `POST` | `/api/bi/kpis` | Dynamic business KPIs discovery and calculations |
| `POST` | `/api/bi/group-analysis` | Group-wise segmentation and rankings |
| `POST` | `/api/bi/trends` | Time-series trend aggregations across granularities |
| `POST` | `/api/bi/period-comparison` | Period-over-period growth/decline comparison |
| `POST` | `/api/ai/analyze` | Evidence-backed natural-language analysis for supported questions |
| `POST` | `/api/analytics/root-cause` | Period change decomposition across selected dimensions |
| `POST` | `/api/analytics/forecast` | Evaluated naive forecast baseline with uncertainty and metrics |
| `POST` | `/api/reports` | Generate a user-owned business PDF report |
| `GET` | `/api/reports` | List reports for the authenticated user's active datasets |
| `GET` | `/api/reports/{report_id}/download` | Download a report after owner and dataset authorization |

---

## Running Automated Tests

### Backend Test Suite (Pytest)
```bash
cd backend
python -m pytest tests/ -v
```

**Latest verification: 309 passed, 1 skipped.** The skipped test is the optional PostgreSQL integration test, `tests/test_phase4_postgresql.py`; it requires an explicitly configured disposable PostgreSQL database.

To run the optional PostgreSQL integration test, configure `TEST_POSTGRES_DATABASE_URI` with an isolated disposable PostgreSQL database:
```bash
TEST_POSTGRES_DATABASE_URI='postgresql+psycopg://<user>@<host>:5432/<disposable_database>' \
  python -m pytest tests/test_phase4_postgresql.py -v
```

### Frontend Test Suite (Vitest)
```bash
cd frontend
npm test
```

**Latest verification: 19 passed (100% pass rate).**
- Authentication, session initialization, and expired-session tests
- Input and form validation tests
- Auth error display and login/logout tests
- Protected dashboard tabs and analytics rendering tests
- AI Analyst, root-cause, and forecast request/rendering tests
- Dataset selection and report-history tests

### Frontend Production Build
```bash
cd frontend
npm run build
```
**Latest verification: build succeeded** with `VITE_API_URL` set. Vite reports a bundle-size advisory for the 639.56 kB minified JavaScript chunk (193.41 kB gzip).

Neon connectivity and migrations, live Supabase connectivity, and browser behavior on deployed Vercel/Render origins have not been verified. Cross-origin CORS, CSRF, origin checks, and production cookie attributes are tested locally; third-party cookie behavior must still be checked in target browsers.

For the one-worker Gunicorn restart test, migration results, and remaining deployment limitations, see [`docs/PHASE3_SECURITY_REMEDIATION.md`](docs/PHASE3_SECURITY_REMEDIATION.md). These local checks do not certify production readiness.

---

## Repository Structure

```
CSV-Dashboard-Project/
├── backend/
│   ├── app.py                             ← Flask entrypoint & route handlers
│   ├── config.py                          ← Centralized runtime configuration
│   ├── database.py                        ← SQLAlchemy engine & session management
│   ├── models.py                          ← User and Dataset ORM models
│   ├── auth.py                            ← Password hashing, tokens, @login_required
│   ├── rate_limiter.py                    ← Database-backed login throttling
│   ├── alembic.ini and migrations/        ← Versioned schema migration setup
│   ├── storage.py                         ← Local filesystem and private Supabase dataset/report storage
│   ├── dataset_service.py                 ← Lifecycle, ownership, and caching service
│   ├── requirements.txt                   ← Production dependencies (Flask, SQLAlchemy, etc.)
│   ├── requirements-dev.txt               ← Testing dependencies (pytest, pytest-flask)
│   ├── pytest.ini                         ← Pytest configuration
│   ├── .env.example                       ← Environment variable template
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── data_quality.py                ← Data Quality Engine
│   │   └── business_intelligence.py       ← BI & Trends Engine
│   ├── tests/
│   │   ├── conftest.py                    ← Test fixtures with isolated DB & auth
│   │   ├── test_application.py            ← App-level tests
│   │   ├── test_upload.py                 ← Upload endpoint tests
│   │   ├── test_chart.py                  ← Chart generation tests
│   │   ├── test_insights.py               ← Statistical insights tests
│   │   ├── test_ask.py                    ← Q&A tests
│   │   ├── test_download.py               ← Download endpoint tests
│   │   ├── test_data_processing.py        ← Data cleaning tests
│   │   ├── test_error_handling.py         ← Central error handler tests
│   │   ├── test_data_quality.py           ← Phase 2 DQ tests
│   │   ├── test_business_intelligence.py  ← Phase 2 BI tests
│   │   ├── test_api_phase2.py             ← Phase 2 API tests
│   │   ├── test_phase3_auth.py            ← Phase 3 Auth & authorization tests
│   │   ├── test_phase3_persistence.py     ← Phase 3 Database & restart tests
│   │   ├── test_phase3_isolation_and_lifecycle.py ← Phase 3 Multi-tenant & cleanup tests
│   │   ├── test_phase3_security_audit.py  ← Dataset API security regressions
│   │   └── test_phase3_security_remediation.py ← Phase 3 remediation regressions
│   └── uploads/
├── frontend/
│   ├── src/
│   │   ├── App.jsx                        ← Tabbed Analytics Dashboard & Auth UI
│   │   ├── App.css                        ← Design System & Components
│   │   ├── setupTests.js                  ← Vitest testing setup
│   │   ├── __tests__/
│   │   │   └── App.test.jsx               ← Frontend automated test suite
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── docs/
│   ├── PHASE3_IMPLEMENTATION_REPORT.md    ← Comprehensive Phase 3 Engineering Report
│   ├── phase1_baseline_audit.md
│   ├── phase1_implementation_report.md
│   ├── phase1_testing_report.md
│   ├── phase2_data_quality.md
│   ├── phase2_business_intelligence.md
│   └── phase2_testing_report.md
└── render.yaml
```
