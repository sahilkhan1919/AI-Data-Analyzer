"""
test_insights.py – Tests for the /insights endpoint.

Covers: valid insights, statistical correctness, invalid dataset,
non-numeric columns, missing parameters.
"""

import io
import pytest


class TestInsightsValid:
    def test_returns_200(self, client, uploaded_dataset_id):
        resp = client.post(
            "/insights",
            json={
                "dataset_id": uploaded_dataset_id,
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 200

    def test_returns_insights_list(self, client, uploaded_dataset_id):
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
        assert len(body["insights"]) > 0

    def test_includes_row_count(self, client, uploaded_dataset_id):
        resp = client.post(
            "/insights",
            json={
                "dataset_id": uploaded_dataset_id,
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        body = resp.get_json()
        row_insights = [i for i in body["insights"] if "rows" in i.lower()]
        assert len(row_insights) > 0

    def test_includes_column_count(self, client, uploaded_dataset_id):
        resp = client.post(
            "/insights",
            json={
                "dataset_id": uploaded_dataset_id,
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        body = resp.get_json()
        col_insights = [i for i in body["insights"] if "column" in i.lower()]
        assert len(col_insights) > 0

    def test_total_value_correct(self, client):
        """Verify total calculation matches expected independent value."""
        from app import DATASETS
        csv_content = b"Category,Value\nA,10\nB,20\nC,30\n"
        data = {"file": (io.BytesIO(csv_content), "calc.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.post(
            "/insights",
            json={"dataset_id": dataset_id, "x_axis": "Category", "y_axis": "Value"},
        )
        body = resp.get_json()
        total_line = next((i for i in body["insights"] if "Total Value" in i), None)
        assert total_line is not None
        # 10 + 20 + 30 = 60
        assert "60.00" in total_line

    def test_average_value_correct(self, client):
        """Verify average calculation matches expected independent value."""
        from app import DATASETS
        csv_content = b"Category,Value\nA,10\nB,20\nC,30\n"
        data = {"file": (io.BytesIO(csv_content), "calc.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.post(
            "/insights",
            json={"dataset_id": dataset_id, "x_axis": "Category", "y_axis": "Value"},
        )
        body = resp.get_json()
        avg_line = next((i for i in body["insights"] if "Average Value" in i), None)
        assert avg_line is not None
        # (10 + 20 + 30) / 3 = 20.0
        assert "20.00" in avg_line

    def test_max_value_correct(self, client):
        csv_content = b"Category,Value\nA,10\nB,20\nC,30\n"
        data = {"file": (io.BytesIO(csv_content), "calc.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.post(
            "/insights",
            json={"dataset_id": dataset_id, "x_axis": "Category", "y_axis": "Value"},
        )
        body = resp.get_json()
        max_line = next((i for i in body["insights"] if "Maximum Value" in i), None)
        assert max_line is not None
        assert "30.00" in max_line

    def test_min_value_correct(self, client):
        csv_content = b"Category,Value\nA,10\nB,20\nC,30\n"
        data = {"file": (io.BytesIO(csv_content), "calc.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.post(
            "/insights",
            json={"dataset_id": dataset_id, "x_axis": "Category", "y_axis": "Value"},
        )
        body = resp.get_json()
        min_line = next((i for i in body["insights"] if "Minimum Value" in i), None)
        assert min_line is not None
        assert "10.00" in min_line

    def test_top_x_identified(self, client):
        """Top groupby value should be identified correctly."""
        csv_content = b"Category,Value\nA,100\nB,20\nC,30\n"
        data = {"file": (io.BytesIO(csv_content), "top.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.post(
            "/insights",
            json={"dataset_id": dataset_id, "x_axis": "Category", "y_axis": "Value"},
        )
        body = resp.get_json()
        top_line = next((i for i in body["insights"] if "Top Category" in i), None)
        assert top_line is not None
        assert "A" in top_line


class TestInsightsNonNumericY:
    def test_non_numeric_y_returns_row_col_counts(self, client):
        csv_content = b"Name,City\nAlice,NY\nBob,LA\n"
        data = {"file": (io.BytesIO(csv_content), "text.csv")}
        upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
        dataset_id = upload_resp.get_json()["dataset_id"]

        resp = client.post(
            "/insights",
            json={"dataset_id": dataset_id, "x_axis": "Name", "y_axis": "City"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        # Should still return row/column counts even without numeric y
        assert any("rows" in i.lower() for i in body["insights"])


class TestInsightsInvalidDataset:
    def test_nonexistent_dataset_returns_404(self, client):
        import uuid
        resp = client.post(
            "/insights",
            json={
                "dataset_id": str(uuid.uuid4()),
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 404

    def test_invalid_uuid_returns_400(self, client):
        resp = client.post(
            "/insights",
            json={"dataset_id": "bad-id", "x_axis": "Category", "y_axis": "Value"},
        )
        assert resp.status_code == 400

    def test_non_json_returns_415(self, client, uploaded_dataset_id):
        resp = client.post("/insights", data="not json", content_type="text/plain")
        assert resp.status_code == 415
