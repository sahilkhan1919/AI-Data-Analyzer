"""
config.py – Centralised configuration for the CSV Dashboard backend.

All runtime settings are read from environment variables so that the
application can be configured without code changes across development,
CI, and production environments.

Defaults are intentionally conservative for local development.
Production requires an explicit strong SECRET_KEY, PostgreSQL DATABASE_URI,
Supabase Storage, and ALLOWED_ORIGINS.
"""

import os
import logging
import re
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ---------------------------------------------------------------------------
# Flask environment
# ---------------------------------------------------------------------------
FLASK_ENV: str = os.environ.get("FLASK_ENV", "development")
if FLASK_ENV not in {"development", "production"}:
    raise RuntimeError("FLASK_ENV must be either 'development' or 'production'.")
FLASK_DEBUG: bool = FLASK_ENV != "production"
PORT: int = int(os.environ.get("PORT", "5001"))

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
# Max upload size in bytes.  Default: 10 MiB.
# Override via MAX_UPLOAD_BYTES env var (integer bytes).
try:
    MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
except ValueError:
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024

ALLOWED_EXTENSIONS: frozenset = frozenset({"csv", "xlsx"})

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", "uploads")
STORAGE_BACKEND: str = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
if STORAGE_BACKEND not in {"local", "supabase"}:
    raise RuntimeError("STORAGE_BACKEND must be either 'local' or 'supabase'.")

SUPABASE_S3_ENDPOINT: str = os.environ.get("SUPABASE_S3_ENDPOINT", "")
SUPABASE_S3_REGION: str = os.environ.get("SUPABASE_S3_REGION", "")
SUPABASE_S3_ACCESS_KEY_ID: str = os.environ.get("SUPABASE_S3_ACCESS_KEY_ID", "")
SUPABASE_S3_SECRET_ACCESS_KEY: str = os.environ.get(
    "SUPABASE_S3_SECRET_ACCESS_KEY", ""
)
SUPABASE_BUCKET_NAME: str = os.environ.get("SUPABASE_BUCKET_NAME", "")


def validate_supabase_storage_configuration(
    endpoint: str | None,
    region: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
    bucket_name: str | None,
) -> None:
    """Require complete server-side credentials for a private Supabase bucket."""
    required = {
        "SUPABASE_S3_ENDPOINT": endpoint,
        "SUPABASE_S3_REGION": region,
        "SUPABASE_S3_ACCESS_KEY_ID": access_key_id,
        "SUPABASE_S3_SECRET_ACCESS_KEY": secret_access_key,
        "SUPABASE_BUCKET_NAME": bucket_name,
    }
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        raise RuntimeError(
            "Supabase storage requires the following environment variables: "
            + ", ".join(missing)
            + "."
        )

    parsed = urlsplit(endpoint)
    try:
        parsed.port
    except ValueError:
        raise RuntimeError("SUPABASE_S3_ENDPOINT must be a valid HTTPS S3 endpoint.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".supabase.co")
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != "/storage/v1/s3"
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "SUPABASE_S3_ENDPOINT must be an HTTPS Supabase S3 endpoint ending "
            "in /storage/v1/s3."
        )
    if any(
        character.isspace()
        for credential in (access_key_id, secret_access_key)
        for character in credential
    ):
        raise RuntimeError("Supabase S3 credentials must not contain whitespace.")
    if any(character.isspace() for character in region) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]*", region
    ):
        raise RuntimeError("SUPABASE_S3_REGION must be a valid region identifier.")
    if (
        any(character.isspace() for character in bucket_name)
        or "/" in bucket_name
        or bucket_name in {".", ".."}
    ):
        raise RuntimeError("SUPABASE_BUCKET_NAME must be a valid bucket name.")


if STORAGE_BACKEND == "supabase":
    validate_supabase_storage_configuration(
        SUPABASE_S3_ENDPOINT,
        SUPABASE_S3_REGION,
        SUPABASE_S3_ACCESS_KEY_ID,
        SUPABASE_S3_SECRET_ACCESS_KEY,
        SUPABASE_BUCKET_NAME,
    )

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Comma-separated list of allowed frontend origins.
# In production, set this to the exact deployed frontend URL.
# Example: ALLOWED_ORIGINS=https://my-dashboard.vercel.app
_raw_origins: str = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS: list = [o.strip() for o in _raw_origins.split(",") if o.strip()]


def validate_production_origins(raw_origins: str | None) -> list[str]:
    """Require explicit, concrete HTTP(S) origins for credentialed production CORS."""
    origins = [
        origin.strip().rstrip("/")
        for origin in (raw_origins or "").split(",")
        if origin.strip()
    ]
    if not origins:
        raise RuntimeError("Production requires ALLOWED_ORIGINS to be explicitly configured.")

    for origin in origins:
        parsed = urlsplit(origin)
        try:
            parsed.port
        except ValueError:
            raise RuntimeError(
                "Production ALLOWED_ORIGINS must contain only valid HTTP(S) origins."
            ) from None
        if (
            "*" in origin
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                "Production ALLOWED_ORIGINS must contain only explicit HTTP(S) origins "
                "without wildcards, credentials, paths, queries, or fragments."
            )

    return origins


# ---------------------------------------------------------------------------
# Database & Authentication (Phase 3)
# ---------------------------------------------------------------------------
_default_db_path = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "csv_dashboard.db"
)
DATABASE_URI: str = os.environ.get("DATABASE_URI", f"sqlite:///{_default_db_path}")


def normalize_database_uri(uri: str) -> str:
    """Use psycopg 3 for PostgreSQL URLs, including Neon-provided URI schemes."""
    if uri.startswith("postgres://"):
        return "postgresql+psycopg://" + uri[len("postgres://") :]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg://" + uri[len("postgresql://") :]
    return uri


def validate_secret_key(secret: str | None, environment: str) -> str:
    """Require one stable, high-entropy environment key in every environment."""
    if (
        not secret
        or len(secret.encode("utf-8")) < 32
        or len(set(secret)) < 16
        or re.search(
            r"(change[-_ ]?me|example|placeholder|development|dev[-_ ]?secret)",
            secret,
            re.IGNORECASE,
        )
    ):
        raise RuntimeError(
            f"{environment.capitalize()} requires SECRET_KEY to be a stable, "
            "environment-provided secret of at least 32 bytes."
        )
    return secret


SECRET_KEY: str = validate_secret_key(os.environ.get("SECRET_KEY"), FLASK_ENV)
if FLASK_ENV == "production":
    if not normalize_database_uri(DATABASE_URI).startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "Production requires DATABASE_URI using PostgreSQL; postgres:// and "
            "postgresql:// URLs are normalized to the psycopg 3 driver."
        )
    if STORAGE_BACKEND != "supabase":
        raise RuntimeError(
            "Production requires STORAGE_BACKEND=supabase for durable file storage."
        )
    ALLOWED_ORIGINS = validate_production_origins(os.environ.get("ALLOWED_ORIGINS"))

# Maintenance credentials and login throttling
DATASET_CLEANUP_TOKEN: str = os.environ.get("DATASET_CLEANUP_TOKEN", "")
LOGIN_RATE_LIMIT_ATTEMPTS: int = int(os.environ.get("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = int(
    os.environ.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900")
)
if LOGIN_RATE_LIMIT_ATTEMPTS < 1 or LOGIN_RATE_LIMIT_WINDOW_SECONDS < 1:
    raise RuntimeError("Login rate-limit attempts and window must both be positive.")

# Dataset expiration in hours (default: 24h)
try:
    DATASET_EXPIRATION_HOURS: int = int(os.environ.get("DATASET_EXPIRATION_HOURS", 24))
except ValueError:
    DATASET_EXPIRATION_HOURS = 24

# Session cookie configuration
SESSION_COOKIE_NAME: str = "csv_session"
SESSION_COOKIE_SECURE: bool = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    or FLASK_ENV == "production"
)
SESSION_COOKIE_SAMESITE: str = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_MAX_AGE_SECONDS: int = 7 * 24 * 3600  # 7 days
CSRF_TOKEN_MAX_AGE_SECONDS: int = SESSION_COOKIE_MAX_AGE_SECONDS
if FLASK_ENV == "production" and SESSION_COOKIE_SAMESITE.lower() != "none":
    raise RuntimeError(
        "Production cross-origin authentication requires SESSION_COOKIE_SAMESITE=None."
    )

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
_numeric_level: int = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=_numeric_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

logger: logging.Logger = logging.getLogger("csv_dashboard")
logger.setLevel(_numeric_level)
