"""
test_api_phase2.py – Integration tests for Phase 2 API endpoints:
  - /api/data-quality (GET & POST)
  - /api/data-profile (GET & POST)
  - /api/bi/kpis (POST)
  - /api/bi/group-analysis (POST)
  - /api/bi/trends (POST)
  - /api/bi/period-comparison (POST)
"""

import io
import pytest


@pytest.fixture()
def retail_dataset_id(client):
    """Upload a realistic retail CSV for BI and Data Quality API testing."""
    csv_content = (
        b"order_id,order_date,region,category,sales,profit,quantity\n"
        b"1001,2023-01-15,North,Furniture,250.00,50.00,2\n"
        b"1001,2023-01-15,North,Technology,400.00,120.00,1\n"
        b"1002,2023-02-10,South,Technology,150.00,-25.00,3\n"
        b"1003,2023-03-05,East,Office,80.00,15.00,5\n"
        b"1004,2023-03-20,West,Technology,500.00,150.00,2\n"
        b"1004,2023-03-20,West,Furniture,300.00,45.00,1\n"
    )
    data = {"file": (io.BytesIO(csv_content), "retail.csv")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    return resp.get_json()["dataset_id"]


class TestDataQualityEndpoint:
    def test_get_data_quality_success(self, client, retail_dataset_id):
        resp = client.get(f"/api/data-quality?dataset_id={retail_dataset_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "quality_score" in body
        assert "overview" in body
        assert "column_profiles" in body
        assert "missing_analysis" in body
        assert "duplicate_analysis" in body
        assert "outlier_analysis" in body
        assert "quality_insights" in body
        assert body["quality_score"]["score"] >= 0.0

    def test_post_data_quality_success(self, client, retail_dataset_id):
        resp = client.post("/api/data-quality", json={"dataset_id": retail_dataset_id})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "quality_score" in body

    def test_missing_dataset_id(self, client):
        resp = client.get("/api/data-quality")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "MISSING_DATASET_ID"

    def test_invalid_uuid(self, client):
        resp = client.get("/api/data-quality?dataset_id=not-a-uuid")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_DATASET_ID"

    def test_nonexistent_dataset(self, client):
        resp = client.get("/api/data-quality?dataset_id=00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "DATASET_NOT_FOUND"

    def test_post_not_json(self, client):
        resp = client.post("/api/data-quality", data="raw string", content_type="text/plain")
        assert resp.status_code == 415


class TestDataProfileEndpoint:
    def test_get_data_profile_success(self, client, retail_dataset_id):
        resp = client.get(f"/api/data-profile?dataset_id={retail_dataset_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "overview" in body
        assert "column_profiles" in body
        assert len(body["column_profiles"]) == 7


class TestBIKPIsEndpoint:
    def test_bi_kpis_auto_discovery(self, client, retail_dataset_id):
        resp = client.post("/api/bi/kpis", json={"dataset_id": retail_dataset_id})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "discovery" in body
        assert "kpis" in body
        assert "insights" in body

        kpis = body["kpis"]
        names = [k["metric_name"] for k in kpis]
        assert any("sales" in n.lower() for n in names)
        assert any("profit" in n.lower() for n in names)

    def test_bi_kpis_explicit_columns(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/kpis",
            json={
                "dataset_id": retail_dataset_id,
                "revenue_col": "sales",
                "profit_col": "profit",
                "order_id_col": "order_id",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        kpis = {k["metric_name"]: k for k in body["kpis"]}
        assert "Total sales" in kpis
        assert "Profit Margin" in kpis
        assert "Average Order Value (AOV)" in kpis

    def test_bi_kpis_invalid_column(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/kpis",
            json={"dataset_id": retail_dataset_id, "revenue_col": "nonexistent_col"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_COLUMN"


class TestBIGroupAnalysisEndpoint:
    def test_group_analysis_success(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/group-analysis",
            json={
                "dataset_id": retail_dataset_id,
                "group_col": "category",
                "measure_col": "sales",
                "aggregation": "sum",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["group_column"] == "category"
        assert body["measure_column"] == "sales"
        assert body["total_groups"] == 3
        assert len(body["records"]) > 0

    def test_group_analysis_missing_parameters(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/group-analysis",
            json={"dataset_id": retail_dataset_id, "measure_col": "sales"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "MISSING_GROUP_COL"

    def test_group_analysis_invalid_aggregation(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/group-analysis",
            json={
                "dataset_id": retail_dataset_id,
                "group_col": "category",
                "measure_col": "sales",
                "aggregation": "invalid_agg",
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_AGGREGATION"


class TestBITrendsEndpoint:
    def test_monthly_trends_success(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/trends",
            json={
                "dataset_id": retail_dataset_id,
                "date_col": "order_date",
                "measure_col": "sales",
                "granularity": "monthly",
                "aggregation": "sum",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["date_column"] == "order_date"
        assert body["granularity"] == "monthly"
        assert "labels" in body
        assert "values" in body
        assert len(body["labels"]) == 3  # Jan, Feb, Mar 2023

    def test_trends_invalid_granularity(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/trends",
            json={
                "dataset_id": retail_dataset_id,
                "date_col": "order_date",
                "measure_col": "sales",
                "granularity": "biweekly",
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_GRANULARITY"


class TestBIPeriodComparisonEndpoint:
    def test_period_comparison_success(self, client, retail_dataset_id):
        resp = client.post(
            "/api/bi/period-comparison",
            json={
                "dataset_id": retail_dataset_id,
                "date_col": "order_date",
                "measure_col": "sales",
                "granularity": "monthly",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["is_valid_comparison"] is True
        assert "current_period" in body
        assert "previous_period" in body
        assert "absolute_change" in body
        assert "percentage_change" in body
        assert "direction" in body
        assert "explanation" in body
