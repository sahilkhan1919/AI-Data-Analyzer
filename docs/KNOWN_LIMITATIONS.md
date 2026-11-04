# Known Limitations

## Deployment and operations

- No live production deployment, managed PostgreSQL instance, production
  browser, or host-provided durable storage was available. Production readiness
  remains unverified.
- The final PostgreSQL integration test was skipped because no explicit
  disposable `TEST_POSTGRES_DATABASE_URI` was configured.
- The example Render configuration has a persistent disk for one service.
  Horizontal scaling requires a shared durable storage strategy; local file
  paths are not shared across independent instances.
- `/` is a liveness-style endpoint, not a database/storage readiness check.
- Dependency security scanning and automated lint/type-check commands are not
  configured in the inspected manifests.

## Analytics and AI scope

- The data-quality score is heuristic and does not guarantee semantic or
  business validity.
- The AI Analyst supports a limited set of deterministic calculations and
  explicitly rejects unsupported questions. Its optional LLM explanation path
  was not tested against a live provider.
- Root-cause analysis is descriptive contribution analysis; it does not
  establish causality.
- Predictive analytics is a last-observation baseline with chronological
  holdout metrics and approximate uncertainty bounds, not a trained seasonal
  model.
- Tests cover core CSV/XLSX paths, but a valid near-limit upload, protected or
  corrupted XLSX, and production-scale load were not verified.

## Performance and presentation

- The production build’s primary JavaScript chunk is 638.85 kB minified
  (193.12 kB gzip) and exceeds Vite’s 500 kB advisory threshold. Consider
  route-level lazy loading and chart/report code splitting.
- No large-dataset latency, memory, concurrency, or browser performance
  benchmark was run.
- Backend production requirements are not fully lockfile-pinned.

## Workspace constraints

- The project directory has no Git metadata, so change history, a clean/dirty
  worktree check, and a backup commit were unavailable.
- Existing ignored uploads and local user files were not deleted or modified by
  this audit. The temporary account and dataset created for live testing were
  removed.
