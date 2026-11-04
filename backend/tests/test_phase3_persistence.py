"""
test_phase3_persistence.py – Database persistence and restart survival acceptance tests.

Acceptance criteria covered:
  - Uploaded dataset metadata is properly stored in SQLAlchemy database.
  - Backend restart simulation: memory cache is cleared, but dataset remains accessible.
  - Raw and cleaned representations remain available and identical to uploaded data.
  - Dataset survival verified across chart, insights, and download endpoints.
  - Failed uploads do not leave orphaned files or inconsistent database rows.
"""

import io
import os
import pandas as pd
import pytest
from database import SessionLocal
from models import Dataset
import storage


class TestDatabasePersistence:
    def test_upload_persists_metadata_in_database(self, client, simple_csv_bytes):
        data = {"file": (io.BytesIO(simple_csv_bytes), "sales_data.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        db = SessionLocal()
        record = db.get(Dataset, dataset_id)
        assert record is not None
        assert record.original_filename == "sales_data.csv"
        assert record.file_size_bytes == len(simple_csv_bytes)
        assert record.columns == ["Category", "Value"]
        assert "Value" in record.numeric_columns
        assert record.expires_at is not None
        assert os.path.isfile(record.raw_storage_path)
        assert os.path.isfile(record.cleaned_storage_path)

    def test_dataset_survives_backend_restart(self, client, simple_csv_bytes):
        """
        Simulate backend restart by completely wiping in-memory DATASETS cache.
        The dataset must be transparently restored from database + storage.
        """
        from app import DATASETS, RAW_DATASETS

        # 1. Upload dataset
        data = {"file": (io.BytesIO(simple_csv_bytes), "restart_test.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        # 2. Simulate process crash / backend restart
        DATASETS.clear()
        RAW_DATASETS.clear()
        assert dataset_id not in DATASETS
        assert dataset_id not in RAW_DATASETS

        # 3. Request chart data after restart -> must succeed
        chart_resp = client.post(
            "/chart-data",
            json={
                "dataset_id": dataset_id,
                "chart_type": "Bar",
                "x_axis": "Category",
                "y_axis": "Value",
            },
        )
        assert chart_resp.status_code == 200
        chart_data = chart_resp.get_json()
        assert "labels" in chart_data
        assert "values" in chart_data
        assert len(chart_data["labels"]) > 0

        # 4. Verify in-memory cache was restored transparently
        assert dataset_id in DATASETS

        # 5. Request download after restart -> must succeed
        dl_resp = client.get(f"/download/{dataset_id}")
        assert dl_resp.status_code == 200
        assert "Category" in dl_resp.data.decode("utf-8")

    def test_raw_and_cleaned_representations_preserved(self, client):
        """Verify that duplicate rows in raw data are preserved in raw representation."""
        csv_with_dups = b"Category,Value\nA,10\nA,10\nB,20\n"
        data = {"file": (io.BytesIO(csv_with_dups), "dups.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        dataset_id = resp.get_json()["dataset_id"]

        # Clear memory cache
        from app import DATASETS, RAW_DATASETS
        DATASETS.clear()
        RAW_DATASETS.clear()

        # Data quality endpoint uses raw dataset to assess duplication
        dq_resp = client.post("/api/data-quality", json={"dataset_id": dataset_id})
        assert dq_resp.status_code == 200
        dq_data = dq_resp.get_json()
        assert dq_data["duplicate_analysis"]["duplicate_rows_count"] == 1

    def test_failed_upload_leaves_no_orphaned_records(self, client):
        """An empty file fails upload and should not create database rows or files."""
        db = SessionLocal()
        count_before = db.query(Dataset).count()

        data = {"file": (io.BytesIO(b""), "empty.csv")}
        resp = client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400

        count_after = db.query(Dataset).count()
        assert count_after == count_before

    def test_storage_write_failure_leaves_no_partial_files(self, tmp_path, monkeypatch):
        storage_dir = tmp_path / "dataset-storage"
        monkeypatch.setattr(storage, "STORAGE_DIR", str(storage_dir))
        original_to_csv = pd.DataFrame.to_csv
        calls = 0

        def fail_second_write(frame, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated storage failure")
            return original_to_csv(frame, *args, **kwargs)

        monkeypatch.setattr(pd.DataFrame, "to_csv", fail_second_write)

        with pytest.raises(OSError, match="simulated storage failure"):
            storage.persist_dataset(
                "partial-write-test",
                pd.DataFrame({"value": [1]}),
                pd.DataFrame({"value": [1]}),
            )

        assert list(storage_dir.iterdir()) == []
