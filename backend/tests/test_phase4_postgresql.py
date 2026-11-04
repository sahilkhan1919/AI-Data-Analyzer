"""Optional end-to-end integration against an explicitly supplied disposable PostgreSQL DB."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from flask.testing import FlaskClient


POSTGRES_URI = os.environ.get("TEST_POSTGRES_DATABASE_URI")


@pytest.mark.skipif(
    not POSTGRES_URI,
    reason="Set TEST_POSTGRES_DATABASE_URI to an isolated disposable PostgreSQL database.",
)
def test_phase4_workflows_on_postgresql(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    migration_env = os.environ.copy()
    migration_env["DATABASE_URI"] = POSTGRES_URI
    migration = subprocess.run(
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
        env=migration_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert migration.returncode == 0, "PostgreSQL Alembic upgrade failed."

    import app as application
    import config
    import storage
    from auth import generate_auth_token, hash_password
    from database import SessionLocal, init_app_db
    from models import User

    class ExplicitCsrfClient(FlaskClient):
        def open(self, *args, **kwargs):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Origin", "http://localhost:5173")
            kwargs["headers"] = headers
            return super().open(*args, **kwargs)

    previous_storage_dir = storage.STORAGE_DIR
    storage.STORAGE_DIR = str(tmp_path / "datasets")
    os.makedirs(storage.STORAGE_DIR, exist_ok=True)
    application.app.test_client_class = ExplicitCsrfClient
    application.app.config.update(TESTING=True)
    engine = init_app_db(application.app, database_uri=POSTGRES_URI)
    application.DATASETS.clear()
    application.RAW_DATASETS.clear()
    try:
        db = SessionLocal()
        user = User(email="phase4-postgres@example.test", password_hash=hash_password("safe-test-password"))
        db.add(user)
        db.commit()
        user_id = user.id
        db.close()

        client = application.app.test_client()
        session_token = generate_auth_token(user_id)
        client.set_cookie(config.SESSION_COOKIE_NAME, session_token)
        from auth import generate_csrf_token

        headers = {
            "Origin": "http://localhost:5173",
            "X-CSRF-Token": generate_csrf_token(session_token),
        }

        login_failure = client.post(
            "/api/auth/login",
            json={"email": "phase4-postgres@example.test", "password": "wrong-password"},
            headers=headers,
        )
        assert login_failure.status_code == 401

        data = pd.DataFrame(
            {
                "Date": pd.date_range("2025-01-01", periods=12, freq="MS"),
                "Region": ["North" if index % 2 == 0 else "South" for index in range(12)],
                "Revenue": [100 + index * 10 for index in range(12)],
                "Profit": [20 + index * 2 for index in range(12)],
            }
        )
        uploaded = client.post(
            "/upload",
            data={"file": (io.BytesIO(data.to_csv(index=False).encode()), "postgres.csv")},
            content_type="multipart/form-data",
            headers=headers,
        )
        assert uploaded.status_code == 200
        dataset_id = uploaded.get_json()["dataset_id"]

        application.DATASETS.clear()
        application.RAW_DATASETS.clear()
        forecast = client.post(
            "/api/analytics/forecast",
            json={
                "dataset_id": dataset_id,
                "date_col": "Date",
                "measure_col": "Revenue",
                "horizon": 2,
            },
            headers=headers,
        )
        assert forecast.status_code == 200
        assert len(forecast.get_json()["forecast"]) == 2

        report = client.post("/api/reports", json={"dataset_id": dataset_id}, headers=headers)
        assert report.status_code == 201
        report_id = report.get_json()["report_id"]
        assert client.get("/api/reports").get_json()["reports"][0]["report_id"] == report_id
        assert client.get(f"/api/reports/{report_id}/download").data.startswith(b"%PDF")

        deleted = client.delete(f"/api/datasets/{dataset_id}", headers=headers)
        assert deleted.status_code == 200
        assert client.get("/api/reports").get_json()["reports"] == []
    finally:
        SessionLocal.remove()
        engine.dispose()
        storage.STORAGE_DIR = previous_storage_dir
        application.DATASETS.clear()
        application.RAW_DATASETS.clear()
