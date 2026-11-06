"""Mocked Supabase S3 adapter and owner-scoped file lifecycle tests."""

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


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.fail_put_key = None
        self.fail_after_write = False

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise MissingObjectError()
        return {}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body
        if Key == self.fail_put_key:
            if not self.fail_after_write:
                self.objects.pop((Bucket, Key), None)
            raise RuntimeError("simulated object-store failure")

    def get_object(self, Bucket, Key):
        try:
            content = self.objects[(Bucket, Key)]
        except KeyError:
            raise MissingObjectError() from None
        return {"Body": BytesIO(content)}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def _use_fake_supabase(monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr(config, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(config, "SUPABASE_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(
        config,
        "SUPABASE_S3_ENDPOINT",
        "https://project.supabase.co/storage/v1/s3",
    )
    monkeypatch.setattr(config, "SUPABASE_S3_REGION", "us-east-1")
    monkeypatch.setattr(config, "SUPABASE_S3_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setattr(
        config, "SUPABASE_S3_SECRET_ACCESS_KEY", "test-secret-key"
    )
    monkeypatch.setattr(storage, "_s3_client", client)
    return client


def test_supabase_dataset_storage_persists_loads_and_deletes_raw_and_cleaned_csvs(
    monkeypatch,
):
    client = _use_fake_supabase(monkeypatch)
    dataset_id = str(uuid.uuid4())
    raw = pd.DataFrame({"name": ["A", "A", "B"], "value": [1, 1, 2]})
    cleaned = raw.drop_duplicates()

    raw_path, cleaned_path = storage.persist_dataset(dataset_id, raw, cleaned)

    assert raw_path.startswith("supabase://test-bucket/csv-dashboard/datasets/")
    assert storage.load_raw_dataset(raw_path).equals(raw)
    assert storage.load_dataset(cleaned_path).equals(cleaned.reset_index(drop=True))
    assert len(client.objects) == 2
    staged = storage.stage_dataset_deletion(dataset_id)
    storage.remove_staged_dataset(staged)
    assert client.objects == {}
    storage.remove_staged_dataset(staged)
    assert client.objects == {}


def test_supabase_missing_dataset_and_report_objects_raise_file_not_found(monkeypatch):
    _use_fake_supabase(monkeypatch)
    with pytest.raises(FileNotFoundError):
        storage.load_dataset("supabase://test-bucket/csv-dashboard/datasets/missing.csv")
    with pytest.raises(FileNotFoundError):
        storage.load_report("supabase://test-bucket/csv-dashboard/reports/missing.pdf")


def test_supabase_partial_dataset_upload_is_rolled_back(monkeypatch):
    client = _use_fake_supabase(monkeypatch)
    dataset_id = str(uuid.uuid4())
    client.fail_put_key = f"csv-dashboard/datasets/{dataset_id}_cleaned.csv"
    client.fail_after_write = True

    with pytest.raises(RuntimeError, match="simulated object-store failure"):
        storage.persist_dataset(
            dataset_id,
            pd.DataFrame({"value": [1]}),
            pd.DataFrame({"value": [1]}),
        )
    assert client.objects == {}


def test_supabase_report_write_failure_is_rolled_back(monkeypatch):
    client = _use_fake_supabase(monkeypatch)
    report_id = str(uuid.uuid4())
    client.fail_put_key = f"csv-dashboard/reports/{report_id}.pdf"
    client.fail_after_write = True

    with pytest.raises(RuntimeError, match="simulated object-store failure"):
        storage.persist_report(report_id, b"%PDF test")
    assert client.objects == {}


def test_supabase_s3_client_uses_endpoint_credentials_region_and_path_style(
    monkeypatch,
):
    import boto3

    _use_fake_supabase(monkeypatch)
    monkeypatch.setattr(storage, "_s3_client", None)
    calls = {}

    def fake_boto3_client(service, **kwargs):
        calls["service"] = service
        calls.update(kwargs)
        return object()

    monkeypatch.setattr(boto3, "client", fake_boto3_client)
    storage._get_s3_client()

    assert calls["service"] == "s3"
    assert calls["endpoint_url"] == "https://project.supabase.co/storage/v1/s3"
    assert calls["region_name"] == "us-east-1"
    assert calls["aws_access_key_id"] == "test-access-key"
    assert calls["aws_secret_access_key"] == "test-secret-key"
    assert calls["config"].s3["addressing_style"] == "path"
    assert calls["config"].signature_version == "s3v4"


def test_supabase_upload_raw_cleaned_and_report_download_delete_respect_ownership(
    monkeypatch,
    client,
    secondary_client,
    duplicate_csv_bytes,
):
    s3_client = _use_fake_supabase(monkeypatch)
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

    report_path = storage.get_report_path(report_id)
    assert (config.SUPABASE_BUCKET_NAME, storage._s3_key(report_path)) in s3_client.objects
    deleted = client.delete(f"/api/datasets/{dataset_id}")
    assert deleted.status_code == 200
    assert s3_client.objects == {}
    assert client.get(f"/api/reports/{report_id}/download").status_code == 404


def test_missing_raw_object_returns_controlled_404_without_cleaned_fallback(
    monkeypatch, client, simple_csv_bytes
):
    s3_client = _use_fake_supabase(monkeypatch)
    uploaded = client.post(
        "/upload",
        data={"file": (BytesIO(simple_csv_bytes), "missing-raw.csv")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200
    dataset_id = uploaded.get_json()["dataset_id"]

    import app as application

    application.DATASETS.clear()
    application.RAW_DATASETS.clear()
    raw_path, _ = storage.get_dataset_paths(dataset_id)
    s3_client.delete_object(
        Bucket=config.SUPABASE_BUCKET_NAME,
        Key=storage._s3_key(raw_path),
    )

    raw_download = client.get(f"/download/{dataset_id}/raw")
    assert raw_download.status_code == 404
    assert raw_download.get_json()["error"]["code"] == "RAW_DATASET_FILE_MISSING"
    assert client.get(f"/download/{dataset_id}").status_code == 200
