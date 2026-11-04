# Phase 2 — Business Intelligence Engine Documentation

**Module:** `backend/analytics/business_intelligence.py`  
**API Endpoints:** `POST /api/bi/kpis`, `POST /api/bi/group-analysis`, `POST /api/bi/trends`, `POST /api/bi/period-comparison`  
**Status:** Implemented & Verified (17 dedicated unit tests, 16 API integration tests)

---

## 1. Overview and Design Principles

The Business Intelligence (BI) Engine dynamically computes business KPIs, categorical segment rankings, and chronological time trends directly from uploaded datasets.

Key architectural principles:
- **Dynamic & Keyword-Agnostic:** Does not require hardcoded column names (e.g., `Sales` or `Profit`). Discovers candidate measures dynamically and supports user-selected dimensions and metrics.
- **Non-Additive Identifier Protection:** Identifies and excludes IDs, postal codes, and phone numbers from additive summation operations.
- **Zero-Division & Edge-Case Protection:** Zero denominators (e.g. zero revenue in profit margin or zero previous period value in period-over-period change) return safe structured values rather than crashing.
- **Evidence-Based Insights:** All generated observations are deterministic and mathematically grounded in dataset calculations. No external LLMs or unverified causal assertions are used.

---

## 2. Capabilities

### A. Business Measure Discovery
`discover_business_kpis(df)` classifies numeric columns:
- Analyzes column naming patterns against additive exclusions (`id`, `uuid`, `zip`, `code`, `phone`, `ssn`).
- Checks if all integer values are 100% unique (surrogate key detection).
- Infers candidate business roles using keywords:
  - **Revenue / Sales:** `revenue`, `sales`, `turnover`, `amount`, `income`
  - **Profit / Margin:** `profit`, `margin`, `gain`, `net`
  - **Quantity / Volume:** `quantity`, `qty`, `units`, `volume`
  - **Orders Identifier:** `order_id`, `transaction_id`, `invoice_id`
  - **Cost:** `cost`, `expense`, `cogs`
  - **Discount:** `discount`, `rebate`

### B. Dynamic Business KPI Calculations
When suitable columns exist, `calculate_business_kpis()` calculates:
1. **Total Revenue / Sales:** Sum of valid observations in the revenue measure.
2. **Total Profit:** Sum of profit observations. Negative totals are clearly documented as net losses.
3. **Profit Margin (%):**
   $$\text{Profit Margin (\%)} = \frac{\text{Total Profit}}{\text{Total Revenue}} \times 100$$
   *Calculated only when Total Revenue is non-zero.*
4. **Total Quantity / Volume:** Sum of quantity observations.
5. **Distinct Orders Count:** `df[order_id_col].nunique()` — Counts unique transactions rather than raw rows.
6. **Average Order Value (AOV):**
   $$\text{AOV} = \frac{\text{Total Revenue}}{\text{Distinct Orders}}$$
   *Correctly handles datasets where multiple line items share the same order ID.*
7. **Average Discount (%):** Mean discount across all recorded lines.
8. **Generic Numeric Aggregates:** If a dataset is non-commercial (e.g. academic grades, meteorological measurements), the engine provides generic additive sums and averages without fabricating retail KPIs.

### C. Group-Wise Comparison & Ranking
`calculate_group_analysis(df, group_col, measure_col, aggregation, limit)`:
- Aggregations supported: `sum`, `mean`, `median`, `count`, `min`, `max`.
- Null handling: Missing group labels are displayed as `"(Missing / None)"` rather than discarded.
- Contribution %: Computes each group's percentage of the total measure volume.
- Performance Ranking: Identifies highest-performing group, lowest-performing group, and flags groups with negative values.
- Contextual caveat: Notes that highest value is not always optimal (e.g. lower expenses or failure counts are preferable).

### D. Date-Based Trend Analysis
`calculate_date_trends(df, date_col, measure_col, aggregation, granularity)`:
- Granularities supported: `daily`, `weekly`, `monthly`, `quarterly`, `yearly`.
- Reliable parsing: Parses dates via `pd.to_datetime(errors='coerce')` and separates valid periods from unparseable records.
- Chronological Sorting: Orders aggregated periods chronologically by date period.
- Output: Returns period labels, values, total periods count, start date, and end date for chart visualization.

### E. Period-over-Period (PoP) Comparison
`calculate_period_over_period()` compares the latest period against the immediately preceding period:
$$\text{Absolute Change} = \text{Current Value} - \text{Previous Value}$$
$$\text{Percentage Change} = \left(\frac{\text{Absolute Change}}{|\text{Previous Value}|}\right) \times 100$$

- Directional classification: `increase`, `decrease`, or `neutral`.
- Zero denominator protection: If previous period value is 0.0, percentage change is returned as `None` with an explanatory note rather than producing infinity.
- Insufficient data handling: If fewer than 2 periods exist, returns `is_valid_comparison: False` with clear messaging.

### F. Deterministic Insights
`generate_deterministic_insights()` produces structured, categorized observations:
- **Categories:** `Performance`, `Trend`, `Anomaly`, `Data Quality`.
- **Fields:** `title`, `category`, `explanation`, `supporting_metric`, `severity` (`positive`, `info`, `warning`), and `recommended_action`.
- No LLM hallucination: Does not fabricate explanations (e.g., will not claim sales dropped due to marketing or weather unless the dataset explicitly contains those variables).
