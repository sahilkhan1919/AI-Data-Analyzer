"""
models.py – SQLAlchemy database models for Phase 3.

Defines persistent User and Dataset entities for authentication,
multi-tenant dataset ownership, and dataset lifecycle management.
"""

from datetime import datetime, timezone
import json
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Registered application user with securely hashed credentials."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    datasets = relationship(
        "Dataset",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RevokedSession(Base):
    """Hash-only record of a logged-out authentication token."""

    __tablename__ = "revoked_sessions"

    token_hash = Column(String(64), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class Dataset(Base):
    """
    Metadata record for an uploaded CSV or XLSX dataset.

    Actual tabular data is persisted to disk under storage paths, keeping database
    records lightweight while preserving full persistence across restarts.
    """

    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    raw_storage_path = Column(String(512), nullable=False)
    cleaned_storage_path = Column(String(512), nullable=False)

    upload_timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_accessed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    deletion_pending = Column(Boolean, nullable=False, default=False)

    # Cached JSON metadata for immediate UI responses without reading from disk
    columns_json = Column(Text, nullable=True)
    numeric_columns_json = Column(Text, nullable=True)
    date_columns_json = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True)
    preview_json = Column(Text, nullable=True)

    user = relationship("User", back_populates="datasets")

    @property
    def columns(self) -> list:
        return json.loads(self.columns_json) if self.columns_json else []

    @property
    def numeric_columns(self) -> list:
        return json.loads(self.numeric_columns_json) if self.numeric_columns_json else []

    @property
    def date_columns(self) -> list:
        return json.loads(self.date_columns_json) if self.date_columns_json else []

    @property
    def summary(self) -> dict:
        return json.loads(self.summary_json) if self.summary_json else {}

    @property
    def preview(self) -> list:
        return json.loads(self.preview_json) if self.preview_json else []

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.id,
            "original_filename": self.original_filename,
            "file_size_bytes": self.file_size_bytes,
            "upload_timestamp": self.upload_timestamp.isoformat() if self.upload_timestamp else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "columns": self.columns,
            "numeric_columns": self.numeric_columns,
            "date_columns": self.date_columns,
            "summary": self.summary,
            "preview": self.preview,
        }


class LoginRateLimit(Base):
    """Shared database-backed login attempt window for all application workers."""

    __tablename__ = "login_rate_limits"

    key = Column(String(64), primary_key=True)
    attempt_count = Column(Integer, nullable=False)
    window_started_at = Column(DateTime(timezone=True), nullable=False, index=True)


class BusinessReport(Base):
    """Generated PDF metadata, scoped to its requesting user and dataset."""

    __tablename__ = "business_reports"

    id = Column(String(36), primary_key=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_path = Column(String(512), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
