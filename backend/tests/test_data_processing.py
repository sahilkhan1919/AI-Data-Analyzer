"""
test_data_processing.py – Tests for clean_data() and statistical correctness.

Tests the data-processing functions directly, independently of HTTP routing.
"""

import io
import pytest
import pandas as pd


class TestCleanDataFunction:
    def test_strips_column_whitespace(self):
        from app import clean_data
        df = pd.DataFrame({" Name ": ["Alice", "Bob"], " Score ": [90, 80]})
        cleaned = clean_data(df)
        assert "Name" in cleaned.columns
        assert "Score" in cleaned.columns

    def test_resolves_duplicate_columns_created_by_whitespace_trimming(self):
        from app import clean_data
        from analytics.business_intelligence import calculate_date_trends

        df = pd.DataFrame(
            [
                ["2025-01-01", "2025-01-02", 10],
                ["2025-02-01", "2025-02-02", 12],
            ],
            columns=["Date", " Date ", "Revenue"],
        )

        cleaned = clean_data(df)
        trends = calculate_date_trends(cleaned, "Date", "Revenue")

        assert cleaned.columns.tolist() == ["Date", "Date_2", "Revenue"]
        assert trends["total_periods"] == 2
        assert trends["values"] == [10, 12]

    def test_removes_duplicate_rows(self):
        from app import clean_data
        df = pd.DataFrame({"A": ["x", "x", "y"], "B": [1, 1, 2]})
        cleaned = clean_data(df)
        assert len(cleaned) == 2

    def test_drops_all_empty_rows(self):
        from app import clean_data
        df = pd.DataFrame({"A": ["x", None, "y"], "B": [1, None, 2]})
        cleaned = clean_data(df)
        # The row with all NaN should be dropped
        assert len(cleaned) == 2

    def test_fills_numeric_nan_with_mean(self):
        from app import clean_data
        # Use two named columns so no row is entirely NaN (dropna(how='all') won't drop it)
        df = pd.DataFrame({"Name": ["Alice", "Bob", "Charlie"], "Score": [10.0, None, 20.0]})
        cleaned = clean_data(df)
        # Mean of [10, 20] = 15.0; Bob's score should be filled
        assert not cleaned["Score"].isnull().any()
        bob_score = cleaned.loc[cleaned["Name"] == "Bob", "Score"].values[0]
        assert bob_score == pytest.approx(15.0, rel=1e-3)

    def test_fills_text_nan_with_unknown(self):
        from app import clean_data
        # Use two columns so the NaN row is not entirely empty (survives dropna(how='all'))
        df = pd.DataFrame({"Name": ["Alice", None, "Bob"], "Score": [1.0, 2.0, 3.0]})
        cleaned = clean_data(df)
        assert not cleaned["Name"].isnull().any()
        # Convert to list for Pandas 3 ArrowStringArray compatibility
        assert "Unknown" in list(cleaned["Name"])

    def test_returns_dataframe(self):
        from app import clean_data
        df = pd.DataFrame({"A": [1, 2, 3]})
        result = clean_data(df)
        assert isinstance(result, pd.DataFrame)

    def test_original_not_mutated(self):
        from app import clean_data
        df = pd.DataFrame({"A": [1, 1, 2]})
        original_len = len(df)
        clean_data(df)
        assert len(df) == original_len  # original should be unchanged


class TestStatisticalCorrectness:
    """Verify that statistics computed via pandas match independently-computed values."""

    def setup_method(self):
        self.data = [10, 20, 30, 40, 50]
        self.df = pd.DataFrame({"Value": self.data})

    def test_sum_matches_expected(self):
        assert self.df["Value"].sum() == 150

    def test_mean_matches_expected(self):
        assert self.df["Value"].mean() == pytest.approx(30.0)

    def test_max_matches_expected(self):
        assert self.df["Value"].max() == 50

    def test_min_matches_expected(self):
        assert self.df["Value"].min() == 10

    def test_duplicate_count_matches_expected(self):
        df = pd.DataFrame({"A": [1, 1, 2, 2, 3]})
        assert df.duplicated().sum() == 2


class TestDuplicateRemovalCorrectness:
    def test_exact_row_count_after_cleaning(self, client):
        """Upload a known CSV and verify the exact row count after cleaning."""
        # 5 rows, 2 duplicates → 3 unique rows
        csv_content = b"Cat,Val\nA,10\nA,10\nB,20\nB,20\nC,30\n"
        data = {"file": (io.BytesIO(csv_content), "dup.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert body["summary"]["total_rows"] == 3
        assert body["summary"]["duplicate_rows_removed"] == 2


class TestResponseFormatCompatibility:
    """Verify upload response fields match what the frontend expects."""

    def test_upload_response_has_all_required_fields(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        required = ["dataset_id", "columns", "numeric_columns", "summary", "preview"]
        for field in required:
            assert field in body, f"Missing field: {field}"

    def test_summary_has_all_required_sub_fields(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        summary = resp.get_json()["summary"]
        required = [
            "total_rows",
            "total_columns",
            "duplicate_rows_removed",
            "missing_values_handled",
        ]
        for field in required:
            assert field in summary, f"Missing summary field: {field}"

    def test_chart_response_has_labels_and_values(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        body = resp.get_json()
        assert "labels" in body
        assert "values" in body

    def test_insights_response_has_insights_list(self, client, uploaded_dataset_id):
        resp = client.post(
            "/insights",
            json={
                "dataset_id": uploaded_dataset_id,
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        body = resp.get_json()
        assert "insights" in body
        assert isinstance(body["insights"], list)

    def test_ask_response_has_answer_and_table(self, client, uploaded_dataset_id):
        resp = client.post(
            "/ask",
            json={"dataset_id": uploaded_dataset_id, "question": "count rows"},
        )
        body = resp.get_json()
        assert "answer" in body
        assert "table" in body
