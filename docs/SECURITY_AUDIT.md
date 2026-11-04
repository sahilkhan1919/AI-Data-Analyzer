# Security Audit

**Audit date:** 2026-11-04  
**Scope:** Local source/configuration review plus automated security,
authentication, ownership, and browser-session verification. This is not a
penetration test or a production certification.

## Security controls observed

| Control | Evidence and result |
|---|---|
| Signing key | `backend/config.py` requires a stable, high-entropy environment-provided `SECRET_KEY` in development and production. No fallback key remains. Missing/weak key tests pass. |
| Local secret handling | A persistent local key is in ignored `backend/.env`, mode `0600`; its value was not printed. New deployments must provision their own key and must not reuse the local value. |
| Cookie | `csv_session` is HTTP-only, host-only, path `/`, seven-day maximum age; `Secure` is enabled in production. SameSite behavior is environment-configured (`Lax` locally; Render example uses `None` with Secure). |
| Authentication | Signed timed tokens identify a user; protected routes use `@login_required`. Browser login, immediate profile request, refresh, logout, and invalid-session behavior passed. |
| Logout revocation | Revocation stores a hash and rejects replay. Backend regression test and browser post-logout check pass. |
| CSRF/CORS | Unsafe cookie requests require a session-bound signed CSRF token and trusted origin/referer. Credentialed CORS uses configured origins; local preflight returned exact origin and credentials headers. |
| Passwords and throttling | Passwords use Werkzeug scrypt hashing. Database-backed login throttling has regression coverage. |
| Tenant authorization | Dataset/report lookup and download checks ownership. Backend tests cover cross-user dataset and report denial. |
| Cleanup operations | Global cleanup requires a configured scheduler/admin bearer secret; ordinary and unauthenticated callers are denied. |
| Error/input handling | This audit fixed malformed registration/login JSON and field types that previously could produce 500 responses; invalid types now return structured 400s. |

## Findings and disposition

| ID | Severity | Finding | Status |
|---|---|---|---|
| SEC-01 | HIGH (historical) | A known development signing-key fallback was unsafe and could cause immediate cross-host/session problems. | Removed in prior remediation; current configuration rejects missing or weak secrets. Local stable key provisioned. Old sessions are invalidated. |
| SEC-02 | MEDIUM | Malformed JSON objects and non-string email/password fields caused uncaught errors. | Fixed and covered by registration/login regressions. |
| SEC-03 | LOW | Password policy permits a six-character minimum and has no documented breached-password check. | Not changed in this audit to avoid an unrequested auth-policy compatibility change; consider a stronger minimum and documented policy before public launch. |
| SEC-04 | LOW / operational | Backend dependency versions are mostly unpinned and no dependency vulnerability scan ran. | No manifest changes made. Pin/review dependencies and run an approved advisory scanner before release. |
| SEC-05 | NOT TESTED | Production TLS, proxy-derived client addresses, cross-site cookies, managed database, and storage durability were unavailable. | Must be verified in staging/production-like environment before launch. |

No new critical or high-severity exploitable issue was confirmed in the reviewed
paths. This does not imply that every vulnerability class or dependency was
exhaustively assessed.

## Security verification evidence

- Backend auth/security suite is included in the 268 passing tests; the optional
  PostgreSQL integration was skipped in the final run.
- Browser checked credentialed session creation, authenticated profile after
  login, refresh persistence, logout, and rejection of the old session.
- Browser API invalid credentials did not authenticate.
- Credentialed local CORS preflight returned HTTP 200 with the exact requesting
  origin and credentials enabled.
- Production configuration is specified in `render.yaml`, but no service was
  deployed or tested.

## Operator requirements

Generate and persist a unique secret in the deployment’s secret manager; do not
copy the local `.env` or rotate the key on each restart. Set the exact deployed
frontend origin, PostgreSQL URI, HTTPS secure-cookie policy, and a durable
storage mount. Protect the cleanup token and LLM API key if configured. Back up
the database and file storage and exercise recovery before accepting user data.
