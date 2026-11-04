# Login Session Bug Fix

## Root cause

The browser was opened at `http://127.0.0.1:5173`, while
`frontend/.env` explicitly sent API requests to `http://localhost:5001`.
The backend issues a host-only `csv_session` cookie with `SameSite=Lax`.
Although both frontend origins were allowed by CORS, cookies for `localhost`
are not sent to `127.0.0.1`. The first protected request therefore appeared
unauthenticated and the frontend returned to the login screen.

The development configuration also supplied a hardcoded signing-key fallback.
That fallback was removed because it made authentication dependent on an
insecure, code-provided key rather than a stable environment secret.

## Changes made

- Updated `frontend/.env` to leave `VITE_API_URL` unset locally. The existing
  frontend URL fallback now uses the page hostname, so the API and host-only
  session cookie use the same host.
- Updated `backend/config.py` to require a strong, environment-provided
  `SECRET_KEY` for development and production, without exposing its value.
- Updated `backend/.env.example` with instructions to generate and persist a
  stable key.
- Added backend tests for missing/weak development keys and for the complete
  login-cookie → authenticated `/api/auth/me` → logout → rejected-cookie-replay
  flow.
- Added a frontend regression test for successful login followed by app
  remount/session restoration, including the credentialed Axios setting.
- Provisioned a persistent local development signing key in the ignored
  `backend/.env` file and restricted its permissions. The key is not included
  in this report or source control.

No backend routes, database schemas, analytics calculations, or authentication
protections were removed.

## Verification

| Check | Result |
|---|---|
| Backend test suite | 260 passed, 1 skipped |
| Frontend test suite | 14 passed |
| Production frontend build | Passed |
| Backend root health endpoint | HTTP 200 |
| Credentialed CORS preflight from `127.0.0.1:5173` | HTTP 200; exact origin and credentials headers returned |
| Browser registration and login | Passed with a temporary test account |
| Immediate authenticated `/api/auth/me` request | HTTP 200 |
| Browser refresh and session restoration | Passed |
| Browser logout and subsequent `/api/auth/me` | Login screen restored; HTTP 401 |
| Invalid credentials | Rejected with “Invalid email or password.” |
| Temporary browser test account | Removed |

The production build reports a pre-existing-size warning for the main JavaScript
bundle (about 639 kB before gzip); the build completes successfully.

## Session key rotation

Sessions signed with the previous hardcoded development key are no longer
valid. Users with such a local session must sign in again. The newly provisioned
local key is stable across backend restarts; it must be backed up securely and
must not be committed.

## Remaining limitations

Browser verification used a temporary account and local HTTP development
origins. Production HTTPS, deployed-origin CORS, and deployment-specific
secret provisioning were not exercised in this environment.
