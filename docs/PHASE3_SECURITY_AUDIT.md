# Phase 3 Security and Reliability Audit

**Audit date:** November 3, 2026  
**Scope:** Current workspace implementation of the CSV Dashboard / AI Data Analyzer  
**Method:** Read-only source review, existing automated suites, isolated runtime probes, and an isolated two-process restart test. No production service or database was accessed.

**Status note:** This report records the initial read-only audit before remediation. The final status of all eight findings and post-remediation verification are appended below.

## Executive summary

The local implementation has working password hashing, signed expiring sessions, persisted logout revocation, per-dataset ownership checks, and local SQLite/filesystem persistence. The audit verified that an uploaded dataset remained queryable and downloadable after stopping and restarting a separate Gunicorn process using the same temporary SQLite database and storage directory.

The existing backend and frontend suites pass. This does **not** establish production readiness. The repository's Render configuration does not define the secret, production mode, database, or durable storage. The current development default uses a known signing key and non-secure cookies. The cleanup endpoint is unauthenticated, cookie-authenticated unsafe methods have no CSRF verification, and cleanup can discard metadata even when file deletion fails.

**Production readiness: Not established.** No deployed environment, production cookie flow, PostgreSQL service, migration process, shared volume, or multi-instance behavior was available to verify.

## Findings

| ID | Severity | Finding |
|---|---|---|
| F-01 | HIGH | Known default session signing key is accepted when `SECRET_KEY` is not configured |
| F-02 | MEDIUM | Dataset cleanup is callable without authentication and acts globally |
| F-03 | MEDIUM | Cleanup can delete metadata after storage deletion fails or before a failed DB commit |
| F-04 | MEDIUM | Cookie-authenticated unsafe requests have no explicit CSRF token or Origin validation |
| F-05 | MEDIUM | Deployment manifest does not configure production settings or durable persistence |
| F-06 | MEDIUM | PostgreSQL and schema migration readiness are incomplete and unverified |
| F-07 | LOW | Frontend does not return to login when a session expires after initialization |
| F-08 | LOW | Login endpoint has no rate limiting or lockout control |

### F-01 — Known default session signing key

**Severity:** HIGH  
**Evidence:** [`backend/config.py`](../backend/config.py) assigns a fixed, source-visible fallback to `SECRET_KEY` when the environment variable is absent (lines 66–68). [`backend/auth.py`](../backend/auth.py) signs and validates session tokens using that key. The deployment manifest [`render.yaml`](../render.yaml) does not declare `SECRET_KEY`. An isolated runtime probe confirmed that the current configuration resolves to the known fallback.

**Reproduction:**
1. Start the application without setting `SECRET_KEY`.
2. Obtain a valid user's UUID.
3. Use the fixed key and the application's token salt to sign a token with that `user_id`.
4. Send that token as the `csv_session` cookie to a protected endpoint such as `GET /api/auth/me`.

The token signature is forgeable in this configuration. Exploitation requires a target user's UUID; account IDs are returned to their owners by registration/profile responses.

**Recommended remediation:** In production, require a strong randomly generated secret from the deployment secret manager and fail startup if it is absent or matches a development fallback. Rotate the key if an exposed/default key has been used in a real deployment; previously signed tokens will then be invalidated.

### F-02 — Unauthenticated global dataset cleanup

**Severity:** MEDIUM  
**Evidence:** [`backend/app.py`](../backend/app.py) defines `POST /api/datasets/cleanup` at lines 334–340 without `@login_required` or another authorization check. It invokes cleanup across all users' datasets. An isolated test-database request without credentials returned HTTP 200.

**Reproduction:** Send `POST /api/datasets/cleanup` with no cookie or authorization header. The route runs the global cleanup operation. It only targets expired rows, which are already inaccessible to analytics, but an unauthenticated caller can choose when all expired users' files and metadata are removed and can repeatedly trigger the database/filesystem work.

**Recommended remediation:** Protect this maintenance operation with an explicit administrative or scheduler credential and rate-limit it. Do not treat CORS as authorization.

### F-03 — Cleanup file/database consistency is not atomic

**Severity:** MEDIUM  
**Evidence:** [`backend/dataset_service.py`](../backend/dataset_service.py) deletes files before deleting rows and committing (lines 173–186). [`backend/storage.py`](../backend/storage.py) catches and logs `OSError` during file deletion (lines 81–90), without reporting failure to the caller. Cleanup then continues to remove the database row and commit. Conversely, if the DB commit fails after successful file deletion, the rollback restores metadata but cannot restore the removed files.

**Reproduction:**
1. Create an expired dataset.
2. Cause `os.remove` to fail for its stored files (for example, revoke file permissions).
3. Run cleanup.
4. Observe that the DB row can be committed as deleted while one or both files remain.

Alternatively, make the final database commit fail after file deletion; the row can remain while its storage files are gone.

**Recommended remediation:** Make deletion retryable and consistent. For example, mark records as pending deletion in a committed transaction, delete files, then remove metadata only after successful deletion; retry pending cleanup. Record and report failures, and add an orphan reconciliation process. Avoid swallowing deletion failures when the caller must preserve metadata.

### F-04 — No explicit CSRF defense for cookie-authenticated unsafe methods

**Severity:** MEDIUM  
**Evidence:** [`backend/auth.py`](../backend/auth.py) sets an HTTP-only cookie with `SameSite` configurable and defaulting to `Lax`; the app configures credentialed CORS for listed origins. No CSRF token, Origin/Referer validation, or equivalent unsafe-method check was found. CORS controls response access and is not itself a general CSRF defense. Some routes accept browser-simple multipart requests, and same-site hostile origins may still send Lax cookies.

**Reproduction:** From a hostile origin that is same-site with the API (for example, an untrusted sibling subdomain), submit a cross-origin form POST to a cookie-authenticated endpoint that accepts form data, such as `/upload`. Verify in a production browser whether the API cookie accompanies the request and whether the operation succeeds. No deployed browser/origin setup was available, so exploitability in a particular deployment is not confirmed.

**Recommended remediation:** Add CSRF protection for cookie-authenticated state-changing requests, preferably a synchronizer/double-submit token or strict Origin validation against the configured frontend origins. Keep `SameSite` as defense in depth, not the only control. Verify the cross-origin behavior in a real production browser setup.

### F-05 — Deployment manifest leaves security and persistence settings undefined

**Severity:** MEDIUM  
**Evidence:** [`render.yaml`](../render.yaml) defines a free web service with `gunicorn app:app`, but no `FLASK_ENV`, `SECRET_KEY`, `ALLOWED_ORIGINS`, `DATABASE_URI`, or durable disk configuration. The application defaults to development mode, the known fallback secret, local-only allowed origins (and adds local origins outside production), `SESSION_COOKIE_SECURE=false`, SQLite, and local filesystem storage. A runtime probe in the workspace confirmed development mode and a non-secure cookie default. The Render dashboard may supply overrides, but its settings were unavailable.

**Reproduction:** Deploy the manifest without dashboard overrides and inspect effective environment/configuration, response CORS headers, `Set-Cookie`, database URI, and storage behavior after a service restart. The manifest alone does not establish production-safe configuration.

**Recommended remediation:** Document and provision production secrets and exact origins using the hosting platform's secret/configuration facility; explicitly set production mode and secure cookie settings; use a managed persistent database and durable shared storage. Add startup validation that rejects unsafe production defaults.

### F-06 — PostgreSQL driver and schema migration workflow are missing

**Severity:** MEDIUM  
**Evidence:** [`backend/database.py`](../backend/database.py) accepts non-SQLite SQLAlchemy URIs, but [`backend/requirements.txt`](../backend/requirements.txt) does not include a PostgreSQL DBAPI driver. The source and dependencies contain no Alembic/Flask-Migrate setup; `Base.metadata.create_all()` is used to initialize tables. No PostgreSQL service was available during this audit.

**Reproduction:** Install only the declared backend requirements, set `DATABASE_URI=postgresql://...`, and start the backend. SQLAlchemy's PostgreSQL dialect requires an installed driver; the declared dependencies do not provide one. Also, changing an existing schema is not handled by `create_all()`.

**Recommended remediation:** Add and pin the selected PostgreSQL driver, verify a real PostgreSQL integration test, and introduce a versioned migration workflow before deploying schema changes. The example URI should name the selected driver if using a driver-specific dialect.

### F-07 — Frontend does not handle session expiry after initialization

**Severity:** LOW  
**Evidence:** [`frontend/src/App.jsx`](../frontend/src/App.jsx) checks `/api/auth/me` on mount (lines 216–237) and enables credentials (line 180). Dataset/API request handlers display errors, but no shared 401 interceptor or equivalent transition resets authentication state. The UI can remain in the dashboard after the server rejects an expired cookie.

**Reproduction:** Log in, let the session expire or revoke it from another client, then trigger a protected analytics request. The API returns 401, while the React state still has `isLoggedIn=true`; the request error is displayed without redirecting to login.

**Recommended remediation:** Handle 401 responses centrally (excluding expected unauthenticated bootstrap/login cases), clear protected dashboard state, and return the user to the login form with a clear session-expired message.

### F-08 — No login throttling

**Severity:** LOW  
**Evidence:** [`backend/app.py`](../backend/app.py) validates credentials and hashes passwords but has no rate limiting, escalating delay, or account/IP abuse control on `POST /api/auth/login`. This was a source review; no external load/abuse test was performed.

**Reproduction:** Repeatedly submit invalid credentials to `/api/auth/login`. The route has no application-level request threshold or lockout response.

**Recommended remediation:** Add a deployment-appropriate rate limiter and monitoring with privacy-preserving identifiers. Avoid permanent account lockout that enables denial of service.

## Verification checklist

| # | Audit area | Result and evidence |
|---|---|---|
| 1 | Database persistence after backend restart | **PASS locally.** Uploaded a CSV to a temporary SQLite DB/storage directory, terminated and restarted a separate one-worker Gunicorn process, then successfully queried chart data and downloaded the dataset. This verified a real process restart, not just cache eviction. |
| 2 | Registration, password hashing, login | **PASS in tests.** Registration, duplicate/invalid input, password hash, and valid/invalid login tests pass. Responses set an HTTP-only cookie and do not return the token in JSON. |
| 3 | Server-side session revocation after logout | **PASS in tests.** Logout writes a hash-only revocation record and clears the cookie; a test checks subsequent unauthorized access. |
| 4 | Replay using copied session cookie | **PASS in tests.** Replaying the captured cookie after logout receives 401. Revocation is database-backed, though an actual cross-process replay test was not run. |
| 5 | Expired and invalid sessions | **PASS for token validation.** Tampered-token tests pass; an isolated check verified an expired timed token is rejected. No end-to-end browser expiry test was available. |
| 6 | Cross-user dataset access prevention | **PASS in tests.** Cross-user chart, download, and data-quality access are rejected. Dataset lookup checks owner identity before loading data. |
| 7 | Authentication on dataset APIs | **PASS for analytical routes; EXCEPTION for cleanup.** Upload, chart, insights, ask, download, quality/profile, and BI routes are decorated with `@login_required`; cleanup is not authenticated (F-02). |
| 8 | Temporary file cleanup after failed uploads | **PARTIAL PASS.** Storage write failure has a test proving partial temporary files are removed. Empty-file upload creates no DB row. Filesystem cleanup itself is best-effort, as detailed in F-03. |
| 9 | Dataset deletion and storage consistency | **GAP.** There is no user-scoped dataset deletion API. Expiration cleanup is global and can lose consistency on file/DB errors (F-02, F-03). |
| 10 | Database transaction rollback | **PARTIAL PASS.** Dataset creation explicitly rolls back DB errors and attempts file cleanup; the shared DB context manager rolls back exceptions. No test injected a DB commit failure into dataset creation or cleanup. Cleanup's DB and filesystem operations are not one atomic transaction (F-03). |
| 11 | CSRF and production cookie configuration | **GAP / NOT VERIFIED.** No CSRF token or unsafe-method Origin check was found. Cookie secure behavior depends on environment; no production browser deployment was available (F-04, F-05). |
| 12 | CORS and production environment | **LOCAL DEFAULTS VERIFIED; PRODUCTION NOT VERIFIED.** CORS is credentialed and uses explicit origins, but current defaults are development/local and Render does not declare the production overrides (F-05). |
| 13 | PostgreSQL compatibility and migrations | **NOT VERIFIED / INCOMPLETE.** SQLAlchemy URI branch exists, but no PostgreSQL driver or migration framework is declared (F-06). |
| 14 | Multi-worker and shared-storage behavior | **PARTIAL / NOT VERIFIED.** A one-worker restart test passed. Database/files can be shared if all workers use the same persistent filesystem/database; in-memory caches are process-local. Multi-instance/shared-volume behavior and the configured Render free service's persistence were not tested. |
| 15 | Frontend authentication and session expiry | **PARTIAL.** Login/session bootstrap uses backend cookie auth and all 8 frontend tests pass. Handling of a later 401 does not transition back to login (F-07). |

## Test results

Existing suites, run during the read-only audit before adding new security tests:

- Backend: `python -m pytest tests/ -q` — **215 passed**.
- Frontend: `npm test -- --reporter=dot` — **8 passed**.
- Actual process-restart check — **passed** with isolated Gunicorn, SQLite, and storage in a temporary directory.
- Isolated configuration/route probes — confirmed known fallback secret, `development` mode, `SESSION_COOKIE_SECURE=false`, timed-token expiry rejection, and unauthenticated cleanup returning 200.

After recording the findings above, security-specific tests were added in [`backend/tests/test_phase3_security_audit.py`](../backend/tests/test_phase3_security_audit.py):

- Backend suite including audit tests: **229 passed, 2 expected failures**. The expected failures correspond to F-02 and F-03 and intentionally remain as failing security expectations.
- New audit tests alone: **14 passed, 2 expected failures**.
- Frontend suite re-run: **8 passed**.

The xfails are strict so that they will cause a failure if the audited behavior changes and the xfail markers are not updated.

## Deployment conclusion

The local test suite supports local-development persistence, authentication, and ownership claims. It does not establish safe production deployment. Resolve F-01 through F-06 and verify the actual host's effective settings, PostgreSQL, migrations, durable storage, CSRF behavior, and multi-worker behavior before making a production-readiness claim.

## Remediation follow-up

The eight findings were subsequently addressed. Final automated and integration evidence is documented in [`PHASE3_SECURITY_REMEDIATION.md`](./PHASE3_SECURITY_REMEDIATION.md).

| ID | Severity | Final status | Verification | Remaining limitation |
|---|---|---|---|---|
| F-01 | HIGH | Fixed | Missing, weak, valid secret and production startup tests pass | No production host was deployed; rotate any key previously used in a real environment |
| F-02 | MEDIUM | Fixed | Unauthenticated, normal-user, invalid-token, and authorized cleanup tests pass | Shared scheduler token must be secured operationally |
| F-03 | MEDIUM | Fixed with retryable staged workflow | Permission failure, partial deletion, missing files, failed commit, and retry tests pass | Persistent storage failures require operator intervention |
| F-04 | MEDIUM | Fixed | CSRF token and origin regression tests pass; PostgreSQL integration exercised cookie-authenticated writes | Production browser and deployed cookie/origin behavior are not verified |
| F-05 | MEDIUM | Configuration updated | Startup validation and Render manifest assertions pass | Render was not deployed; external origins, database, cost, and volume behavior remain unverified |
| F-06 | MEDIUM | Implemented and locally integration-tested | SQLite migration tests and a disposable real PostgreSQL integration pass | Managed production database and a real deployed legacy upgrade were not tested |
| F-07 | LOW | Fixed | Frontend protected-request 401 test passes | Deployed browser behavior remains unverified |
| F-08 | LOW | Fixed | Repeated-failure, 429, recovery, and PostgreSQL upsert checks pass | Reverse-proxy client IP behavior is deployment-specific |

**Post-remediation verification:** Backend **243 passed**; frontend **9 passed**; Vite production build succeeded with a 608.14 kB minified-chunk advisory. A real one-worker Gunicorn restart preserved the authenticated session and dataset. Logout invalidated a copied cookie. SQLite and local PostgreSQL Alembic upgrades passed. No production deployment was verified; production readiness remains **not established**.
