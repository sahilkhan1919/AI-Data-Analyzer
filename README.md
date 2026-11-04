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

---

## Database Configuration

### Local Development (SQLite)
Default setup requires zero configuration:
```env
DATABASE_URI=sqlite:///csv_dashboard.db
```
Development and test tables are initialized on startup. Production schema changes use Alembic migrations; `create_all()` is not used in production.

### Production Deployment (PostgreSQL)
Use an externally provisioned PostgreSQL database and set its connection string in the deployment environment:
```env
FLASK_ENV=production
DATABASE_URI=postgresql+psycopg://<user>:<password>@<host>:5432/<database_name>
SECRET_KEY=<high-entropy-secret-of-at-least-32-bytes>
ALLOWED_ORIGINS=https://<your-frontend-origin>
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=None
UPLOAD_FOLDER=/var/data
```
Keep secrets in the hosting provider's secret manager, not in this repository. A durable/shared storage volume is required for dataset files; `render.yaml` is an example, not proof that the deployed service or database is provisioned. The current Render example requires an externally supplied `DATABASE_URI` and `ALLOWED_ORIGINS`.

Run schema migrations before starting production workers:
```bash
cd backend
alembic -c alembic.ini upgrade head
```
For an existing database whose tables were created before Alembic was introduced, the initial migration reconciles missing migration-managed tables/columns and records the revision. Back up the database before its first production migration.

---

## Environment Variables (Backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` or `production` |
| `PORT` | `5001` | Backend HTTP port |
| `DATABASE_URI` | Local SQLite path | SQLAlchemy connection URI; production requires `postgresql+psycopg://` |
| `SECRET_KEY` | Required (no default) | Stable, environment-provided high-entropy secret of at least 32 bytes; required in every environment |
| `DATASET_CLEANUP_TOKEN` | Unset (cleanup disabled) | Private scheduler/admin Bearer credential for global expired-dataset cleanup |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Login attempts allowed in a window |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `900` | Login rate-limit window in seconds |
| `DATASET_EXPIRATION_HOURS` | `24` | Dataset expiration lifetime in hours |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` in production with HTTPS |
| `SESSION_COOKIE_SAMESITE`| `Lax` | SameSite cookie policy |
| `MAX_UPLOAD_BYTES` | `10485760` (10 MB) | Maximum upload size in bytes |
| `UPLOAD_FOLDER` | `uploads` | Directory for temporary exports and dataset files |
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

### Core & Analytical Endpoints (Protected by `@login_required`)
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Health check endpoint |
| `POST` | `/upload` | Upload and clean CSV/Excel with database metadata persistence |
| `POST` | `/chart-data` | Generate chart data (Bar, Line, Pie, Scatter, Histogram) |
| `POST` | `/insights` | Basic statistical insights for selected columns |
| `POST` | `/ask` | Rule-based natural-language Q&A |
| `GET` | `/download/<dataset_id>` | Stream cleaned CSV dataset |
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

**Latest verification: 268 passed; 1 optional PostgreSQL integration test is skipped unless `TEST_POSTGRES_DATABASE_URI` is supplied.**

The optional integration test runs Alembic and the authenticated analytics/report workflows against a disposable PostgreSQL database:
```bash
TEST_POSTGRES_DATABASE_URI='postgresql+psycopg://<user>@<host>:5432/<disposable_database>' \
  python -m pytest tests/test_phase4_postgresql.py -v
```

### Frontend Test Suite (Vitest)
```bash
cd frontend
npm test
```

**Latest verification: 15 passed (100% pass rate).**
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
**Latest verification: build succeeded.** Vite reports a bundle-size advisory for the 638.85 kB minified JavaScript chunk (193.12 kB gzip).

The Phase 4 PostgreSQL integration was run against a temporary local database, which was dropped after verification. Production deployment, managed PostgreSQL, target-host storage durability, and browser behavior behind the production proxy have not been verified. The Render example uses one Gunicorn worker with four threads and a persistent disk; horizontal multi-instance deployments need shared object storage or another explicitly shared durable storage solution.

For the one-worker Gunicorn restart test, local PostgreSQL integration, migration results, and remaining deployment limitations, see [`docs/PHASE3_SECURITY_REMEDIATION.md`](docs/PHASE3_SECURITY_REMEDIATION.md). These local checks do not certify production readiness.

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
│   ├── storage.py                         ← Filesystem raw & cleaned dataset storage
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
