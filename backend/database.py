"""
database.py – Centralized SQLAlchemy engine and session management.

Supports SQLite for local development and PostgreSQL in deployment.
Ensures connection pooling, connection recycling, and clean transaction handling.
"""

from contextlib import contextmanager
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

import config
from models import Base

logger = logging.getLogger("csv_dashboard")

_engine = None
_SessionFactory = None
SessionLocal = None


def create_db_engine(database_uri: str = None):
    """
    Create an engine configured appropriately for the target dialect.
    """
    uri = config.normalize_database_uri(database_uri or config.DATABASE_URI)
    connect_args = {}

    if uri.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure parent directory exists for SQLite db file
        if ":///" in uri:
            db_path = uri.split(":///", 1)[1]
            parent_dir = os.path.dirname(os.path.abspath(db_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
        return create_engine(
            uri,
            connect_args=connect_args,
        )
    else:
        # PostgreSQL or other production databases
        return create_engine(
            uri,
            pool_pre_ping=True,
            pool_recycle=300,
        )


_engine = create_db_engine()
_SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
SessionLocal = scoped_session(_SessionFactory)


def init_app_db(app=None, database_uri: str = None):
    """Initialize database tables and reconfigure scoped session."""
    global _engine
    _engine = create_db_engine(database_uri)
    SessionLocal.remove()
    SessionLocal.configure(bind=_engine)
    if config.FLASK_ENV != "production":
        Base.metadata.create_all(bind=_engine)
    else:
        logger.info("Production schema initialization is managed by Alembic migrations.")
    logger.info("Initialized database with tables: %s", list(Base.metadata.tables.keys()))
    return _engine


@contextmanager
def get_db_session():
    """Context manager for safe transactional database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
