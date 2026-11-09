"""
test_phase3_auth.py – Comprehensive backend authentication and authorization tests.

Acceptance criteria covered:
  - Registration succeeds with valid input.
  - Duplicate account registration is rejected (409 Conflict).
  - Weak passwords and invalid emails are rejected (400 Bad Request).
  - Invalid credentials on login are rejected (401 Unauthorized).
  - Passwords are encrypted as secure hashes and never stored as plaintext.
  - Unauthenticated users cannot access protected APIs (401 Unauthorized).
  - Authenticated users can retrieve their profile (/api/auth/me).
  - Logout clears authentication and subsequent requests are rejected.
  - Tampered or malformed session tokens are rejected.
"""

import uuid
import pytest
from database import SessionLocal
from models import User
from auth import verify_password


class TestUserRegistration:
    @pytest.mark.parametrize(
        "payload",
        [
            [{"email": "newuser@example.com", "password": "SecurePassword123!"}],
            {"email": 42, "password": "SecurePassword123!"},
            {"email": "newuser@example.com", "password": 42},
        ],
    )
    def test_registration_rejects_non_object_or_non_string_fields(
        self, unauth_client, payload
    ):
        response = unauth_client.post("/api/auth/register", json=payload)

        assert response.status_code == 400
        assert response.get_json()["error"]["code"] in {
            "INVALID_REQUEST",
            "INVALID_EMAIL",
            "INVALID_PASSWORD",
        }

    def test_registration_success(self, unauth_client):
        resp = unauth_client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "SecurePassword123!"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "user" in data
        assert data["user"]["email"] == "newuser@example.com"
        assert "id" in data["user"]
        assert "token" not in data
        # Verify cookie is set
        assert "csv_session" in resp.headers.get("Set-Cookie", "")

    def test_duplicate_registration_rejected(self, unauth_client):
        unauth_client.post(
            "/api/auth/register",
            json={"email": "dup@example.com", "password": "Password123!"},
        )
        resp = unauth_client.post(
            "/api/auth/register",
            json={"email": "dup@example.com", "password": "Password123!"},
        )
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error"]["code"] == "USER_EXISTS"

    def test_invalid_email_format_rejected(self, unauth_client):
        resp = unauth_client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "Password123!"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_EMAIL"

    def test_weak_password_rejected(self, unauth_client):
        resp = unauth_client.post(
            "/api/auth/register",
            json={"email": "valid@example.com", "password": "123"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "WEAK_PASSWORD"

    def test_password_stored_as_hash(self, unauth_client):
        raw_password = "MySecretPassword99!"
        resp = unauth_client.post(
            "/api/auth/register",
            json={"email": "hashcheck@example.com", "password": raw_password},
        )
        assert resp.status_code == 201
        user_id = resp.get_json()["user"]["id"]

        db = SessionLocal()
        user = db.get(User, user_id)
        assert user is not None
        # Must not equal raw password
        assert user.password_hash != raw_password
        # Must verify correctly via scrypt
        assert verify_password(user.password_hash, raw_password) is True


class TestUserLogin:
    @pytest.mark.parametrize(
        "payload",
        [
            [{"email": "loginuser@example.com", "password": "Password123!"}],
            {"email": 42, "password": "Password123!"},
            {"email": "loginuser@example.com", "password": 42},
        ],
    )
    def test_login_rejects_non_object_or_non_string_fields(
        self, unauth_client, payload
    ):
        response = unauth_client.post("/api/auth/login", json=payload)

        assert response.status_code == 400
        assert response.get_json()["error"]["code"] in {
            "INVALID_REQUEST",
            "INVALID_EMAIL",
            "INVALID_PASSWORD",
        }

    def test_login_success(self, unauth_client):
        unauth_client.post(
            "/api/auth/register",
            json={"email": "loginuser@example.com", "password": "Password123!"},
        )
        resp = unauth_client.post(
            "/api/auth/login",
            json={"email": "loginuser@example.com", "password": "Password123!"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["email"] == "loginuser@example.com"
        assert "token" not in data
        assert "csv_session" in resp.headers.get("Set-Cookie", "")

    def test_login_cookie_authenticates_next_request_and_is_revoked_on_logout(
        self, unauth_client, default_user
    ):
        login = unauth_client.post(
            "/api/auth/login",
            json={"email": default_user.email, "password": "Password123!"},
        )
        assert login.status_code == 200
        assert unauth_client.get_cookie("csv_session") is not None

        profile = unauth_client.get("/api/auth/me")
        assert profile.status_code == 200
        assert profile.get_json()["user"]["email"] == default_user.email

        cookie = unauth_client.get_cookie("csv_session")
        logout = unauth_client.post("/api/auth/logout")
        assert logout.status_code == 200

        unauth_client.set_cookie("csv_session", cookie.value)
        replay = unauth_client.get("/api/auth/me")
        assert replay.status_code == 401

    def test_login_cookie_authenticates_upload(
        self, unauth_client, default_user, simple_csv_bytes
    ):
        import io

        login = unauth_client.post(
            "/api/auth/login",
            json={"email": default_user.email, "password": "Password123!"},
        )

        assert login.status_code == 200
        assert unauth_client.get_cookie("csv_session") is not None
        assert "token" not in login.get_json()

        upload = unauth_client.post(
            "/upload",
            data={"file": (io.BytesIO(simple_csv_bytes), "test.csv")},
            content_type="multipart/form-data",
        )

        assert upload.status_code == 200
        assert "dataset_id" in upload.get_json()

    def test_login_invalid_password_rejected(self, unauth_client):
        unauth_client.post(
            "/api/auth/register",
            json={"email": "loginfail@example.com", "password": "Password123!"},
        )
        resp = unauth_client.post(
            "/api/auth/login",
            json={"email": "loginfail@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_nonexistent_user_rejected(self, unauth_client):
        resp = unauth_client.post(
            "/api/auth/login",
            json={"email": "doesnotexist@example.com", "password": "Password123!"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


class TestAuthProfileAndLogout:
    def test_auth_me_authenticated(self, client, default_user):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["email"] == default_user.email

    def test_auth_me_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_logout_clears_cookie(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        # Cookie deletion sends max-age=0 or expires in past
        set_cookie = resp.headers.get("Set-Cookie", "")
        assert "csv_session" in set_cookie
        assert ("Expires=" in set_cookie or "Max-Age=0" in set_cookie)

    def test_logout_revokes_previously_issued_cookie(self, unauth_client):
        registration = unauth_client.post(
            "/api/auth/register",
            json={"email": "logout_replay@example.com", "password": "Password123!"},
        )
        assert registration.status_code == 201
        token = unauth_client.get_cookie("csv_session").value

        logout = unauth_client.post("/api/auth/logout")
        assert logout.status_code == 200

        # Simulate a copied cookie being replayed after logout.
        unauth_client.set_cookie("csv_session", token)
        replay = unauth_client.get("/api/auth/me")
        assert replay.status_code == 401
        assert replay.get_json()["error"]["code"] == "UNAUTHORIZED"


class TestUnauthenticatedAccessRejected:
    """Every protected route must return 401 when accessed without credentials."""

    def test_upload_requires_auth(self, unauth_client, simple_csv_bytes):
        import io
        data = {"file": (io.BytesIO(simple_csv_bytes), "test.csv")}
        resp = unauth_client.post("/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_chart_data_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/chart-data",
            json={"dataset_id": str(uuid.uuid4()), "chart_type": "Bar", "x_axis": "A", "y_axis": "B"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_insights_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/insights",
            json={"dataset_id": str(uuid.uuid4()), "x_axis": "A", "y_axis": "B"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_ask_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/ask",
            json={"dataset_id": str(uuid.uuid4()), "question": "Total rows"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_download_requires_auth(self, unauth_client):
        resp = unauth_client.get(f"/download/{uuid.uuid4()}")
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_data_quality_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/api/data-quality",
            json={"dataset_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"

    def test_tampered_token_rejected(self, unauth_client):
        unauth_client.set_cookie("csv_session", "malicious-tampered-token-value")
        resp = unauth_client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"
