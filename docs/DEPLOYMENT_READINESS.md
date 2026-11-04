# Deployment Readiness

**Decision:** **NOT TESTED in production; do not claim deployed or production
verified.** Local code and build checks pass, and an example Render manifest
exists. Important production dependencies and host behavior remain unverified.

## Readiness matrix

| Requirement | Status | Evidence / next action |
|---|---|---|
| Production mode and debug disabled | CONFIGURED, not deployed | `FLASK_ENV=production` in `render.yaml`; verify effective runtime settings after deploy. |
| Stable signing key | CONFIGURED, not deployed | Required by `config.py`; Render manifest generates a value. Provision independent target secret; never copy local `.env`. |
| PostgreSQL URI | CONFIGURED, not connected | Production startup requires `postgresql+psycopg://`; final optional PostgreSQL integration was skipped. Create disposable staging DB and run migrations/workflows. |
| Database migrations | CONFIGURED, locally covered | Render pre-deploy invokes Alembic; verify migration/rollback procedure against a disposable staging database and back up before first migration. |
| CORS and CSRF | LOCALLY VERIFIED | Explicit origins and credentials; exact local preflight passes. Set the exact deployed frontend origin and browser-test unsafe requests. |
| HTTPS and session cookies | CONFIGURED, not tested | Production `Secure` and configured SameSite policy; verify TLS termination and browser cookie behavior on deployed domains. |
| Dataset and report storage | PARTIALLY CONFIGURED | Render example mounts `/var/data`. Verify persistence after restart, disk capacity, backups, restore, and any multi-instance access. |
| Multiple backend instances | NOT TESTED | Render example uses one Gunicorn worker; local disk is not shared across instances. Use shared object storage before horizontal scaling. |
| App server | CONFIGURED | Example uses Gunicorn rather than Flask development server; verify health and timeout behavior on the target plan. |
| Health/readiness | PARTIAL | `/` returns a liveness message and HTTP 200 locally; it does not establish database or storage readiness. Add/verify an operational readiness probe if required. |
| Upload limits | CONFIGURED | Default 10 MiB Flask request limit. Validate platform proxy/request limits and disk capacity in deployment. |
| Cleanup scheduler | CONFIGURED, not operated | Endpoint requires a secret; arrange a protected scheduled task and alerting for retryable cleanup failures. |
| Frontend deployment/API URL | PARTIAL | Local host fallback verified; production deployment must set `VITE_API_URL` to the API service origin. |
| Observability and backups | NOT TESTED | Configure log aggregation, retention, alerting, database backup, and file-storage backup/recovery. |

## Local evidence

- Local frontend/backend are responsive at ports 5173/5001.
- Credentialed CORS preflight succeeded for `127.0.0.1:5173`.
- Authentication, upload, analytics, and report download worked in the local
  browser workflow.
- Production frontend build succeeds but has a 638.85 kB main-chunk advisory.

## Required before launch

1. Provision staging PostgreSQL and durable storage, then run Alembic migrations.
2. Test authenticated registration/login/refresh/logout, CSRF, cross-user access,
   upload, dataset restart persistence, report download, and cleanup against the
   deployed host and exact frontend origin.
3. Confirm HTTPS cookie behavior and proxy IP/rate-limit behavior.
4. Verify backup and restore, monitoring, and cleanup scheduling.
5. Re-run all suites and production build in CI on the deployment runtime.

No credentials or production access were supplied; no deployment was attempted.
