"""Security regression checks added after the read-only Phase 3 audit."""

import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import storage
from auth import generate_auth_token, verify_auth_token
from database import SessionLocal
from dataset_service import cleanup_expired_datasets
from models import Dataset


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("POST", "/upload", None),
        ("POST", "/chart-data", {"dataset_id": str(uuid.uuid4())}),
        ("POST", "/insights", {"dataset_id": str(uuid.uuid4())}),
        ("POST", "/ask", {"dataset_id": str(uuid.uuid4())}),
        ("GET", f"/download/{uuid.uuid4()}", None),
        ("GET", f"/api/data-quality?dataset_id={uuid.uuid4()}", None),
        ("POST", "/api/data-quality", {"dataset_id": str(uuid.uuid4())}),
        ("GET", f"/api/data-profile?dataset_id={uuid.uuid4()}", None),
        ("POST", "/api/data-profile", {"dataset_id": str(uuid.uuid4())}),
        ("POST", "/api/bi/kpis", {"dataset_id": str(uuid.uuid4())}),
        ("POST", "/api/bi/group-analysis", {"dataset_id": str(uuid.uuid4())}),
        ("POST", "/api/bi/trends", {"dataset_id": str(uuid.uuid4())}),
        ("POST", "/api/bi/period-comparison", {"dataset_id": str(uuid.uuid4())}),
    ],
)
def test_all_analytical_dataset_routes_require_authentication(
    unauth_client, method, path, json_body
):
    response = unauth_client.open(path, method=method, json=json_body)

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_signed_session_token_is_rejected():
    token = generate_auth_token("expired-audit-user")

    assert verify_auth_token(token, max_age=-1) is None


def test_global_dataset_cleanup_requires_authentication(unauth_client):
    response = unauth_client.post("/api/datasets/cleanup")

    assert response.status_code == 401


def test_cleanup_preserves_metadata_when_dataset_file_deletion_fails(
    client, simple_csv_bytes, monkeypatch
):
    upload_response = client.post(
        "/upload",
        data={"file": (io.BytesIO(simple_csv_bytes), "cleanup-delete-failure.csv")},
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    dataset_id = upload_response.get_json()["dataset_id"]

    db = SessionLocal()
    dataset = db.get(Dataset, dataset_id)
    dataset.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    raw_path = dataset.raw_storage_path
    cleaned_path = dataset.cleaned_storage_path

    original_remove = storage.os.remove

    def reject_dataset_file(path):
        if path in {f"{raw_path}.deleting", f"{cleaned_path}.deleting"}:
            raise PermissionError("simulated storage deletion failure")
        return original_remove(path)

    monkeypatch.setattr(storage.os, "remove", reject_dataset_file)

    with pytest.raises(RuntimeError, match="retry is pending"):
        cleanup_expired_datasets()

    db.expire_all()
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.deletion_pending is True
    assert not os.path.exists(raw_path)
    assert os.path.exists(f"{raw_path}.deleting")
