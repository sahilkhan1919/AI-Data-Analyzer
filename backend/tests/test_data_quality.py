"""
test_data_quality.py – Unit tests for the Data Quality Engine.

Tests functions in backend.analytics.data_quality directly:
  - Empty DataFrames
  - Missing value detection & strategies
  - Duplicate detection & preview
  - Empty rows & columns
  - Numeric & categorical profiling
  - Constant columns & high cardinality
  - IQR outlier detection (normal, outliers, IQR=0, <4 rows)
  - Date detection
  - JSON serialization safety
  - Quality score boundaries and calculations
"""

import json
import numpy as np
import pandas as pd
import pytest

from analytics.data_quality import (
    compute_column_profiling,
    compute_data_quality_score,
    compute_dataset_overview,
    compute_duplicate_detection,
    compute_missing_value_analysis,
    compute_outlier_detection,
    detect_date_columns,
    generate_quality_report,
    sanitize_for_json,
)


class TestEmptyDataFrame:
    def test_overview_empty_dataframe(self):
        df = pd.DataFrame()
        overview = compute_dataset_overview(df)
        assert overview["total_rows"] == 0
        assert overview["total_columns"] == 0
        assert overview["missing_cell_percentage"] == 0.0

    def test_profiling_empty_dataframe(self):
        df = pd.DataFrame()
        profiles = compute_column_profiling(df)
        assert profiles == []

    def test_quality_score_empty_dataframe(self):
        df = pd.DataFrame()
        score = compute_data_quality_score(df)
        assert score["score"] == 0.0
        assert score["grade"] == "Empty"

    def test_json_serialization_empty_dataframe(self):
        df = pd.DataFrame()
        report = generate_quality_report(df)
        # Must be valid json without error
        serialized = json.dumps(report)
        assert isinstance(serialized, str)


class TestMissingValues:
    def test_detects_missing_cells_accurately(self):
        df = pd.DataFrame({
            "A": [1, 2, np.nan, 4],
            "B": ["x", None, "z", "w"],
        })
        res = compute_missing_value_analysis(df)
        assert res["total_missing_cells"] == 2
        assert res["missing_cell_percentage"] == 25.0

    def test_high_missing_recommends_removal(self):
        df = pd.DataFrame({
            "sparse": [1, np.nan, np.nan, np.nan, np.nan],  # 80% missing
        })
        res = compute_missing_value_analysis(df)
        col_res = res["columns_with_missing"][0]
        assert "Investigate / Consider Column Removal" in col_res["recommendation_strategy"]

    def test_low_missing_numeric_recommends_imputation(self):
        # 1 out of 25 is 4% (< 5%)
        nums = [10.0] * 24 + [np.nan]
        df = pd.DataFrame({"Score": nums})
        res = compute_missing_value_analysis(df)
        col_res = res["columns_with_missing"][0]
        assert "Median or Mean Imputation" in col_res["recommendation_strategy"]

    def test_categorical_missing_recommends_unknown_category(self):
        df = pd.DataFrame({
            "City": ["Paris", "Tokyo", None, "London"],
        })
        res = compute_missing_value_analysis(df)
        col_res = res["columns_with_missing"][0]
        assert "Unknown" in col_res["recommendation_strategy"] or "Mode" in col_res["recommendation_strategy"]


class TestDuplicates:
    def test_detects_exact_duplicates(self):
        df = pd.DataFrame({
            "id": [1, 2, 2, 3],
            "val": ["a", "b", "b", "c"],
        })
        res = compute_duplicate_detection(df)
        assert res["total_rows"] == 4
        assert res["duplicate_rows_count"] == 1
        assert res["duplicate_percentage"] == 25.0
        assert res["unique_rows_count"] == 3
        assert len(res["duplicate_preview"]) > 0

    def test_no_duplicates(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        res = compute_duplicate_detection(df)
        assert res["duplicate_rows_count"] == 0
        assert res["duplicate_percentage"] == 0.0
        assert len(res["duplicate_preview"]) == 0


class TestEmptyRowsAndColumns:
    def test_detects_empty_rows_and_cols(self):
        df = pd.DataFrame([
            {"A": 1, "B": np.nan, "C": np.nan},
            {"A": np.nan, "B": np.nan, "C": np.nan},  # all NaN row
            {"A": 3, "B": np.nan, "C": np.nan},       # Col B and C are all NaN
        ])
        overview = compute_dataset_overview(df)
        assert overview["empty_rows_count"] == 1
        assert overview["empty_columns_count"] == 2


class TestColumnProfiling:
    def test_numeric_statistics(self):
        df = pd.DataFrame({
            "Metric": [10.0, 20.0, 30.0, 40.0, 50.0],
        })
        profiles = compute_column_profiling(df)
        p = profiles[0]
        assert p["detected_type"] == "numeric"
        assert p["min"] == 10.0
        assert p["max"] == 50.0
        assert p["mean"] == 30.0
        assert p["median"] == 30.0
        assert p["q1"] == 20.0
        assert p["q3"] == 40.0

    def test_categorical_profiling(self):
        df = pd.DataFrame({
            "Color": ["Red", "Blue", "Red", "Green", "Red", "Blue"],
        })
        profiles = compute_column_profiling(df)
        p = profiles[0]
        assert p["detected_type"] == "categorical"
        assert p["unique_count"] == 3
        assert p["most_frequent_value"] == "Red"
        assert p["most_frequent_count"] == 3

    def test_constant_column(self):
        df = pd.DataFrame({
            "Const": [42, 42, 42, 42],
        })
        profiles = compute_column_profiling(df)
        assert profiles[0]["is_constant"] is True


class TestIQROutliers:
    def test_flags_known_outliers(self):
        # 10, 11, 12, 13, 14, 15, 1000 -> 1000 is clearly an outlier
        vals = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 1000.0]
        df = pd.DataFrame({"Value": vals})
        res = compute_outlier_detection(df)
        col_res = res["columns"][0]
        assert col_res["status"] == "has_outliers"
        assert col_res["outlier_count"] == 1
        assert 1000.0 in col_res["examples"]

    def test_handles_constant_column_zero_iqr(self):
        df = pd.DataFrame({"Const": [5.0, 5.0, 5.0, 5.0, 5.0]})
        res = compute_outlier_detection(df)
        col_res = res["columns"][0]
        assert col_res["iqr"] == 0.0
        assert col_res["outlier_count"] == 0

    def test_insufficient_data(self):
        df = pd.DataFrame({"Tiny": [1.0, 2.0]})
        res = compute_outlier_detection(df)
        col_res = res["columns"][0]
        assert col_res["status"] == "insufficient_data"
        assert col_res["outlier_count"] == 0


class TestDateDetection:
    def test_identifies_date_column(self):
        df = pd.DataFrame({
            "order_date": ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"],
            "not_a_date": ["A", "B", "C", "D"],
            "id_col": [1, 2, 3, 4],
        })
        date_cols = detect_date_columns(df)
        assert "order_date" in date_cols
        assert "not_a_date" not in date_cols
        assert "id_col" not in date_cols


class TestQualityScore:
    def test_perfect_score(self):
        # Clean, unique, evenly distributed, no missing, no duplicates
        df = pd.DataFrame({
            "ID": [1, 2, 3, 4, 5],
            "Score": [10.0, 20.0, 30.0, 40.0, 50.0],
        })
        res = compute_data_quality_score(df)
        assert res["score"] == 100.0
        assert res["grade"] == "Excellent"

    def test_penalties_applied(self):
        # 50% duplicates, 50% missing
        df = pd.DataFrame({
            "A": [1, 1, np.nan, np.nan],
            "B": [10, 10, np.nan, np.nan],
        })
        res = compute_data_quality_score(df)
        assert res["score"] < 100.0
        assert res["penalties"]["missing_penalty"] > 0
        assert res["penalties"]["duplicate_penalty"] > 0
        assert 0.0 <= res["score"] <= 100.0


class TestSanitizeForJson:
    def test_replaces_nan_and_inf(self):
        payload = {
            "nan": float("nan"),
            "inf": float("inf"),
            "neg_inf": float("-inf"),
            "valid": 42.5,
            "int_val": np.int64(10),
            "date": pd.Timestamp("2023-05-01"),
        }
        sanitized = sanitize_for_json(payload)
        assert sanitized["nan"] is None
        assert sanitized["inf"] is None
        assert sanitized["neg_inf"] is None
        assert sanitized["valid"] == 42.5
        assert sanitized["int_val"] == 10
        assert isinstance(sanitized["date"], str)
        # Verify json dumps succeeds
        assert json.dumps(sanitized)
