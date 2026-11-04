"""
auth.py – Secure backend authentication and authorization utilities for Phase 3.

Features:
  - NIST-approved password hashing via Werkzeug (scrypt / pbkdf2:sha256).
  - Secure signed session tokens via itsdangerous.
  - HTTP-only cookie management with configurable SameSite & Secure flags.
  - @login_required decorator setting g.current_user.
  - Authorization error handling with standard structured JSON responses.
"""

from functools import wraps
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import re
from flask import g, jsonify, request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import config
from database import SessionLocal
from models import RevokedSession, User

logger = logging.getLogger("csv_dashboard")

_EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="csv-dashboard-auth")
_csrf_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="csv-dashboard-csrf")


def hash_password(password: str) -> str:
    """Hash password using Werkzeug's default modern hashing (scrypt)."""
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify plaintext password against stored hash."""
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)


def generate_auth_token(user_id: str) -> str:
    """Create a tamper-proof cryptographically signed session token."""
    return _serializer.dumps({"user_id": user_id})


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token(session_token: str) -> str:
    """Create a short-lived CSRF token bound to the current signed session."""
    return _csrf_serializer.dumps({"session": _token_hash(session_token)})


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    """Verify that a CSRF token is valid and belongs to this session cookie."""
    if not session_token or not csrf_token:
        return False
    try:
        data = _csrf_serializer.loads(
            csrf_token,
            max_age=config.CSRF_TOKEN_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return False
    return hmac.compare_digest(
        str(data.get("session", "")),
        _token_hash(session_token),
    )


def verify_auth_token(token: str, max_age: int = None) -> str | None:
    """
    Validate session token and return user_id if valid.
    Returns None if signature is invalid or token expired.
    """
    if not token:
        return None
    age = max_age if max_age is not None else config.SESSION_COOKIE_MAX_AGE_SECONDS
    try:
        data = _serializer.loads(token, max_age=age)
        user_id = data.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            return None
        if SessionLocal().get(RevokedSession, _token_hash(token)):
            return None
        return user_id
    except (BadSignature, SignatureExpired):
        return None


def revoke_auth_token(token: str) -> None:
    """Persist a hash-only revocation record so a logged-out token cannot be replayed."""
    if not token:
        return

    try:
        _serializer.loads(token, max_age=config.SESSION_COOKIE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    db.query(RevokedSession).filter(RevokedSession.expires_at <= now).delete(
        synchronize_session=False
    )
    db.merge(
        RevokedSession(
            token_hash=_token_hash(token),
            expires_at=now + timedelta(seconds=config.SESSION_COOKIE_MAX_AGE_SECONDS),
        )
    )
    db.commit()


def get_current_authenticated_user() -> User | None:
    """
    Retrieve current authenticated user from session cookie or Authorization header.
    Returns User instance or None.
    """
    # 1. Check HTTP-only cookie first
    token = request.cookies.get(config.SESSION_COOKIE_NAME)

    # 2. Support Authorization header (Bearer token) for flexibility & testing
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    user_id = verify_auth_token(token)
    if not user_id:
        return None

    db = SessionLocal()
    user = db.get(User, user_id)
    return user


def login_required(f):
    """
    Decorator to protect routes.
    Sets g.current_user if authenticated; returns 401 UNAUTHORIZED otherwise.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_authenticated_user()
        if not user:
            return jsonify({
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Authentication required. Please log in.",
                }
            }), 401

        g.current_user = user
        return f(*args, **kwargs)

    return decorated_function


def set_auth_cookie(response: Response, token: str) -> Response:
    """Attach HTTP-only session cookie to response."""
    response.set_cookie(
        config.SESSION_COOKIE_NAME,
        token,
        max_age=config.SESSION_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite=config.SESSION_COOKIE_SAMESITE,
        path="/",
    )
    return response


def clear_auth_cookie(response: Response) -> Response:
    """Clear session cookie on logout."""
    response.delete_cookie(
        config.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite=config.SESSION_COOKIE_SAMESITE,
    )
    return response


def validate_email_format(email: str) -> bool:
    """Validate email address format."""
    return bool(isinstance(email, str) and _EMAIL_REGEX.match(email.strip()))
