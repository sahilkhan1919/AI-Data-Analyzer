import io
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session as SQLAlchemySession

import config
import storage
from auth import generate_csrf_token
from database import SessionLocal
from dataset_service import cleanup_expired_datasets
from models import Dataset, LoginRateLimit


def _upload_expired_dataset(client, simple_csv_bytes):
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(simple_csv_bytes), "expiring.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    dataset_id = response.get_json()["dataset_id"]
    db = SessionLocal()
    dataset = db.get(Dataset, dataset_id)
    dataset.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    return dataset_id, dataset.raw_storage_path, dataset.cleaned_storage_path


def test_production_secret_validation_rejects_missing_and_weak_values():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_secret_key(None, "production")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_secret_key(None, "development")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_secret_key("short", "production")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_secret_key("short", "development")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.validate_secret_key("A" * 64, "production")

    strong_secret = secrets.token_urlsafe(48)
    assert config.validate_secret_key(strong_secret, "production") == strong_secret
    assert config.validate_secret_key(strong_secret, "development") == strong_secret


def test_development_startup_fails_with_missing_secret():
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["FLASK_ENV"] = "development"
    env["SECRET_KEY"] = ""
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Development requires SECRET_KEY" in result.stderr


def test_application_startup_fails_with_missing_production_secret():
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["FLASK_ENV"] = "production"
    env["SECRET_KEY"] = ""
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Production requires SECRET_KEY" in result.stderr


def test_production_startup_accepts_valid_secret_and_explicit_deployment_settings(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "FLASK_ENV": "production",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_URI": "postgresql+psycopg://test:test@127.0.0.1:5432/not_connected",
            "ALLOWED_ORIGINS": "https://dashboard.example.test",
            "UPLOAD_FOLDER": str(tmp_path / "durable-volume"),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app, config; print(config.FLASK_ENV, config.SESSION_COOKIE_SECURE)",
        ],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "production True" in result.stdout


def test_render_manifest_declares_production_configuration_without_inline_secrets():
    repository_root = Path(__file__).resolve().parents[2]
    manifest = (repository_root / "render.yaml").read_text()

    assert "value: production" in manifest
    assert "key: SECRET_KEY\n        generateValue: true" in manifest
    assert "key: ALLOWED_ORIGINS\n        sync: false" in manifest
    assert "key: DATABASE_URI\n        sync: false" in manifest
    assert "mountPath: /var/data" in manifest
    assert "value: /var/data" in manifest


def test_cleanup_requires_admin_token_and_rejects_normal_users(
    unauth_client, client, monkeypatch
):
    monkeypatch.setattr(config, "DATASET_CLEANUP_TOKEN", "a-test-admin-token")

    assert unauth_client.post("/api/datasets/cleanup").status_code == 401
    assert client.post("/api/datasets/cleanup").status_code == 403

    wrong_token = unauth_client.post(
        "/api/datasets/cleanup",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert wrong_token.status_code == 403

    admin_response = unauth_client.post(
        "/api/datasets/cleanup",
        headers={"Authorization": "Bearer a-test-admin-token"},
    )
    assert admin_response.status_code == 200
    assert admin_response.get_json() == {"cleaned_datasets": 0}


def test_cookie_mutations_require_csrf_token_and_trusted_origin(client):
    missing_token = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": ""},
    )
    assert missing_token.status_code == 403
    assert missing_token.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    invalid_token = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": "invalid"},
    )
    assert invalid_token.status_code == 403

    cookie = client.get_cookie(config.SESSION_COOKIE_NAME)
    valid_token = generate_csrf_token(cookie.value)
    untrusted_origin = client.post(
        "/api/auth/logout",
        headers={
            "Origin": "https://untrusted.example",
            "X-CSRF-Token": valid_token,
        },
    )
    assert untrusted_origin.status_code == 403
    assert untrusted_origin.get_json()["error"]["code"] == "CSRF_ORIGIN_INVALID"

    missing_origin = client.post(
        "/api/auth/logout",
        headers={"Origin": "", "X-CSRF-Token": valid_token},
    )
    assert missing_origin.status_code == 403

    valid_request = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": valid_token},
    )
    assert valid_request.status_code == 200


def test_failed_staged_file_removal_keeps_retryable_metadata(
    client, simple_csv_bytes, monkeypatch
):
    dataset_id, raw_path, cleaned_path = _upload_expired_dataset(client, simple_csv_bytes)
    original_remove = storage.os.remove

    def fail_cleaned_file(path):
        if path == f"{cleaned_path}.deleting":
            raise PermissionError("simulated partial deletion failure")
        return original_remove(path)

    monkeypatch.setattr(storage.os, "remove", fail_cleaned_file)
    with pytest.raises(RuntimeError, match="retry is pending"):
        cleanup_expired_datasets()

    db = SessionLocal()
    db.expire_all()
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.deletion_pending is True
    assert not os.path.exists(raw_path)
    assert os.path.exists(f"{cleaned_path}.deleting")

    monkeypatch.setattr(storage.os, "remove", original_remove)
    assert cleanup_expired_datasets() == 1
    assert db.get(Dataset, dataset_id) is None
    assert not os.path.exists(f"{cleaned_path}.deleting")


def test_storage_permission_error_is_not_treated_as_a_missing_file(
    client, simple_csv_bytes, monkeypatch
):
    dataset_id, raw_path, _ = _upload_expired_dataset(client, simple_csv_bytes)
    original_lstat = storage.os.lstat

    def deny_raw_file_stat(path, *args, **kwargs):
        if path == raw_path:
            raise PermissionError("simulated inaccessible storage directory")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(storage.os, "lstat", deny_raw_file_stat)
    with pytest.raises(RuntimeError, match="retry is pending"):
        cleanup_expired_datasets()

    db = SessionLocal()
    db.expire_all()
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.deletion_pending is True
    assert os.path.isfile(raw_path)

    monkeypatch.setattr(storage.os, "lstat", original_lstat)
    assert cleanup_expired_datasets() == 1
    assert db.get(Dataset, dataset_id) is None


def test_missing_storage_file_does_not_prevent_expired_metadata_cleanup(
    client, simple_csv_bytes
):
    dataset_id, raw_path, cleaned_path = _upload_expired_dataset(client, simple_csv_bytes)
    os.remove(raw_path)

    assert cleanup_expired_datasets() == 1
    db = SessionLocal()
    assert db.get(Dataset, dataset_id) is None
    assert not os.path.exists(cleaned_path)


def test_database_commit_failure_leaves_deletion_retryable(
    client, simple_csv_bytes, monkeypatch
):
    dataset_id, raw_path, cleaned_path = _upload_expired_dataset(client, simple_csv_bytes)
    original_commit = SQLAlchemySession.commit
    calls = 0

    def fail_metadata_delete_commit(session):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated database commit failure")
        return original_commit(session)

    monkeypatch.setattr(SQLAlchemySession, "commit", fail_metadata_delete_commit)
    with pytest.raises(RuntimeError, match="retry is pending"):
        cleanup_expired_datasets()
    monkeypatch.setattr(SQLAlchemySession, "commit", original_commit)

    db = SessionLocal()
    db.expire_all()
    dataset = db.get(Dataset, dataset_id)
    assert dataset is not None
    assert dataset.deletion_pending is True
    assert not os.path.exists(raw_path)
    assert not os.path.exists(cleaned_path)

    assert cleanup_expired_datasets() == 1
    assert db.get(Dataset, dataset_id) is None


def test_login_rate_limit_returns_429_and_recovers_after_window(
    client, default_user, monkeypatch
):
    monkeypatch.setattr(config, "LOGIN_RATE_LIMIT_ATTEMPTS", 2)
    monkeypatch.setattr(config, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
    login_url = "/api/auth/login"
    payload = {"email": default_user.email, "password": "incorrect"}

    assert client.post(login_url, json=payload).status_code == 401
    assert client.post(login_url, json=payload).status_code == 401
    limited_response = client.post(login_url, json=payload)
    assert limited_response.status_code == 429
    assert limited_response.get_json()["error"]["code"] == "RATE_LIMITED"
    assert int(limited_response.headers["Retry-After"]) > 0

    db = SessionLocal()
    bucket = db.query(LoginRateLimit).one()
    bucket.window_started_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    db.commit()

    recovered = client.post(
        login_url,
        json={"email": default_user.email, "password": "Password123!"},
    )
    assert recovered.status_code == 200
    assert db.query(LoginRateLimit).count() == 0


def test_alembic_upgrade_creates_and_reconciles_schema(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "migration-test.sqlite"
    env = os.environ.copy()
    env["DATABASE_URI"] = f"sqlite:///{database_path}"

    for _ in range(2):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    from sqlalchemy import create_engine

    engine = create_engine(env["DATABASE_URI"])
    table_names = set(inspect(engine).get_table_names())
    assert {
        "users",
        "datasets",
        "revoked_sessions",
        "login_rate_limits",
        "business_reports",
        "alembic_version",
    } <= table_names
    dataset_columns = {column["name"] for column in inspect(engine).get_columns("datasets")}
    assert "deletion_pending" in dataset_columns
    engine.dispose()
