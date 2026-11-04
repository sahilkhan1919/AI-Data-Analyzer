"""Leakage-aware baseline forecasting for regularly indexed numeric series."""

import math
from typing import Any

import numpy as np
import pandas as pd

from analytics.data_quality import sanitize_for_json


_FREQUENCIES = {
    "daily": ("D", "D"),
    "weekly": ("W", "W"),
    "monthly": ("M", "MS"),
    "quarterly": ("Q", "QS"),
    "yearly": ("Y", "YS"),
}


def forecast_series(
    df: pd.DataFrame,
    date_col: str,
    measure_col: str,
    granularity: str = "monthly",
    aggregation: str = "sum",
    horizon: int = 3,
) -> dict[str, Any]:
    """Forecast with a last-observation baseline and chronological holdout metrics."""
    if not isinstance(granularity, str) or not isinstance(aggregation, str):
        raise ValueError("granularity and aggregation must be strings.")
    granularity = granularity.lower()
    aggregation = aggregation.lower()
    if granularity not in _FREQUENCIES:
        raise ValueError("granularity must be daily, weekly, monthly, quarterly, or yearly.")
    if aggregation not in {"sum", "mean", "median", "count", "min", "max"}:
        raise ValueError("Unsupported aggregation.")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or not 1 <= horizon <= 24:
        raise ValueError("Forecast horizon must be an integer from 1 to 24 periods.")
    if date_col not in df.columns or measure_col not in df.columns:
        raise ValueError("The selected date and measure columns must exist in the dataset.")

    work = df[[date_col, measure_col]].copy()
    work["_date"] = pd.to_datetime(work[date_col], errors="coerce", utc=True).dt.tz_localize(None)
    work["_value"] = pd.to_numeric(work[measure_col], errors="coerce")
    work = work.dropna(subset=["_date", "_value"])
    if work.empty:
        raise ValueError("No valid date and numeric measure pairs are available.")

    period_frequency, future_frequency = _FREQUENCIES[granularity]
    work["_period"] = work["_date"].dt.to_period(period_frequency)
    observed = work.groupby("_period")["_value"].agg(aggregation).sort_index()
    complete_index = pd.period_range(observed.index.min(), observed.index.max(), freq=period_frequency)
    missing_count = int(len(complete_index) - len(observed))
    series = observed.reindex(complete_index).astype(float)
    if missing_count:
        if aggregation in {"sum", "count"}:
            series = series.fillna(0)
            missing_policy = "Missing periods were treated as zero for sum/count aggregation."
        else:
            series = series.interpolate(method="linear", limit_direction="both")
            missing_policy = "Missing periods were linearly interpolated between observations."
    else:
        missing_policy = "No periods were missing."

    values = series.to_numpy(dtype=float)
    if len(values) < 8:
        raise ValueError(
            f"At least 8 time periods are required; only {len(values)} are available."
        )
    if not np.isfinite(values).all():
        raise ValueError("The time series contains non-finite values after period preparation.")

    test_size = max(1, math.ceil(len(values) * 0.2))
    split = len(values) - test_size
    train, actual = values[:split], values[split:]
    if len(train) < 5:
        raise ValueError("Insufficient training history for a chronological holdout.")
    holdout_prediction = np.repeat(train[-1], len(actual))
    errors = actual - holdout_prediction
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    nonzero_actual = actual != 0
    mape = (
        float(np.mean(np.abs(errors[nonzero_actual] / actual[nonzero_actual])) * 100)
        if nonzero_actual.any()
        else None
    )

    baseline = float(values[-1])
    last_period = complete_index[-1].to_timestamp(how="start")
    future_dates = pd.date_range(
        start=last_period,
        periods=horizon + 1,
        freq=future_frequency,
    )[1:]
    forecasts = []
    for step, timestamp in enumerate(future_dates, start=1):
        margin = 1.96 * rmse * math.sqrt(step)
        forecasts.append(
            {
                "period": timestamp.strftime("%Y-%m-%d"),
                "prediction": baseline,
                "lower_bound": baseline - margin,
                "upper_bound": baseline + margin,
            }
        )

    return sanitize_for_json(
        {
            "date_column": date_col,
            "measure_column": measure_col,
            "granularity": granularity,
            "aggregation": aggregation,
            "method": "last-observation naive baseline",
            "history_periods": int(len(values)),
            "missing_periods": missing_count,
            "missing_period_policy": missing_policy,
            "train_periods": int(len(train)),
            "test_periods": int(len(actual)),
            "metrics": {
                "mae": mae,
                "rmse": rmse,
                "mape_percent": mape,
                "mape_excluded_zero_actuals": int((~nonzero_actual).sum()),
            },
            "historical": [
                {"period": str(period), "value": float(value)}
                for period, value in zip(complete_index, values)
            ],
            "forecast": forecasts,
            "uncertainty": (
                "Bounds are a simple 95%-style residual-error band from the holdout baseline; "
                "they are approximate, not guaranteed prediction intervals."
            ),
            "limitations": [
                "This is a simple baseline, not a causal model.",
                "Forecast quality may be poor when the series has seasonality, structural changes, or sparse observations.",
            ],
        }
    )
