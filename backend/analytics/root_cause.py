"""Period comparison and descriptive contributor decomposition."""

from typing import Any

import pandas as pd

from analytics.data_quality import sanitize_for_json


_PERIOD_FREQUENCIES = {
    "daily": "D",
    "weekly": "W",
    "monthly": "M",
    "quarterly": "Q",
    "yearly": "Y",
}


def analyze_root_cause(
    df: pd.DataFrame,
    date_col: str,
    measure_col: str,
    dimensions: list[str] | None = None,
    granularity: str = "monthly",
    top_n: int = 10,
) -> dict[str, Any]:
    """Decompose an observed period change by dimensions without asserting causation."""
    if not isinstance(granularity, str):
        raise ValueError("granularity must be a string.")
    granularity = granularity.lower()
    if granularity not in _PERIOD_FREQUENCIES:
        raise ValueError("granularity must be daily, weekly, monthly, quarterly, or yearly.")
    if date_col not in df.columns or measure_col not in df.columns:
        raise ValueError("The selected date and measure columns must exist in the dataset.")
    if not pd.api.types.is_numeric_dtype(df[measure_col]):
        raise ValueError(f"Measure column '{measure_col}' must be numeric.")

    if dimensions is not None and (
        not isinstance(dimensions, list)
        or any(not isinstance(dimension, str) for dimension in dimensions)
    ):
        raise ValueError("dimensions must be a list of column names.")
    dimensions = dimensions or [
        str(column)
        for column in df.columns
        if column not in {date_col, measure_col}
        and not pd.api.types.is_numeric_dtype(df[column])
        and not pd.api.types.is_datetime64_any_dtype(df[column])
    ]
    if len(dimensions) > 5:
        raise ValueError("Select no more than five dimensions.")
    if any(dimension not in df.columns for dimension in dimensions):
        raise ValueError("Every selected dimension must exist in the dataset.")
    if date_col in dimensions or measure_col in dimensions:
        raise ValueError("Date and measure columns cannot also be dimensions.")
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
        raise ValueError("top_n must be a positive integer.")

    work = df[[date_col, measure_col, *dimensions]].copy()
    work["_date"] = pd.to_datetime(work[date_col], errors="coerce", utc=True).dt.tz_localize(None)
    work["_measure"] = pd.to_numeric(work[measure_col], errors="coerce")
    work = work.dropna(subset=["_date", "_measure"])
    if work.empty:
        raise ValueError("No valid date and numeric measure pairs are available.")

    work["_period"] = work["_date"].dt.to_period(_PERIOD_FREQUENCIES[granularity])
    periods = sorted(work["_period"].unique())
    if len(periods) < 2:
        raise ValueError("At least two observed periods are required for comparison.")
    previous_period, current_period = periods[-2], periods[-1]
    previous = work.loc[work["_period"] == previous_period, "_measure"]
    current = work.loc[work["_period"] == current_period, "_measure"]
    previous_total = float(previous.sum())
    current_total = float(current.sum())
    total_change = current_total - previous_total

    contributors = []
    for dimension in dimensions:
        previous_groups = (
            work.loc[work["_period"] == previous_period]
            .assign(_group=lambda frame: frame[dimension].fillna("(Missing)").astype(str))
            .groupby("_group")["_measure"]
            .sum()
        )
        current_groups = (
            work.loc[work["_period"] == current_period]
            .assign(_group=lambda frame: frame[dimension].fillna("(Missing)").astype(str))
            .groupby("_group")["_measure"]
            .sum()
        )
        changes = pd.concat(
            [previous_groups.rename("previous"), current_groups.rename("current")],
            axis=1,
        ).fillna(0)
        changes["change"] = changes["current"] - changes["previous"]
        changes = changes.sort_values("change", ascending=(total_change < 0))
        rows = []
        for group, values in changes.head(min(top_n, 20)).iterrows():
            delta = float(values["change"])
            contributes = (total_change < 0 and delta < 0) or (
                total_change > 0 and delta > 0
            )
            rows.append(
                {
                    "group": str(group),
                    "previous_value": float(values["previous"]),
                    "current_value": float(values["current"]),
                    "change": delta,
                    "contribution_of_net_change_pct": (
                        round(abs(delta / total_change) * 100, 2) if contributes else None
                    ),
                    "direction": "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged",
                }
            )
        contributors.append(
            {
                "dimension": dimension,
                "contributors": rows,
                "interpretation": (
                    "Descriptive association with the observed change; not proof of causation."
                ),
            }
        )

    return sanitize_for_json(
        {
            "is_valid_comparison": True,
            "metric": measure_col,
            "granularity": granularity,
            "previous_period": str(previous_period),
            "current_period": str(current_period),
            "previous_value": previous_total,
            "current_value": current_total,
            "absolute_change": total_change,
            "percentage_change": (
                round(total_change / abs(previous_total) * 100, 2)
                if previous_total != 0
                else None
            ),
            "direction": "increase" if total_change > 0 else "decrease" if total_change < 0 else "neutral",
            "valid_records": int(len(work)),
            "dimensions": contributors,
            "limitations": [
                "These are observed associations and do not establish causal factors.",
                "The comparison uses the latest two periods present in the dataset; the periods may not be consecutive.",
            ],
            "recommended_next_action": (
                "Investigate the largest measured contributors and validate them with operational context."
            ),
        }
    )
