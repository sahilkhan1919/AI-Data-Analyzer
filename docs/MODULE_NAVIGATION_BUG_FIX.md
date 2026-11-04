# Module Navigation Bug Fix

## Root cause

Sidebar items had distinct keys, `handleTabChange` updated `activeTab`, and the page modules already had separate render conditions. However, the Overview KPI summary block was conditioned only on `summary` being present. Since the selected dataset summary remains in app state while navigating, the Overview cards rendered above every module.

The other KPI groups are already module-scoped: quality summary cards are inside the quality branch, BI KPIs inside the BI branch, and group-analysis metrics inside its BI section. No lazy-loaded module falls back to Overview.

## Fix

- Restricted the shared Overview KPI summary block to `activeTab === "charts"`.
- Added a stable `overview-kpis` test marker for explicitly checking module isolation.
- Added a frontend navigation test that uploads a dataset and visits all 11 sidebar destinations. It checks active navigation state, module-specific content, KPI isolation, and dataset state persistence.
- Added valid trend and period-comparison API fixtures to the navigation test so the Trends module is rendered using the expected response shape.

## Files changed

- `frontend/src/App.jsx`
- `frontend/src/__tests__/App.test.jsx`

No backend, package manifest, authentication, dataset, API, or analytics calculation code was changed.

## Verification

- `cd frontend && npm test`: **Passed** — 13 tests.
- `cd frontend && npm run build`: **Passed** — Vite production build completed.
- Navigation test: visits Overview & Charts, Data Quality & Profile, Business Intelligence, Trends & Comparisons, AI Analyst, Root Cause Analysis, Predictive Analytics, Business Reports, Upload Dataset, Dataset Management, and Settings. Confirms each active state and its page-specific heading/content; Overview KPI cards are present only on Overview; selected dataset remains available in Settings and after returning to Overview.
- Browser smoke check: the frontend loads and displays the login page. The browser has no authenticated session; the backend returns 401 for session lookup as expected. Authenticated interactions were checked using the frontend test suite’s mocked API responses.

## Remaining notes

- The build emits the existing Vite CJS API deprecation notice and bundle-size advisory; neither prevents a successful build.
- Git history is not available in this workspace, so the fix was based on direct source tracing.
