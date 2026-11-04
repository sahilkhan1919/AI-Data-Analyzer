# Phase 2 — Data Quality Engine Documentation

**Module:** `backend/analytics/data_quality.py`  
**API Endpoints:** `GET /api/data-quality`, `POST /api/data-quality`, `GET /api/data-profile`, `POST /api/data-profile`  
**Status:** Implemented & Verified (21 dedicated unit tests, 16 API integration tests)

---

## 1. Overview and Design Principles

The Data Quality Engine provides tabular profiling, anomaly identification, and actionable cleaning recommendations based on the actual uploaded dataset. 

Key architectural principles:
- **Non-Destructive:** Analysis never mutates the underlying uploaded dataset. Recommendations provide actionable guidance for analysts rather than applying irreversible transformations.
- **Framework Independence:** The core analytical logic in `analytics/data_quality.py` is independent of Flask HTTP routes, allowing direct reuse in worker jobs, CLI scripts, and automated test runners.
- **Strict JSON Safety:** All outputs are sanitized via `sanitize_for_json()` to convert NaN, infinity, numpy scalars, and datetime timestamps into standard JSON-serializable types.

---

## 2. Capabilities

### A. Dataset Overview
Extracts high-level dataset structural metrics:
- Total rows and total columns.
- Count of numeric, categorical, and detected date columns.
- Total missing cells and overall dataset missing-cell percentage.
- Duplicate rows count and percentage.
- Count of completely empty rows and completely empty columns.

### B. Column-Level Profiling
For every column, the engine calculates:
- Detected semantic data type (`numeric`, `categorical`, `datetime`, `boolean`).
- Non-null count, missing count, and missing percentage.
- Unique value count and duplicate-value frequency.
- Constant column detection (`is_constant = True` if unique count == 1).
- High cardinality detection (`is_high_cardinality = True` if unique / non-null > 0.7 or unique > 50).
- Safe, non-exposing example values (up to 5 distinct values).

For **numeric** columns:
- Minimum, maximum, mean, median, standard deviation, first quartile (Q1, 25%), and third quartile (Q3, 75%).

For **categorical** columns:
- Number of unique categories.
- Most frequent category value and its occurrence count.
- Frequency distribution for top 5 categories with percentages.

### C. Missing-Value Analysis & Recommendations
Detects missing entries across every column and generates evidence-based recommendations:
- **> 60% Missing:** `Investigate / Consider Column Removal` — If non-essential for reporting, dropping reduces noise.
- **Numeric & ≤ 5% Missing:** `Median or Mean Imputation` — Low missingness. Median imputation is robust against distribution skew; mean imputation is appropriate for normal distributions.
- **Numeric & 5% - 60% Missing:** `Evaluate Domain Significance & Imputation` — Moderate missingness. Audits whether absence is systematically informative before model-based imputation.
- **Categorical Missing:** `Explicit 'Unknown' Category or Mode Imputation` — Retains total record count without biasing category ratios.
- **0% Missing:** `No Action Required` — Complete data.

### D. Duplicate Detection
- Calculates exact row-level duplicates using `df.duplicated(keep=False)`.
- Reports total duplicate rows, duplicate percentage, and count of unique records.
- Provides a controlled preview of duplicate rows (up to 5 records).
- Technical impact note: explains how duplicates may artificially inflate revenue or transaction counts while noting that identical records may be legitimate repeat transactions depending on domain context.

### E. Potential Outlier Detection (IQR Method)
Evaluates numeric columns using the Interquartile Range (IQR) method:
$$\text{IQR} = Q_3 - Q_1$$
$$\text{Lower Bound} = Q_1 - 1.5 \times \text{IQR}$$
$$\text{Upper Bound} = Q_3 + 1.5 \times \text{IQR}$$

- Flags values strictly below the lower bound or above the upper bound as potential outliers.
- Edge case handling:
  - Columns with $< 4$ observations return status `insufficient_data` without error.
  - Columns with constant values or $\text{IQR} = 0$ return status `constant_or_zero_iqr` with 0 outliers flagged.
- Business disclaimer: outliers represent extreme statistical variance and may reflect genuine high-value transactions (e.g., enterprise B2B sales or Black Friday spikes) rather than errors.

---

## 3. Data Quality Scoring Formula

The Data Quality Score is a transparent, explainable metric scaled between **0.0 and 100.0**:

$$\text{Score} = 100.0 - (\text{Penalty}_{\text{missing}} + \text{Penalty}_{\text{duplicate}} + \text{Penalty}_{\text{outliers}})$$

### Penalty Allocations
1. **Missing Cells Penalty (Weight: 40 points maximum):**
   $$\text{Penalty}_{\text{missing}} = \min\left(40.0, \frac{\text{Missing Cells}}{\text{Total Cells}} \times 100 \times 0.8\right)$$

2. **Duplicate Rows Penalty (Weight: 30 points maximum):**
   $$\text{Penalty}_{\text{duplicate}} = \min\left(30.0, \frac{\text{Duplicate Rows}}{\text{Total Rows}} \times 100 \times 0.6\right)$$

3. **IQR Outlier Penalty (Weight: 30 points maximum):**
   $$\text{Penalty}_{\text{outliers}} = \min\left(30.0, \frac{\text{Total Outliers Flagged}}{\text{Total Numeric Observations}} \times 100 \times 0.6\right)$$

### Grading Thresholds
- **90.0 – 100.0:** `Excellent`
- **75.0 – 89.9:** `Good`
- **50.0 – 74.9:** `Fair`
- **< 50.0:** `Needs Attention`
- **Empty Dataset:** `0.0 (Empty)`

### Explicit Score Limitations
The Data Quality Score evaluates heuristic penalties based on missingness, exact duplication, and statistical dispersion. A score of 100 indicates that none of the heuristic penalties were triggered; it does not certify semantic correctness, business truth, or absence of fraudulent data.

---

## 4. Date Column Detection Heuristics

`detect_date_columns(df)` uses a multi-stage detection pipeline:
1. Native `datetime64` dtypes (e.g. from Excel imports) are recognized immediately.
2. For string or object columns, non-null samples (up to 50 items) are analyzed.
3. Pure small integer values (e.g. "1", "2") are excluded to prevent confusing IDs or sequence numbers with dates.
4. Samples are parsed with `pd.to_datetime(errors='coerce')`. If $\ge 80\%$ of sample strings parse successfully into valid dates, the column is classified as a date column.
