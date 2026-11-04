"""
business_intelligence.py – Reusable Business Intelligence (BI) Engine.

Calculates dynamic KPIs, group-wise aggregations, ranking comparisons,
date-based trend analysis, and period-over-period performance metrics based on
actual uploaded tabular datasets.
"""

import math
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analytics.data_quality import detect_date_columns, sanitize_for_json


# Common non-additive column identifiers to exclude from automatic summing
NON_ADDITIVE_PATTERNS = [
    "id", "uuid", "guid", "code", "zip", "postal", "phone", "ssn", "pin",
    "year", "month", "day", "index", "key", "number", "no"
]


def _is_additive_numeric(col_name: str, series: pd.Series) -> bool:
    """
    Check if a numeric column is likely an additive business measure
    rather than an identifier, postal code, or sequence key.
    """
    clean_name = str(col_name).lower().strip().replace("_", "").replace(" ", "")
    for pattern in NON_ADDITIVE_PATTERNS:
        if clean_name.endswith(pattern) or clean_name == pattern:
            return False

    # If all values are unique integers, it is almost certainly a surrogate key or row ID
    non_null = series.dropna()
    if len(non_null) > 10 and non_null.nunique() == len(non_null):
        if pd.api.types.is_integer_dtype(series) or (non_null % 1 == 0).all():
            return False

    return True


def discover_business_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Inspect the dataset and identify candidate numeric measures, non-additive columns,
    and inferred business roles (revenue, profit, cost, quantity, orders, discounts).
    """
    if df.empty or df.shape[1] == 0:
        return sanitize_for_json({
            "candidate_measures": [],
            "inferred_mappings": {},
            "summary": "Dataset is empty.",
        })

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    date_cols = detect_date_columns(df)

    candidates = []
    inferred_mappings: Dict[str, Optional[str]] = {
        "revenue_col": None,
        "profit_col": None,
        "quantity_col": None,
        "order_id_col": None,
        "cost_col": None,
        "discount_col": None,
    }

    for col in numeric_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue

        is_additive = _is_additive_numeric(col, series)
        col_lower = str(col).lower()

        # Inferred role matching
        if not inferred_mappings["revenue_col"] and any(k in col_lower for k in ["revenue", "sales", "turnover", "total_amount", "amount"]):
            inferred_mappings["revenue_col"] = str(col)
        elif not inferred_mappings["profit_col"] and any(k in col_lower for k in ["profit", "margin", "net_gain", "gain"]):
            inferred_mappings["profit_col"] = str(col)
        elif not inferred_mappings["quantity_col"] and any(k in col_lower for k in ["quantity", "qty", "units", "volume"]):
            inferred_mappings["quantity_col"] = str(col)
        elif not inferred_mappings["cost_col"] and any(k in col_lower for k in ["cost", "expense", "cogs"]):
            inferred_mappings["cost_col"] = str(col)
        elif not inferred_mappings["discount_col"] and any(k in col_lower for k in ["discount", "rebate"]):
            inferred_mappings["discount_col"] = str(col)

        candidates.append({
            "column": str(col),
            "is_additive": is_additive,
            "count": int(series.count()),
            "sum": float(series.sum()) if is_additive else None,
            "mean": float(series.mean()),
            "median": float(series.median()),
            "min": float(series.min()),
            "max": float(series.max()),
        })

    # Look for order_id among all columns
    for col in df.columns:
        col_lower = str(col).lower()
        if any(k in col_lower for k in ["order_id", "orderid", "transaction_id", "invoice_id", "receipt_id"]):
            inferred_mappings["order_id_col"] = str(col)
            break

    return sanitize_for_json({
        "candidate_measures": candidates,
        "inferred_mappings": inferred_mappings,
        "date_columns": [str(c) for c in date_cols],
        "total_numeric_columns": len(numeric_cols),
    })


def calculate_business_kpis(
    df: pd.DataFrame,
    revenue_col: Optional[str] = None,
    profit_col: Optional[str] = None,
    quantity_col: Optional[str] = None,
    order_id_col: Optional[str] = None,
    discount_col: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Calculate dynamic business KPIs based on explicit or automatically discovered columns.
    Never fabricates metrics. Handles missing measures and zero denominators safely.
    """
    kpis = []
    if df.empty:
        return []

    # If specific columns were not supplied, use discovery to infer candidate mappings
    if not (revenue_col or profit_col or quantity_col or order_id_col or discount_col):
        discovery = discover_business_kpis(df)
        mappings = discovery.get("inferred_mappings", {})
        revenue_col = mappings.get("revenue_col")
        profit_col = mappings.get("profit_col")
        quantity_col = mappings.get("quantity_col")
        order_id_col = mappings.get("order_id_col")
        discount_col = mappings.get("discount_col")

    # 1. Total Revenue / Sales
    if revenue_col and revenue_col in df.columns and pd.api.types.is_numeric_dtype(df[revenue_col]):
        rev_series = pd.to_numeric(df[revenue_col], errors="coerce").dropna()
        total_rev = float(rev_series.sum())
        kpis.append({
            "metric_name": f"Total {revenue_col}",
            "metric_value": total_rev,
            "formatted_value": f"${total_rev:,.2f}" if total_rev >= 0 else f"-${abs(total_rev):,.2f}",
            "units": "currency",
            "calculation_explanation": f"Sum of all valid observations in column '{revenue_col}'.",
            "columns_used": [revenue_col],
            "assumptions": "Assumes values represent monetary revenue.",
        })
    else:
        total_rev = None

    # 2. Total Profit
    if profit_col and profit_col in df.columns and pd.api.types.is_numeric_dtype(df[profit_col]):
        prof_series = pd.to_numeric(df[profit_col], errors="coerce").dropna()
        total_prof = float(prof_series.sum())
        kpis.append({
            "metric_name": f"Total {profit_col}",
            "metric_value": total_prof,
            "formatted_value": f"${total_prof:,.2f}" if total_prof >= 0 else f"-${abs(total_prof):,.2f}",
            "units": "currency",
            "calculation_explanation": f"Sum of all valid observations in column '{profit_col}'.",
            "columns_used": [profit_col],
            "assumptions": "Positive values indicate net profit; negative values represent a net loss.",
        })
    else:
        total_prof = None

    # 3. Profit Margin (%)
    if total_rev is not None and total_prof is not None:
        if total_rev != 0.0:
            margin = (total_prof / total_rev) * 100.0
            kpis.append({
                "metric_name": "Profit Margin",
                "metric_value": round(margin, 2),
                "formatted_value": f"{margin:.2f}%",
                "units": "percentage",
                "calculation_explanation": f"(Total {profit_col} / Total {revenue_col}) * 100",
                "columns_used": [profit_col, revenue_col],
                "assumptions": "Calculated only when Total Sales is non-zero.",
            })
        else:
            kpis.append({
                "metric_name": "Profit Margin",
                "metric_value": None,
                "formatted_value": "N/A",
                "units": "percentage",
                "calculation_explanation": "Total sales is zero; profit margin is undefined.",
                "columns_used": [profit_col, revenue_col],
                "assumptions": "Zero denominator prevents division.",
            })

    # 4. Total Quantity
    if quantity_col and quantity_col in df.columns and pd.api.types.is_numeric_dtype(df[quantity_col]):
        qty_series = pd.to_numeric(df[quantity_col], errors="coerce").dropna()
        total_qty = float(qty_series.sum())
        kpis.append({
            "metric_name": f"Total {quantity_col}",
            "metric_value": total_qty,
            "formatted_value": f"{total_qty:,.0f}",
            "units": "units",
            "calculation_explanation": f"Sum of quantity/units in column '{quantity_col}'.",
            "columns_used": [quantity_col],
            "assumptions": "Assumes additive volume measure.",
        })

    # 5. Orders Count & Average Order Value (AOV)
    if order_id_col and order_id_col in df.columns:
        distinct_orders = int(df[order_id_col].dropna().nunique())
        kpis.append({
            "metric_name": f"Distinct Orders ({order_id_col})",
            "metric_value": distinct_orders,
            "formatted_value": f"{distinct_orders:,}",
            "units": "count",
            "calculation_explanation": f"Count of distinct order identifiers in '{order_id_col}'.",
            "columns_used": [order_id_col],
            "assumptions": "Multiple line items sharing the same ID are counted as one order.",
        })

        if total_rev is not None and distinct_orders > 0:
            aov = total_rev / distinct_orders
            kpis.append({
                "metric_name": "Average Order Value (AOV)",
                "metric_value": round(aov, 2),
                "formatted_value": f"${aov:,.2f}",
                "units": "currency",
                "calculation_explanation": f"Total {revenue_col} / Distinct Orders ({order_id_col})",
                "columns_used": [revenue_col, order_id_col],
                "assumptions": "Correctly aggregates multiple line items per order.",
            })

    # 6. Average Discount
    if discount_col and discount_col in df.columns and pd.api.types.is_numeric_dtype(df[discount_col]):
        disc_series = pd.to_numeric(df[discount_col], errors="coerce").dropna()
        avg_disc = float(disc_series.mean())
        kpis.append({
            "metric_name": f"Average {discount_col}",
            "metric_value": round(avg_disc, 2),
            "formatted_value": f"{avg_disc:.2f}%" if avg_disc <= 100 else f"{avg_disc:.2f}",
            "units": "percentage" if avg_disc <= 100 else "numeric",
            "calculation_explanation": f"Mean value of '{discount_col}'.",
            "columns_used": [discount_col],
            "assumptions": "Averages discount across all recorded lines.",
        })

    # If no specific business metrics matched, provide generic summary KPIs for available additive numeric columns
    if not kpis:
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        additive_cols = [c for c in numeric_cols if _is_additive_numeric(c, df[c])]
        cols_to_summarize = additive_cols[:3] if additive_cols else numeric_cols[:3]

        for col in cols_to_summarize:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue
            kpis.append({
                "metric_name": f"Total {col}",
                "metric_value": float(series.sum()),
                "formatted_value": f"{series.sum():,.2f}",
                "units": "numeric",
                "calculation_explanation": f"Sum of column '{col}'.",
                "columns_used": [str(col)],
                "assumptions": "Generic additive numeric aggregate.",
            })
            kpis.append({
                "metric_name": f"Average {col}",
                "metric_value": float(series.mean()),
                "formatted_value": f"{series.mean():,.2f}",
                "units": "numeric",
                "calculation_explanation": f"Arithmetic mean of column '{col}'.",
                "columns_used": [str(col)],
                "assumptions": "Generic central tendency measure.",
            })

    return sanitize_for_json(kpis)


def calculate_group_analysis(
    df: pd.DataFrame,
    group_col: str,
    measure_col: str,
    aggregation: str = "sum",
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Aggregate a numeric measure by a categorical group column.
    Supports sum, mean, median, count, min, max.
    Handles null groups cleanly and ranks highest and lowest performers.
    """
    if group_col not in df.columns:
        raise ValueError(f"Grouping column '{group_col}' does not exist in dataset.")
    if measure_col not in df.columns:
        raise ValueError(f"Measure column '{measure_col}' does not exist in dataset.")

    valid_aggs = {"sum", "mean", "median", "count", "min", "max"}
    agg_clean = aggregation.lower().strip()
    if agg_clean not in valid_aggs:
        raise ValueError(f"Unsupported aggregation '{aggregation}'. Must be one of: {', '.join(sorted(valid_aggs))}.")

    work_df = df[[group_col, measure_col]].copy()
    work_df[group_col] = work_df[group_col].fillna("(Missing / None)").astype(str)
    work_df[measure_col] = pd.to_numeric(work_df[measure_col], errors="coerce")

    grouped = work_df.groupby(group_col)[measure_col].agg(agg_clean).dropna()
    grouped_sorted = grouped.sort_values(ascending=False)

    total_groups = len(grouped_sorted)
    if total_groups == 0:
        return sanitize_for_json({
            "group_column": group_col,
            "measure_column": measure_col,
            "aggregation": agg_clean,
            "total_groups": 0,
            "records": [],
            "highest_performing": None,
            "lowest_performing": None,
            "negative_groups": [],
        })

    # Total sum of the measure across all groups for contribution %
    total_val = float(grouped.sum()) if agg_clean == "sum" else None

    records = []
    negative_groups = []

    for name, val in grouped_sorted.head(limit).items():
        val_float = float(val)
        pct = round((val_float / total_val * 100.0), 2) if (total_val and total_val != 0.0) else None
        record = {
            "group": str(name),
            "value": round(val_float, 2),
            "percentage_of_total": pct,
        }
        records.append(record)
        if val_float < 0:
            negative_groups.append(record)

    highest = {
        "group": str(grouped_sorted.index[0]),
        "value": round(float(grouped_sorted.iloc[0]), 2),
    }
    lowest = {
        "group": str(grouped_sorted.index[-1]),
        "value": round(float(grouped_sorted.iloc[-1]), 2),
    }

    return sanitize_for_json({
        "group_column": group_col,
        "measure_column": measure_col,
        "aggregation": agg_clean,
        "total_groups": total_groups,
        "records": records,
        "highest_performing": highest,
        "lowest_performing": lowest,
        "negative_groups": negative_groups,
        "performance_note": (
            f"Ranked by {agg_clean} of '{measure_col}'. Note that highest value is not always optimal "
            "(e.g., lower costs or defects are preferred)."
        ),
    })


def calculate_date_trends(
    df: pd.DataFrame,
    date_col: str,
    measure_col: str,
    aggregation: str = "sum",
    granularity: str = "monthly",
) -> Dict[str, Any]:
    """
    Generate chronological time-series aggregations across specified date granularity.
    Granularities: daily ('D'), weekly ('W'), monthly ('M'), quarterly ('Q'), yearly ('Y').
    """
    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' does not exist.")
    if measure_col not in df.columns:
        raise ValueError(f"Measure column '{measure_col}' does not exist.")

    valid_aggs = {"sum", "mean", "median", "count", "min", "max"}
    agg_clean = aggregation.lower().strip()
    if agg_clean not in valid_aggs:
        raise ValueError(f"Unsupported aggregation '{aggregation}'. Must be one of: {', '.join(sorted(valid_aggs))}.")

    valid_granularities = {"daily", "weekly", "monthly", "quarterly", "yearly"}
    gran_clean = granularity.lower().strip()
    if gran_clean not in valid_granularities:
        raise ValueError(f"Unsupported granularity '{granularity}'. Must be one of: {', '.join(sorted(valid_granularities))}.")

    work_df = df[[date_col, measure_col]].copy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        work_df["parsed_date"] = pd.to_datetime(work_df[date_col], errors="coerce")
    work_df["numeric_measure"] = pd.to_numeric(work_df[measure_col], errors="coerce")

    valid_rows = work_df.dropna(subset=["parsed_date", "numeric_measure"]).copy()
    invalid_dates_count = int(work_df["parsed_date"].isnull().sum())

    if valid_rows.empty:
        return sanitize_for_json({
            "date_column": date_col,
            "measure_column": measure_col,
            "granularity": gran_clean,
            "aggregation": agg_clean,
            "labels": [],
            "values": [],
            "data_points": [],
            "total_periods": 0,
            "valid_records_count": 0,
            "invalid_dates_count": invalid_dates_count,
            "message": "No valid date and measure pairs found for trend analysis.",
        })

    # Period formatting by granularity
    if gran_clean == "daily":
        valid_rows["period"] = valid_rows["parsed_date"].dt.strftime("%Y-%m-%d")
        period_sort_key = valid_rows["parsed_date"].dt.date
    elif gran_clean == "weekly":
        valid_rows["period"] = valid_rows["parsed_date"].dt.strftime("%Y-W%W")
        period_sort_key = valid_rows["parsed_date"].dt.to_period("W")
    elif gran_clean == "monthly":
        valid_rows["period"] = valid_rows["parsed_date"].dt.strftime("%Y-%m")
        period_sort_key = valid_rows["parsed_date"].dt.to_period("M")
    elif gran_clean == "quarterly":
        valid_rows["period"] = valid_rows["parsed_date"].dt.to_period("Q").astype(str)
        period_sort_key = valid_rows["parsed_date"].dt.to_period("Q")
    else:  # yearly
        valid_rows["period"] = valid_rows["parsed_date"].dt.strftime("%Y")
        period_sort_key = valid_rows["parsed_date"].dt.to_period("Y")

    valid_rows["sort_key"] = period_sort_key

    grouped = (
        valid_rows.groupby(["sort_key", "period"])["numeric_measure"]
        .agg(agg_clean)
        .reset_index()
    )
    grouped = grouped.sort_values(by="sort_key", ascending=True)

    labels = grouped["period"].tolist()
    values = [round(float(v), 2) for v in grouped["numeric_measure"].tolist()]
    data_points = [{"period": str(p), "value": v} for p, v in zip(labels, values)]

    min_date = valid_rows["parsed_date"].min().strftime("%Y-%m-%d")
    max_date = valid_rows["parsed_date"].max().strftime("%Y-%m-%d")

    return sanitize_for_json({
        "date_column": date_col,
        "measure_column": measure_col,
        "granularity": gran_clean,
        "aggregation": agg_clean,
        "labels": labels,
        "values": values,
        "data_points": data_points,
        "total_periods": len(labels),
        "valid_records_count": len(valid_rows),
        "invalid_dates_count": invalid_dates_count,
        "start_date": min_date,
        "end_date": max_date,
    })


def calculate_period_over_period(
    df: pd.DataFrame,
    date_col: str,
    measure_col: str,
    aggregation: str = "sum",
    granularity: str = "monthly",
) -> Dict[str, Any]:
    """
    Compare the latest period against the immediately preceding period.
    Reports absolute change, percentage change, and directional change.
    """
    trend_res = calculate_date_trends(
        df=df,
        date_col=date_col,
        measure_col=measure_col,
        aggregation=aggregation,
        granularity=granularity,
    )

    data_points = trend_res.get("data_points", [])
    if len(data_points) < 2:
        return sanitize_for_json({
            "is_valid_comparison": False,
            "message": (
                f"Insufficient periods ({len(data_points)}) to perform period-over-period comparison. "
                "At least 2 consecutive periods are required."
            ),
            "date_column": date_col,
            "measure_column": measure_col,
            "granularity": granularity,
        })

    prev = data_points[-2]
    curr = data_points[-1]

    curr_val = float(curr["value"])
    prev_val = float(prev["value"])
    abs_change = round(curr_val - prev_val, 2)

    if prev_val != 0.0:
        pct_change = round((abs_change / abs(prev_val)) * 100.0, 2)
    else:
        pct_change = None

    if abs_change > 0:
        direction = "increase"
    elif abs_change < 0:
        direction = "decrease"
    else:
        direction = "neutral"

    pct_str = f"{pct_change:+.1f}%" if pct_change is not None else "N/A (prev=0)"
    explanation = (
        f"{granularity.capitalize()} {aggregation} of '{measure_col}' moved from {prev_val:,.2f} in "
        f"{prev['period']} to {curr_val:,.2f} in {curr['period']}, an {direction} of "
        f"{abs_change:+,.2f} ({pct_str})."
    )

    return sanitize_for_json({
        "is_valid_comparison": True,
        "date_column": date_col,
        "measure_column": measure_col,
        "granularity": granularity,
        "aggregation": aggregation,
        "current_period": str(curr["period"]),
        "current_value": curr_val,
        "previous_period": str(prev["period"]),
        "previous_value": prev_val,
        "absolute_change": abs_change,
        "percentage_change": pct_change,
        "direction": direction,
        "explanation": explanation,
    })


def generate_deterministic_insights(
    df: pd.DataFrame,
    revenue_col: Optional[str] = None,
    profit_col: Optional[str] = None,
    date_col: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Generate evidence-based deterministic insights across Data Quality, Performance,
    Trend, and Anomaly categories without using any external LLM service.
    """
    insights = []
    if df.empty:
        return []

    discovery = discover_business_kpis(df)
    mappings = discovery.get("inferred_mappings", {})

    rev = revenue_col or mappings.get("revenue_col")
    prof = profit_col or mappings.get("profit_col")
    date_c = date_col or (discovery.get("date_columns")[0] if discovery.get("date_columns") else None)

    # 1. Performance Insight: Revenue & Profit
    if rev and rev in df.columns:
        total_rev = float(pd.to_numeric(df[rev], errors="coerce").sum())
        insights.append({
            "title": f"Total {rev} Volume",
            "category": "Performance",
            "explanation": f"Dataset accounts for ${total_rev:,.2f} in total {rev}.",
            "supporting_metric": {"total": total_rev, "column": rev},
            "severity": "positive" if total_rev > 0 else "info",
            "recommended_action": f"Drill down into {rev} by categorical dimensions to identify top revenue drivers.",
        })

    # 2. Performance Insight: Profit Margin or Loss
    if rev and prof and rev in df.columns and prof in df.columns:
        tot_rev = float(pd.to_numeric(df[rev], errors="coerce").sum())
        tot_prof = float(pd.to_numeric(df[prof], errors="coerce").sum())
        if tot_rev != 0:
            margin = (tot_prof / tot_rev) * 100.0
            if margin < 0:
                insights.append({
                    "title": "Negative Net Profit Margin",
                    "category": "Performance",
                    "explanation": f"Net profit margin is negative ({margin:.1f}%), indicating total costs exceed revenue.",
                    "supporting_metric": {"margin_pct": round(margin, 2)},
                    "severity": "warning",
                    "recommended_action": "Audit loss-making products or regions to pinpoint negative margins.",
                })
            else:
                insights.append({
                    "title": f"Healthy Profit Margin ({margin:.1f}%)",
                    "category": "Performance",
                    "explanation": f"Net profit is ${tot_prof:,.2f} on revenue of ${tot_rev:,.2f}.",
                    "supporting_metric": {"margin_pct": round(margin, 2)},
                    "severity": "positive",
                    "recommended_action": "Maintain healthy margins while exploring expansion in top categories.",
                })

    # 3. Trend Insight: Latest Period-over-Period
    if date_c and rev:
        try:
            pop = calculate_period_over_period(df, date_col=date_c, measure_col=rev, granularity="monthly")
            if pop.get("is_valid_comparison"):
                chg = pop.get("percentage_change")
                direction = pop.get("direction")
                insights.append({
                    "title": f"Monthly {rev} {direction.capitalize()}",
                    "category": "Trend",
                    "explanation": pop["explanation"],
                    "supporting_metric": {"change_pct": chg, "absolute_change": pop["absolute_change"]},
                    "severity": "warning" if direction == "decrease" else "positive",
                    "recommended_action": (
                        "Investigate demand factors contributing to recent monthly movement."
                        if direction == "decrease" else "Analyze customer acquisition trends driving growth."
                    ),
                })
        except Exception:
            pass

    return sanitize_for_json(insights)
