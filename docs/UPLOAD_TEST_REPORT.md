# Upload and Dataset Test Report

**Audit date:** 2026-11-04

## Supported formats

The backend allowlist accepts `.csv` and `.xlsx`. `.xls` is not supported by
the current implementation. The configured default maximum request body is
10 MiB.

## Reproducible audit fixture

`backend/tests/fixtures/audit_workflow.csv` is synthetic, deterministic test
data containing 13 rows, six columns, 12 calendar months, `Region` and
`Category` dimensions, numeric `Revenue`, `Profit`, and `Orders`, one repeated
row, and one missing `Revenue`.

| Expected/observed value | Result |
|---|---:|
| Rows in source | 13 |
| Rows after cleaning | 12 |
| Columns | 6 |
| Duplicate rows removed | 1 |
| Missing cells handled | 1 |
| Cleaned Revenue sum (mean-imputed) | 20,181.8182 |

The values were confirmed independently with Pandas and in a live browser
upload. The AI Analyst returned the same revenue sum.

## Automated upload coverage

`backend/tests/test_upload.py`, `test_data_processing.py`, and related suites
cover:

- Valid CSV and valid XLSX uploads.
- Missing file, empty file, headers-only input, unsupported extension, and
  oversized upload.
- Duplicate rows, missing-value handling, Unicode/unusual text, parser errors,
  and structured error responses.
- A new CSV with headers `Date, Date ,Revenue`, verifying normalization to
  unique names and successful trend calculation.
- A new direct-cleaning regression verifying trend calculations remain usable
  after whitespace collisions are disambiguated.

The full backend run passed 268 tests with one optional PostgreSQL test skipped.

## Live browser workflow

With a temporary test account, the audit uploaded the fixture through the UI,
observed the cleaned 12-row/6-column summary, generated a Chart.js visualization,
visited analytics modules, generated a PDF, and downloaded it. The dataset was
deleted through the UI after the test; the temporary account was removed.

## Limitations and untested cases

- A valid CSV just below the configured size limit was not uploaded; only the
  over-limit rejection is covered by the existing suite.
- Browser-level XLSX upload was not performed, although the backend XLSX upload
  tests pass.
- Password-protected XLSX and corrupted XLSX cases were not explicitly tested.
- CSV parser behavior can accept some malformed-but-readable inputs; binary
  malformed input is tested to ensure it does not crash the server.
- No production-scale throughput, memory, or concurrent upload benchmark was
  run. The server parses files into Pandas dataframes in memory within the
  configured request-size limit.

## Data safety

The test dataset contains no real business or personal data. Existing files in
`backend/uploads/` were left untouched. Production deployment requires a
durable volume or shared object storage; an ephemeral container filesystem is
not an adequate persistence strategy.
