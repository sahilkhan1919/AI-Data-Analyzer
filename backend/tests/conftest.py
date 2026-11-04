"""
conftest.py – pytest fixtures for the CSV Dashboard backend test suite (Phase 3).

All fixtures use Flask's built-in test client with isolated database and storage.
The client fixture is authenticated by default to ensure all Phase 1 and Phase 2 tests
continue to pass seamlessly, while unauth_client and secondary_client test Phase 3 isolation.
"""

import io
import os
import uuid
import pytest
import pandas as pd
from flask.testing import FlaskClient


class CsrfTestClient(FlaskClient):
    """Provide browser-equivalent trusted-origin and CSRF headers by default."""

    def open(self, *args, **kwargs):
        method = (kwargs.get("method") or "GET").upper()
        headers = dict(kwargs.get("headers") or {})
        if method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            headers.setdefault("Origin", "http://localhost:5173")
            from config import SESSION_COOKIE_NAME
            from auth import generate_csrf_token

            cookie = self.get_cookie(SESSION_COOKIE_NAME)
            if cookie and "X-CSRF-Token" not in headers:
                headers["X-CSRF-Token"] = generate_csrf_token(cookie.value)
        kwargs["headers"] = headers
        return super().open(*args, **kwargs)


# ---------------------------------------------------------------------------
# Application fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """
    Create and configure a fresh Flask application for each test with isolated DB.
    """
    import app as flask_app_module
    from app import DATASETS, RAW_DATASETS
    from database import init_app_db, SessionLocal
    import storage

    flask_app_module.app.test_client_class = CsrfTestClient

    # Set up isolated test database and storage directory
    test_db_path = os.path.join(str(tmp_path), "test_dashboard.db")
    test_db_uri = f"sqlite:///{test_db_path}"
    test_upload_dir = os.path.join(str(tmp_path), "uploads")
    os.makedirs(test_upload_dir, exist_ok=True)

    storage.STORAGE_DIR = os.path.join(test_upload_dir, "datasets")
    os.makedirs(storage.STORAGE_DIR, exist_ok=True)

    init_app_db(flask_app_module.app, database_uri=test_db_uri)

    # Isolate in-memory state
    DATASETS.clear()
    RAW_DATASETS.clear()

    flask_app_module.app.config.update(
        {
            "TESTING": True,
            "MAX_CONTENT_LENGTH": 10 * 1024 * 1024,  # 10 MB
            "DATABASE_URI": test_db_uri,
            "UPLOAD_FOLDER": test_upload_dir,
        }
    )
    yield flask_app_module.app

    # Cleanup after test
    DATASETS.clear()
    RAW_DATASETS.clear()
    SessionLocal.remove()


@pytest.fixture()
def default_user(app):
    """Create default test user for standard test client."""
    from database import SessionLocal
    from models import User
    from auth import hash_password

    db = SessionLocal()
    user = User(
        email="test_user@example.com",
        password_hash=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(autouse=True)
def _auto_authenticate_client(request, default_user):
    """Automatically authenticate any standard client fixture."""
    if "client" in request.fixturenames:
        test_client = request.getfixturevalue("client")
        from auth import generate_auth_token
        import config
        token = generate_auth_token(default_user.id)
        test_client.set_cookie(config.SESSION_COOKIE_NAME, token)


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def unauth_client(app):
    """Unauthenticated client for testing authorization gates."""
    return app.test_client()


@pytest.fixture()
def secondary_user(app):
    """Second user for multi-tenant isolation testing."""
    from database import SessionLocal
    from models import User
    from auth import hash_password

    db = SessionLocal()
    user = User(
        email="secondary_user@example.com",
        password_hash=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def secondary_client(app, secondary_user):
    """Test client authenticated as secondary_user."""
    test_client = app.test_client()
    from auth import generate_auth_token
    import config

    token = generate_auth_token(secondary_user.id)
    test_client.set_cookie(config.SESSION_COOKIE_NAME, token)
    return test_client


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def simple_csv_bytes():
    """Minimal valid CSV content as bytes."""
    return b"Category,Value\nA,10\nB,20\nC,30\nA,5\nB,15\n"


@pytest.fixture()
def simple_csv_file(simple_csv_bytes):
    """BytesIO wrapping a minimal CSV."""
    return io.BytesIO(simple_csv_bytes)


@pytest.fixture()
def duplicate_csv_bytes():
    """CSV with duplicate rows."""
    return b"Category,Value\nA,10\nA,10\nB,20\nB,20\nC,30\n"


@pytest.fixture()
def missing_values_csv_bytes():
    """CSV with missing values in numeric and text columns."""
    return b"Name,Score\nAlice,90\nBob,\nCharlie,85\n,70\n"


@pytest.fixture()
def simple_xlsx_bytes():
    """Minimal XLSX file as bytes (generated in-memory via openpyxl)."""
    df = pd.DataFrame({"Product": ["A", "B", "C"], "Sales": [100, 200, 300]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.read()


@pytest.fixture()
def large_csv_bytes():
    """CSV that exceeds the 10 MB limit."""
    header = b"col1,col2,col3\n"
    row = b"A" * 100 + b",B" * 2 + b"\n"
    return header + row * (11 * 1024 * 1024 // len(row) + 1)


@pytest.fixture()
def malformed_csv_bytes():
    """Content that looks like a CSV but cannot be parsed usefully."""
    return b"\x00\x01\x02\x03\xff\xfe"  # binary garbage


@pytest.fixture()
def empty_csv_bytes():
    """Completely empty file."""
    return b""


@pytest.fixture()
def headers_only_csv_bytes():
    """CSV with headers but no data rows."""
    return b"Category,Value\n"


@pytest.fixture()
def unusual_text_csv_bytes():
    """CSV with unusual but valid text values."""
    return (
        b"Name,Notes\n"
        b'"O\'Brien","Value with, comma"\n'
        b"UTF8\xc3\xa9,caf\xc3\xa9\n"
    )


# ---------------------------------------------------------------------------
# Uploaded-dataset fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def uploaded_dataset_id(client, simple_csv_bytes):
    """Upload a simple CSV and return the dataset_id."""
    data = {"file": (io.BytesIO(simple_csv_bytes), "test.csv")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, f"Upload failed: {resp.get_data(as_text=True)}"
    return resp.get_json()["dataset_id"]


@pytest.fixture()
def uploaded_xlsx_dataset_id(client, simple_xlsx_bytes):
    """Upload a simple XLSX and return the dataset_id."""
    data = {"file": (io.BytesIO(simple_xlsx_bytes), "test.xlsx")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, f"XLSX upload failed: {resp.get_data(as_text=True)}"
    return resp.get_json()["dataset_id"]
