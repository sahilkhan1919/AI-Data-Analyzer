"""
test_phase3_isolation_and_lifecycle.py – Multi-tenant isolation and dataset lifecycle tests.

Acceptance criteria covered:
  - User A uploads dataset -> User B cannot access or download it (403 Forbidden).
  - Datasets marked as expired cannot be queried (404 DATASET_EXPIRED).
  - Background/admin cleanup deletes expired files and database rows.
  - Active (non-expired) datasets are never affected by cleanup.
  - Missing file on server produces a controlled error rather than an unhandled traceback.
"""

from datetime import datetime, timedelta, timezone
import io
import os
import pytest
from database import SessionLocal
from dataset_service import cleanup_expired_datasets
from models import Dataset
from storage import delete_dataset_storage


class TestMultiTenantIsolation:
    def test_user_cannot_access_another_users_chart_data(self, client, secondary_client, simple_csv_bytes):
        # User A uploads dataset
        data = {"file": (io.BytesIO(simple_csv_bytes), "user_a.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        # User B attempts to access User A's dataset
        resp_b = secondary_client.post(
            "/chart-data",
            json={
                "dataset_id": dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert resp_b.status_code == 403
        data_b = resp_b.get_json()
        assert data_b["error"]["code"] == "FORBIDDEN"

    def test_user_cannot_download_another_users_dataset(self, client, secondary_client, simple_csv_bytes):
        # User A uploads dataset
        data = {"file": (io.BytesIO(simple_csv_bytes), "user_a.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        # User B attempts to download User A's dataset
        resp_b = secondary_client.get(f"/download/{dataset_id}")
        assert resp_b.status_code == 403
        assert resp_b.get_json()["error"]["code"] == "FORBIDDEN"

    def test_user_cannot_run_analytics_on_another_users_dataset(self, client, secondary_client, simple_csv_bytes):
        # User A uploads dataset
        data = {"file": (io.BytesIO(simple_csv_bytes), "user_a.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        # User B attempts data-quality report
        resp_b = secondary_client.post("/api/data-quality", json={"dataset_id": dataset_id})
        assert resp_b.status_code == 403
        assert resp_b.get_json()["error"]["code"] == "FORBIDDEN"


class TestDatasetLifecycleAndExpiration:
    def test_expired_dataset_becomes_inaccessible(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "expiring.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        # Evict memory cache and set expires_at in the past
        from app import DATASETS, RAW_DATASETS
        DATASETS.clear()
        RAW_DATASETS.clear()

        db = SessionLocal()
        record = db.get(Dataset, dataset_id)
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        # Query should now return 404 DATASET_EXPIRED
        chart_resp = client.post(
            "/chart-data",
            json={
                "dataset_id": dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert chart_resp.status_code == 404
        assert chart_resp.get_json()["error"]["code"] == "DATASET_EXPIRED"

    def test_cleanup_removes_expired_datasets_and_preserves_active(self, client, simple_csv_bytes):
        # 1. Upload two datasets
        d1 = client.post("/upload", data={"file": (io.BytesIO(simple_csv_bytes), "d1.csv")}, content_type="multipart/form-data")
        d2 = client.post("/upload", data={"file": (io.BytesIO(simple_csv_bytes), "d2.csv")}, content_type="multipart/form-data")
        id1 = d1.get_json()["dataset_id"]
        id2 = d2.get_json()["dataset_id"]

        db = SessionLocal()
        r1 = db.get(Dataset, id1)
        r2 = db.get(Dataset, id2)
        raw1, clean1 = r1.raw_storage_path, r1.cleaned_storage_path
        raw2, clean2 = r2.raw_storage_path, r2.cleaned_storage_path

        # Expire dataset 1 only
        r1.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()

        # Run cleanup
        cleaned_count = cleanup_expired_datasets()
        assert cleaned_count >= 1

        # Confirm dataset 1 is deleted from DB and disk
        assert db.get(Dataset, id1) is None
        assert not os.path.isfile(raw1)
        assert not os.path.isfile(clean1)

        # Confirm dataset 2 is intact in DB and disk
        assert db.get(Dataset, id2) is not None
        assert os.path.isfile(raw2)
        assert os.path.isfile(clean2)

    def test_missing_stored_file_returns_controlled_error(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "missing_file_test.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        from app import DATASETS, RAW_DATASETS
        DATASETS.clear()
        RAW_DATASETS.clear()

        # Manually delete the storage file to simulate filesystem corruption
        db = SessionLocal()
        record = db.get(Dataset, dataset_id)
        if os.path.isfile(record.cleaned_storage_path):
            os.remove(record.cleaned_storage_path)

        # Accessing dataset must produce structured error, not crash with 500 traceback
        chart_resp = client.post(
            "/chart-data",
            json={
                "dataset_id": dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert chart_resp.status_code in (404, 500)
        data = chart_resp.get_json()
        assert "error" in data
        assert "code" in data["error"]
        assert "Traceback" not in chart_resp.get_data(as_text=True)
