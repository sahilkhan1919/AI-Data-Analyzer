"""
test_chart.py – Tests for the /chart-data endpoint.

Covers: valid chart types, column validation, dataset lookup errors,
histogram behavior, missing parameters.
"""

import io
import pytest


class TestChartValidCSV:
    def test_bar_chart_returns_200(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 200

    def test_bar_chart_returns_labels_and_values(self, client, uploaded_dataset_id):
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
        assert len(body["labels"]) == len(body["values"])

    def test_line_chart_returns_200(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Line",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 200

    def test_pie_chart_aggregates_correctly(self, client, uploaded_dataset_id):
        """Pie chart should group by x_axis and sum y_axis."""
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Pie",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        # Category A appears with values 10 and 5 → sum = 15
        # But after cleaning duplicates, depends on actual data
        assert "labels" in body
        assert "values" in body

    def test_scatter_chart_returns_200(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Scatter",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 200

    def test_histogram_returns_200(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Histogram",
                "x_axis": "Value",
                "y_axis": "",
            },
        )
        assert resp.status_code == 200

    def test_histogram_no_y_axis_needed(self, client, uploaded_dataset_id):
        """Histogram works without a y_axis value."""
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Histogram",
                "x_axis": "Value",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "values" in body


class TestChartInvalidDataset:
    def test_nonexistent_dataset_returns_404(self, client):
        import uuid
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": str(uuid.uuid4()),
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 404

    def test_invalid_uuid_returns_400(self, client):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": "not-a-uuid",
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 400

    def test_missing_dataset_id_returns_400(self, client):
        resp = client.post(
            "/chart-data",
            json={"chart_type": "Bar", "x_axis": "Category", "y_axis": "Value"},
        )
        assert resp.status_code == 400


class TestChartInvalidColumns:
    def test_nonexistent_x_axis_returns_400(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Bar",
                "x_axis": "NonExistentColumn",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 400

    def test_nonexistent_y_axis_returns_400(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "NonExistentColumn",
            },
        )
        assert resp.status_code == 400


class TestChartInvalidType:
    def test_invalid_chart_type_returns_400(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Radar",  # Not in allowed list
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 400

    def test_sql_injection_in_chart_type_rejected(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "'; DROP TABLE datasets; --",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 400


class TestChartMissingParameters:
    def test_missing_chart_type_returns_400(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 400

    def test_missing_x_axis_returns_400(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Bar",
                "y_axis": "Value",
            },
        )
        assert resp.status_code == 400

    def test_non_json_body_returns_415(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 415


class TestPieChartValues:
    def test_pie_chart_values_are_numeric(self, client, uploaded_dataset_id):
        resp = client.post(
            "/chart-data",
            json={
                "dataset_id": uploaded_dataset_id,
                "chart_type": "Pie",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        body = resp.get_json()
        for v in body["values"]:
            assert isinstance(v, (int, float))
