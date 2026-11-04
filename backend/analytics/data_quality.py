"""
data_quality.py – Reusable Data Quality Engine for tabular datasets.

Provides comprehensive profiling, missing-value analysis, duplicate detection,
IQR-based outlier detection, transparent quality scoring, and actionable cleaning
recommendations without mutating the underlying data.
"""

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize objects so they are strictly JSON-serializable.
    Converts NaN/Inf to None, numpy types to native Python, and datetimes to ISO strings.
    """
    if obj is None:
        return None
    if isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(float(obj), 4)
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, pd.Series, np.ndarray)):
        return [sanitize_for_json(item) for item in obj]
    return str(obj)


def detect_date_columns(df: pd.DataFrame, sample_size: int = 50) -> List[str]:
    """
    Reliably detect date/datetime columns in a DataFrame.
    Checks native datetime dtypes first, then performs heuristic parsing on non-null samples.
    """
    date_cols = []
    for col in df.columns:
        series = df[col]
        # Native datetime
        if pd.api.types.is_datetime64_any_dtype(series):
            date_cols.append(str(col))
            continue

        # If object/string/category, test string samples
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            non_null = series.dropna()
            if non_null.empty:
                continue

            sample = non_null.astype(str).head(sample_size)
            # Avoid single integers or pure numbers like "1", "20" being misclassified
            all_pure_integers = all(s.strip().isdigit() and len(s.strip()) <= 4 for s in sample)
            if all_pure_integers and not any(k in str(col).lower() for k in ["year", "date", "day"]):
                continue

            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    parsed = pd.to_datetime(sample, errors="coerce")
                success_ratio = parsed.notnull().sum() / len(sample)
                # Require >= 80% parse success
                if success_ratio >= 0.8:
                    date_cols.append(str(col))
            except Exception:
                continue

    return date_cols


def compute_dataset_overview(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate dataset-level structural metrics.
    """
    total_rows = int(df.shape[0])
    total_columns = int(df.shape[1])

    if total_rows == 0 or total_columns == 0:
        return sanitize_for_json({
            "total_rows": total_rows,
            "total_columns": total_columns,
            "numeric_columns_count": 0,
            "categorical_columns_count": 0,
            "date_columns_count": 0,
            "date_columns": [],
            "total_missing_cells": 0,
            "missing_cell_percentage": 0.0,
            "duplicate_rows_count": 0,
            "duplicate_rows_percentage": 0.0,
            "empty_rows_count": 0,
            "empty_columns_count": 0,
        })

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    date_cols = detect_date_columns(df)
    categorical_cols = [c for c in df.columns if c not in numeric_cols and c not in date_cols]

    total_cells = total_rows * total_columns
    missing_cells = int(df.isnull().sum().sum())
    missing_pct = round((missing_cells / total_cells) * 100.0, 2) if total_cells > 0 else 0.0

    duplicate_rows = int(df.duplicated().sum())
    duplicate_pct = round((duplicate_rows / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

    empty_rows = int(df.isnull().all(axis=1).sum())
    empty_cols = int(df.isnull().all(axis=0).sum())

    return sanitize_for_json({
        "total_rows": total_rows,
        "total_columns": total_columns,
        "numeric_columns_count": len(numeric_cols),
        "categorical_columns_count": len(categorical_cols),
        "date_columns_count": len(date_cols),
        "date_columns": [str(c) for c in date_cols],
        "total_missing_cells": missing_cells,
        "missing_cell_percentage": missing_pct,
        "duplicate_rows_count": duplicate_rows,
        "duplicate_rows_percentage": duplicate_pct,
        "empty_rows_count": empty_rows,
        "empty_columns_count": empty_cols,
    })


def compute_column_profiling(df: pd.DataFrame, max_examples: int = 5) -> List[Dict[str, Any]]:
    """
    Profile each column with summary statistics, distribution traits, and safe samples.
    """
    profiles = []
    total_rows = int(df.shape[0])
    date_cols = set(detect_date_columns(df))

    for col in df.columns:
        series = df[col]
        non_null_count = int(series.notnull().sum())
        missing_count = int(series.isnull().sum())
        missing_pct = round((missing_count / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

        unique_count = int(series.nunique(dropna=True))
        duplicate_val_count = max(0, non_null_count - unique_count)

        is_constant = (unique_count <= 1 and non_null_count > 0)
        is_high_cardinality = (
            unique_count > 50 or (unique_count / non_null_count > 0.7 if non_null_count > 10 else False)
        )

        # Detect data type category
        if str(col) in date_cols or pd.api.types.is_datetime64_any_dtype(series):
            detected_type = "datetime"
        elif pd.api.types.is_bool_dtype(series):
            detected_type = "boolean"
        elif pd.api.types.is_numeric_dtype(series):
            detected_type = "numeric"
        else:
            detected_type = "categorical"

        # Safe sample example values
        sample_vals = series.dropna().unique()[:max_examples]
        example_values = [sanitize_for_json(val) for val in sample_vals]

        profile: Dict[str, Any] = {
            "column": str(col),
            "detected_type": detected_type,
            "non_null_count": non_null_count,
            "missing_count": missing_count,
            "missing_percentage": missing_pct,
            "unique_count": unique_count,
            "duplicate_value_count": duplicate_val_count,
            "is_constant": bool(is_constant),
            "is_high_cardinality": bool(is_high_cardinality),
            "example_values": example_values,
        }

        if detected_type == "numeric" and non_null_count > 0:
            num_clean = pd.to_numeric(series, errors="coerce").dropna()
            if not num_clean.empty:
                profile.update({
                    "min": float(num_clean.min()),
                    "max": float(num_clean.max()),
                    "mean": float(num_clean.mean()),
                    "median": float(num_clean.median()),
                    "std": float(num_clean.std()) if len(num_clean) > 1 else 0.0,
                    "q1": float(num_clean.quantile(0.25)),
                    "q3": float(num_clean.quantile(0.75)),
                })
        elif detected_type in ("categorical", "datetime"):
            if non_null_count > 0:
                val_counts = series.value_counts(dropna=True).head(5)
                top_values = [
                    {
                        "value": str(k),
                        "count": int(v),
                        "percentage": round((int(v) / non_null_count) * 100.0, 2),
                    }
                    for k, v in val_counts.items()
                ]
                profile["unique_categories"] = unique_count
                profile["most_frequent_value"] = str(val_counts.index[0]) if not val_counts.empty else None
                profile["most_frequent_count"] = int(val_counts.iloc[0]) if not val_counts.empty else 0
                profile["top_values"] = top_values

        profiles.append(sanitize_for_json(profile))

    return profiles


def compute_missing_value_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detect missing values and provide evidence-based, non-destructive recommendations.
    """
    total_rows = int(df.shape[0])
    total_cols = int(df.shape[1])
    total_cells = total_rows * total_cols
    total_missing = int(df.isnull().sum().sum())
    overall_pct = round((total_missing / total_cells) * 100.0, 2) if total_cells > 0 else 0.0

    columns_report = []

    for col in df.columns:
        series = df[col]
        missing_count = int(series.isnull().sum())
        missing_pct = round((missing_count / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

        if missing_count == 0:
            strategy = "No Action Required"
            explanation = "Column has complete data with zero missing values."
        elif missing_pct > 60.0:
            strategy = "Investigate / Consider Column Removal"
            explanation = (
                f"{missing_pct}% of entries are missing. If not required for core reporting, "
                "dropping this column reduces noise. Verify with business stakeholders."
            )
        elif pd.api.types.is_numeric_dtype(series):
            if missing_pct <= 5.0:
                strategy = "Median or Mean Imputation"
                explanation = (
                    f"Low missingness ({missing_pct}%). Median imputation is robust to skew; "
                    "mean imputation works well if data is normally distributed."
                )
            else:
                strategy = "Evaluate Domain Significance & Imputation"
                explanation = (
                    f"Moderate missingness ({missing_pct}%). Verify whether absence is non-random "
                    "(e.g., zero sales vs missing reporting) before imputing with median or predictive models."
                )
        else:
            strategy = "Explicit 'Unknown' Category or Mode Imputation"
            explanation = (
                f"{missing_pct}% missing in categorical column. Assigning an explicit 'Unknown' category "
                "retains row completeness without falsely skewing existing category frequencies."
            )

        columns_report.append({
            "column": str(col),
            "missing_count": missing_count,
            "missing_percentage": missing_pct,
            "data_type": "numeric" if pd.api.types.is_numeric_dtype(series) else "text/categorical",
            "recommendation_strategy": strategy,
            "explanation": explanation,
        })

    return sanitize_for_json({
        "total_missing_cells": total_missing,
        "missing_cell_percentage": overall_pct,
        "columns_with_missing": columns_report,
        "policy_note": "Recommendations are non-destructive and do not alter the underlying dataset.",
    })


def compute_duplicate_detection(df: pd.DataFrame, max_preview: int = 5) -> Dict[str, Any]:
    """
    Detect duplicated rows and evaluate analytical impact.
    """
    total_rows = int(df.shape[0])
    if total_rows == 0:
        return sanitize_for_json({
            "total_rows": 0,
            "duplicate_rows_count": 0,
            "duplicate_percentage": 0.0,
            "unique_rows_count": 0,
            "impact_explanation": "Dataset contains 0 rows.",
            "duplicate_preview": [],
        })

    dup_mask = df.duplicated(keep=False)
    dup_rows_count = int(df.duplicated(keep="first").sum())
    dup_pct = round((dup_rows_count / total_rows) * 100.0, 2)
    unique_rows_count = total_rows - dup_rows_count

    if dup_rows_count > 0:
        impact_explanation = (
            f"Detected {dup_rows_count} duplicated rows ({dup_pct}% of dataset). Duplicates can "
            "artificially inflate aggregations (e.g., total sales, customer counts) and distort averages. "
            "Verify whether duplicate entries represent distinct repeat events or redundant records."
        )
        preview_df = df[dup_mask].head(max_preview)
        duplicate_preview = preview_df.to_dict(orient="records")
    else:
        impact_explanation = "No duplicate rows detected. Each record in the dataset is unique."
        duplicate_preview = []

    return sanitize_for_json({
        "total_rows": total_rows,
        "duplicate_rows_count": dup_rows_count,
        "duplicate_percentage": dup_pct,
        "unique_rows_count": unique_rows_count,
        "impact_explanation": impact_explanation,
        "duplicate_preview": duplicate_preview,
    })


def compute_outlier_detection(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detect potential statistical outliers using the Interquartile Range (IQR) method:
      IQR = Q3 - Q1
      Lower Bound = Q1 - 1.5 * IQR
      Upper Bound = Q3 + 1.5 * IQR
    """
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    column_outliers = []
    total_outliers_across_dataset = 0
    total_numeric_observations = 0

    for col in numeric_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        n_obs = len(series)
        total_numeric_observations += n_obs

        if n_obs < 4:
            column_outliers.append({
                "column": str(col),
                "status": "insufficient_data",
                "message": "Fewer than 4 observations; IQR outlier detection cannot be computed reliably.",
                "q1": None,
                "q3": None,
                "iqr": None,
                "lower_bound": None,
                "upper_bound": None,
                "outlier_count": 0,
                "outlier_percentage": 0.0,
                "examples": [],
            })
            continue

        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = float(q3 - q1)

        if iqr == 0.0 or series.nunique() <= 1:
            column_outliers.append({
                "column": str(col),
                "status": "constant_or_zero_iqr",
                "message": "IQR is 0 or column has constant values; no outliers flagged.",
                "q1": q1,
                "q3": q3,
                "iqr": 0.0,
                "lower_bound": q1,
                "upper_bound": q3,
                "outlier_count": 0,
                "outlier_percentage": 0.0,
                "examples": [],
            })
            continue

        lower_bound = float(q1 - 1.5 * iqr)
        upper_bound = float(q3 + 1.5 * iqr)

        outlier_mask = (series < lower_bound) | (series > upper_bound)
        outlier_count = int(outlier_mask.sum())
        outlier_pct = round((outlier_count / n_obs) * 100.0, 2)
        total_outliers_across_dataset += outlier_count

        outlier_vals = series[outlier_mask].head(5).tolist()

        column_outliers.append({
            "column": str(col),
            "status": "has_outliers" if outlier_count > 0 else "normal",
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "outlier_count": outlier_count,
            "outlier_percentage": outlier_pct,
            "examples": [round(float(v), 2) for v in outlier_vals],
        })

    return sanitize_for_json({
        "analyzed_columns_count": len(numeric_cols),
        "total_outliers_count": total_outliers_across_dataset,
        "total_numeric_observations": total_numeric_observations,
        "columns": column_outliers,
        "summary_explanation": (
            "Outliers reflect values beyond 1.5x IQR from the first and third quartiles. "
            "They may represent genuine high-impact business transactions (e.g., enterprise deals) "
            "or data entry anomalies. Investigate before filtering."
        ),
    })


def compute_data_quality_score(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Transparent, explainable Data Quality Score (0 - 100).

    Scoring Model:
      Base Score: 100.0
      - Missing cell penalty: up to 40 points
          Penalty = min(40.0, (missing_cells / total_cells) * 100 * 0.8)
      - Duplicate row penalty: up to 30 points
          Penalty = min(30.0, (duplicate_rows / total_rows) * 100 * 0.6)
      - Statistical outlier penalty: up to 30 points
          Penalty = min(30.0, (total_outliers / total_numeric_observations) * 100 * 0.6)

      Final Score = max(0.0, min(100.0, 100.0 - (missing_penalty + duplicate_penalty + outlier_penalty)))
    """
    total_rows = int(df.shape[0])
    total_cols = int(df.shape[1])
    total_cells = total_rows * total_cols

    if total_rows == 0 or total_cols == 0:
        return sanitize_for_json({
            "score": 0.0,
            "grade": "Empty",
            "penalties": {
                "missing_penalty": 0.0,
                "duplicate_penalty": 0.0,
                "outlier_penalty": 0.0,
            },
            "formula": "Score = 100 - (missing_penalty[max 40] + duplicate_penalty[max 30] + outlier_penalty[max 30])",
            "limitations": "Score is 0 because the dataset contains no rows or columns.",
        })

    # 1. Missing penalty
    missing_cells = int(df.isnull().sum().sum())
    missing_ratio = (missing_cells / total_cells) * 100.0
    missing_penalty = min(40.0, round(missing_ratio * 0.8, 2))

    # 2. Duplicate penalty
    duplicate_rows = int(df.duplicated().sum())
    duplicate_ratio = (duplicate_rows / total_rows) * 100.0
    duplicate_penalty = min(30.0, round(duplicate_ratio * 0.6, 2))

    # 3. Outlier penalty
    outlier_res = compute_outlier_detection(df)
    total_outliers = outlier_res.get("total_outliers_count", 0)
    total_obs = outlier_res.get("total_numeric_observations", 0)
    if total_obs > 0:
        outlier_ratio = (total_outliers / total_obs) * 100.0
        outlier_penalty = min(30.0, round(outlier_ratio * 0.6, 2))
    else:
        outlier_penalty = 0.0

    final_score = round(max(0.0, min(100.0, 100.0 - (missing_penalty + duplicate_penalty + outlier_penalty))), 1)

    if final_score >= 90.0:
        grade = "Excellent"
    elif final_score >= 75.0:
        grade = "Good"
    elif final_score >= 50.0:
        grade = "Fair"
    else:
        grade = "Needs Attention"

    return sanitize_for_json({
        "score": final_score,
        "grade": grade,
        "penalties": {
            "missing_penalty": missing_penalty,
            "duplicate_penalty": duplicate_penalty,
            "outlier_penalty": outlier_penalty,
        },
        "metrics_evaluated": {
            "missing_cells": missing_cells,
            "missing_cell_percentage": round(missing_ratio, 2),
            "duplicate_rows": duplicate_rows,
            "duplicate_row_percentage": round(duplicate_ratio, 2),
            "outliers_detected": total_outliers,
        },
        "formula": "Score = 100 - (missing_penalty[max 40] + duplicate_penalty[max 30] + outlier_penalty[max 30])",
        "limitations": (
            "The Data Quality Score evaluates heuristic penalties (missing values, exact duplicates, and IQR outliers). "
            "A score of 100 indicates absence of flagged heuristics, not guaranteed business validity or semantic correctness."
        ),
    })


def generate_quality_report(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate a complete, bundled Data Quality Report.
    """
    overview = compute_dataset_overview(df)
    profiling = compute_column_profiling(df)
    missing = compute_missing_value_analysis(df)
    duplicates = compute_duplicate_detection(df)
    outliers = compute_outlier_detection(df)
    score_data = compute_data_quality_score(df)

    # Derive deterministic data quality insights
    insights = []
    if score_data["score"] >= 90:
        insights.append({
            "title": "High Data Quality Score",
            "category": "Data Quality",
            "explanation": f"Dataset scored {score_data['score']}/100 with minimal missing cells and duplicates.",
            "severity": "positive",
            "recommended_action": "Proceed with downstream exploratory and business intelligence analysis.",
        })
    elif score_data["score"] < 60:
        insights.append({
            "title": "Data Quality Concerns Detected",
            "category": "Data Quality",
            "explanation": f"Quality score is {score_data['score']}/100 due to penalties in missingness, duplicates, or outliers.",
            "severity": "warning",
            "recommended_action": "Review the missing value recommendations and duplicate rows before final reporting.",
        })

    if duplicates["duplicate_rows_count"] > 0:
        insights.append({
            "title": f"Duplicate Rows Found ({duplicates['duplicate_rows_count']})",
            "category": "Data Quality",
            "explanation": f"{duplicates['duplicate_percentage']}% of rows are identical copies.",
            "severity": "warning",
            "recommended_action": "Investigate whether duplicate records are valid re-orders or erroneous double-entries.",
        })

    if outliers["total_outliers_count"] > 0:
        insights.append({
            "title": f"Statistical Outliers Detected ({outliers['total_outliers_count']})",
            "category": "Anomaly",
            "explanation": "Values outside 1.5x IQR detected in numeric columns.",
            "severity": "info",
            "recommended_action": "Check extreme values in numeric columns to confirm whether they represent VIP transactions or data entry typos.",
        })

    return sanitize_for_json({
        "quality_score": score_data,
        "overview": overview,
        "column_profiles": profiling,
        "missing_analysis": missing,
        "duplicate_analysis": duplicates,
        "outlier_analysis": outliers,
        "quality_insights": insights,
    })
