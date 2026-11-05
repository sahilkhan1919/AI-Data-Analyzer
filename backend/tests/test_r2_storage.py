"""Cloudflare R2 adapter and owner-scoped file lifecycle tests."""

from io import BytesIO
import uuid

import pandas as pd
import pytest

import config
import storage


class MissingObjectError(Exception):
    response = {
        "Error": {"Code": "NoSuchKey"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


class FakeR2Client:
    def __init__(self):
        self.objects = {}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise MissingObjectError()
        return {}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body

    def copy_object(self, Bucket, Key, CopySource, **kwargs):
        self.objects[(Bucket, Key)] = self.objects[
            (CopySource["Bucket"], CopySource["Key"])
        ]

    def get_object(self, Bucket, Key):
        try:
            content = self.objects[(Bucket, Key)]
        except KeyError:
            raise MissingObjectError() from None
        return {"Body": BytesIO(content)}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def _use_fake_r2(monkeypatch):
    client = FakeR2Client()
    monkeypatch.setattr(config, "STORAGE_BACKEND", "r2")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(config, "R2_PREFIX", "test-prefix")
    monkeypatch.setattr(storage, "_r2_client", client)
    return client


def test_r2_dataset_storage_persists_loads_and_deletes_raw_and_cleaned_csvs(monkeypatch):
    client = _use_fake_r2(monkeypatch)
    dataset_id = str(uuid.uuid4())
    raw = pd.DataFrame({"name": ["A", "A", "B"], "value": [1, 1, 2]})
    cleaned = raw.drop_duplicates()

    raw_path, cleaned_path = storage.persist_dataset(dataset_id, raw, cleaned)

    assert raw_path.startswith("r2://test-bucket/test-prefix/datasets/")
    assert storage.load_raw_dataset(raw_path).equals(raw)
    assert storage.load_dataset(cleaned_path).equals(cleaned.reset_index(drop=True))
    assert len(client.objects) == 2
    staged = storage.stage_dataset_deletion(dataset_id)
    storage.remove_staged_dataset(staged)
    assert client.objects == {}
    storage.remove_staged_dataset(staged)
    assert client.objects == {}


def test_r2_missing_dataset_and_report_objects_raise_file_not_found(monkeypatch):
    _use_fake_r2(monkeypatch)
    with pytest.raises(FileNotFoundError):
        storage.load_dataset("r2://test-bucket/test-prefix/datasets/missing.csv")
    with pytest.raises(FileNotFoundError):
        storage.load_report("r2://test-bucket/test-prefix/reports/missing.pdf")


def test_r2_partial_dataset_upload_is_rolled_back(monkeypatch):
    class FailingCopyClient(FakeR2Client):
        def copy_object(self, Bucket, Key, CopySource, **kwargs):
            if Key.endswith("_cleaned.csv"):
                raise RuntimeError("simulated object-store failure")
            super().copy_object(Bucket, Key, CopySource, **kwargs)

    client = FailingCopyClient()
    monkeypatch.setattr(config, "STORAGE_BACKEND", "r2")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(config, "R2_PREFIX", "test-prefix")
    monkeypatch.setattr(storage, "_r2_client", client)

    with pytest.raises(RuntimeError, match="simulated object-store failure"):
        storage.persist_dataset(
            str(uuid.uuid4()),
            pd.DataFrame({"value": [1]}),
            pd.DataFrame({"value": [1]}),
        )
    assert client.objects == {}


def test_r2_upload_raw_cleaned_and_report_download_delete_respect_ownership(
    monkeypatch,
    client,
    secondary_client,
    duplicate_csv_bytes,
):
    r2_client = _use_fake_r2(monkeypatch)
    uploaded = client.post(
        "/upload",
        data={"file": (BytesIO(duplicate_csv_bytes), "duplicates.csv")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200
    dataset_id = uploaded.get_json()["dataset_id"]

    import app as application

    application.DATASETS.clear()
    application.RAW_DATASETS.clear()
    raw_download = client.get(f"/download/{dataset_id}/raw")
    cleaned_download = client.get(f"/download/{dataset_id}")
    assert raw_download.status_code == cleaned_download.status_code == 200
    assert raw_download.data.count(b"A,10") == 2
    assert cleaned_download.data.count(b"A,10") == 1
    assert secondary_client.get(f"/download/{dataset_id}/raw").status_code == 403

    report_response = client.post("/api/reports", json={"dataset_id": dataset_id})
    assert report_response.status_code == 201
    report_id = report_response.get_json()["report_id"]
    report = client.get(f"/api/reports/{report_id}/download")
    assert report.status_code == 200
    assert report.mimetype == "application/pdf"
    assert report.data.startswith(b"%PDF")
    assert secondary_client.get(f"/api/reports/{report_id}/download").status_code == 404

    monkeypatch.setattr(config, "R2_PREFIX", "changed-prefix")
    deleted = client.delete(f"/api/datasets/{dataset_id}")
    assert deleted.status_code == 200
    assert r2_client.objects == {}
    assert client.get(f"/api/reports/{report_id}/download").status_code == 404
