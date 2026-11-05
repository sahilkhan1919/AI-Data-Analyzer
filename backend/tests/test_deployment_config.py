import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

import config


def _production_env(origins="https://dashboard.example.test"):
    env = os.environ.copy()
    env.update(
        {
            "FLASK_ENV": "production",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_URI": "postgresql://db.example.test/app?sslmode=require",
            "ALLOWED_ORIGINS": origins,
            "STORAGE_BACKEND": "r2",
            "R2_ACCOUNT_ID": "test-account",
            "R2_BUCKET_NAME": "test-bucket",
            "R2_ACCESS_KEY_ID": "test-access-key",
            "R2_SECRET_ACCESS_KEY": "test-secret-key",
            "SESSION_COOKIE_SAMESITE": "None",
        }
    )
    return env


def test_production_origins_accept_explicit_http_and_https_origins():
    assert config.validate_production_origins(
        "https://dashboard.example.test, https://admin.example.test/"
    ) == ["https://dashboard.example.test", "https://admin.example.test"]


@pytest.mark.parametrize(
    "origins",
    [
        "",
        "*",
        "https://*.vercel.app",
        "https://dashboard.example.test/path",
        "https://user@dashboard.example.test",
        "ftp://dashboard.example.test",
        "https://dashboard.example.test?query=1",
        "https://dashboard.example.test:invalid",
    ],
)
def test_production_origins_reject_missing_or_non_origin_values(origins):
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        config.validate_production_origins(origins)


def test_production_startup_rejects_wildcard_allowed_origins():
    backend_dir = Path(__file__).resolve().parents[1]
    env = _production_env("https://dashboard.example.test,*")
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ALLOWED_ORIGINS" in result.stderr


def test_production_startup_requires_explicit_allowed_origins():
    backend_dir = Path(__file__).resolve().parents[1]
    env = _production_env("")
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ALLOWED_ORIGINS" in result.stderr


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (
            "postgres://user:pass@ep.example.neon.tech/app?sslmode=require",
            "postgresql+psycopg://user:pass@ep.example.neon.tech/app?sslmode=require",
        ),
        (
            "postgresql://user:pass@ep.example.neon.tech/app?sslmode=require",
            "postgresql+psycopg://user:pass@ep.example.neon.tech/app?sslmode=require",
        ),
        (
            "postgresql+psycopg://user:pass@db.example.test/app",
            "postgresql+psycopg://user:pass@db.example.test/app",
        ),
    ],
)
def test_postgresql_uri_normalization_supports_neon(uri, expected):
    assert config.normalize_database_uri(uri) == expected


def test_neon_uri_creates_psycopg_engine_without_connecting():
    from database import create_db_engine

    engine = create_db_engine(
        "postgresql://user:pass@ep.example.neon.tech/app?sslmode=require"
    )
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_production_cookie_uses_secure_cross_origin_attributes():
    backend_dir = Path(__file__).resolve().parents[1]
    script = (
        "from flask import Response; "
        "from auth import set_auth_cookie; "
        "print(set_auth_cookie(Response(), 'synthetic-test-token').headers['Set-Cookie'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=_production_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Secure" in result.stdout
    assert "HttpOnly" in result.stdout
    assert "SameSite=None" in result.stdout
    assert "synthetic-test-token" in result.stdout


def test_production_cors_and_csrf_allow_only_the_configured_frontend_origin():
    backend_dir = Path(__file__).resolve().parents[1]
    script = """
import app as application
import config
from auth import generate_auth_token, generate_csrf_token

@application.app.route("/production-csrf-probe", methods=["POST"])
def production_csrf_probe():
    return "ok"

origin = "https://dashboard.example.test"
client = application.app.test_client()
preflight = client.options(
    "/production-csrf-probe",
    headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-csrf-token",
    },
)
assert preflight.headers["Access-Control-Allow-Origin"] == origin
assert preflight.headers["Access-Control-Allow-Credentials"] == "true"

token = generate_auth_token("synthetic-user")
csrf = generate_csrf_token(token)
cookie = f"{config.SESSION_COOKIE_NAME}={token}"
accepted = client.post(
    "/production-csrf-probe",
    headers={"Origin": origin, "Cookie": cookie, "X-CSRF-Token": csrf},
)
assert accepted.status_code == 200
rejected = client.post(
    "/production-csrf-probe",
    headers={
        "Origin": "https://attacker.example",
        "Cookie": cookie,
        "X-CSRF-Token": csrf,
    },
)
assert rejected.status_code == 403
print("production cross-origin checks passed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=_production_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "production cross-origin checks passed" in result.stdout


def test_allowed_cross_origin_preflight_and_csrf(client):
    preflight = client.options(
        "/api/auth/logout",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert preflight.headers["Access-Control-Allow-Credentials"] == "true"

    allowed = client.post(
        "/api/auth/logout",
        headers={"Origin": "http://localhost:5173"},
    )
    assert allowed.status_code == 200


def test_foreign_origin_is_rejected_for_cookie_authenticated_requests(client):
    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "CSRF_ORIGIN_INVALID"


def test_render_manifest_has_gunicorn_bind_and_health_check():
    repository_root = Path(__file__).resolve().parents[2]
    manifest = (repository_root / "render.yaml").read_text()

    assert "startCommand: gunicorn --bind 0.0.0.0:$PORT app:app" in manifest
    assert "healthCheckPath: /api/health" in manifest
    assert "STORAGE_BACKEND" in manifest
    requirements = (repository_root / "backend" / "requirements.txt").read_text()
    assert "gunicorn" in requirements.lower()
    assert "boto3" in requirements.lower()
