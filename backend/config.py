"""
config.py – Centralised configuration for the CSV Dashboard backend.

All runtime settings are read from environment variables so that the
application can be configured without code changes across development,
CI, and production environments.

Defaults are intentionally conservative for local development.
Production requires an explicit strong SECRET_KEY, PostgreSQL DATABASE_URI,
and ALLOWED_ORIGINS. Uploaded files require a durable shared volume.
"""

import os
import logging
import re

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

# ---------------------------------------------------------------------------
# Database & Authentication (Phase 3)
# ---------------------------------------------------------------------------
_default_db_path = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "csv_dashboard.db"
)
DATABASE_URI: str = os.environ.get("DATABASE_URI", f"sqlite:///{_default_db_path}")


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
    if not os.environ.get("DATABASE_URI", "").startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "Production requires DATABASE_URI using the postgresql+psycopg:// driver."
        )
    if not os.environ.get("ALLOWED_ORIGINS"):
        raise RuntimeError("Production requires ALLOWED_ORIGINS to be explicitly configured.")

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
