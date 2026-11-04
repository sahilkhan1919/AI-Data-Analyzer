"""Database-backed login attempt throttling shared across application workers."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import config
from database import SessionLocal
from models import LoginRateLimit

logger = logging.getLogger("csv_dashboard")


def _rate_limit_key(email: str, remote_addr: str | None) -> str:
    value = f"{(remote_addr or 'unknown').strip()}:{email.strip().lower()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def consume_login_attempt(email: str, remote_addr: str | None) -> tuple[bool, int]:
    """Atomically count an attempt; return whether it is allowed and retry seconds."""
    now = datetime.now(timezone.utc)
    window = timedelta(seconds=config.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    cutoff = now - window
    key = _rate_limit_key(email, remote_addr)
    db = SessionLocal()
    try:
        db.execute(
            delete(LoginRateLimit).where(LoginRateLimit.window_started_at <= cutoff)
        )
        dialect = db.get_bind().dialect.name
        insert = {
            "sqlite": sqlite_insert,
            "postgresql": postgresql_insert,
        }.get(dialect)
        if insert is None:
            raise RuntimeError(f"Login throttling does not support database dialect {dialect}.")

        statement = insert(LoginRateLimit).values(
            key=key,
            attempt_count=1,
            window_started_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[LoginRateLimit.key],
            set_={
                "attempt_count": case(
                    (LoginRateLimit.window_started_at <= cutoff, 1),
                    else_=LoginRateLimit.attempt_count + 1,
                ),
                "window_started_at": case(
                    (LoginRateLimit.window_started_at <= cutoff, now),
                    else_=LoginRateLimit.window_started_at,
                ),
            },
        ).returning(LoginRateLimit.attempt_count, LoginRateLimit.window_started_at)
        attempt_count, window_started_at = db.execute(statement).one()
        db.commit()
        allowed = attempt_count <= config.LOGIN_RATE_LIMIT_ATTEMPTS
        started = window_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        retry_after = max(
            1,
            int((started + window - now).total_seconds()),
        )
        return allowed, retry_after
    except Exception:
        db.rollback()
        logger.exception("Could not update the shared login rate limit.")
        raise


def clear_login_attempts(email: str, remote_addr: str | None) -> None:
    """Clear the identifier's failure window after successful authentication."""
    db = SessionLocal()
    try:
        db.query(LoginRateLimit).filter(
            LoginRateLimit.key == _rate_limit_key(email, remote_addr)
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not clear the login rate limit after success.")
        raise
