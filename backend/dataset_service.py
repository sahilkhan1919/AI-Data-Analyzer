"""
dataset_service.py – Unified dataset lifecycle, caching, and multi-tenant access control.

Responsibilities:
  - Coordinate database records with filesystem storage and fast in-memory caches.
  - Enforce tenant isolation: verify that the requesting user owns the dataset.
  - Enforce expiration rules: reject expired datasets and perform safe cleanup.
  - Restore datasets seamlessly across backend restarts from persistent storage.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import pandas as pd
from flask import jsonify
from sqlalchemy import or_

import config
from database import SessionLocal
from models import BusinessReport, Dataset
from storage import (
    delete_report_storage,
    delete_dataset_storage,
    load_dataset,
    load_raw_dataset,
    persist_dataset,
    remove_staged_dataset,
    stage_dataset_deletion,
)

logger = logging.getLogger("csv_dashboard")

# In-memory LRU/dict cache for rapid query responses
# Lost on restart, but transparently restored from database + storage on next request
MEMORY_CACHE: dict[str, pd.DataFrame] = {}
RAW_MEMORY_CACHE: dict[str, pd.DataFrame] = {}


def _json_error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def save_user_dataset(
    user_id: str,
    dataset_id: str,
    original_filename: str,
    file_size_bytes: int,
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    numeric_columns: list,
    date_columns: list,
    summary: dict,
    preview: list,
) -> Dataset:
    """
    Persist raw/cleaned data to filesystem and metadata to database.
    Populates in-memory cache for immediate query availability.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=config.DATASET_EXPIRATION_HOURS)

    # 1. Save files to disk
    raw_path, cleaned_path = persist_dataset(dataset_id, raw_df, cleaned_df)

    # 2. Store in database
    db = SessionLocal()
    try:
        dataset_record = Dataset(
            id=dataset_id,
            user_id=user_id,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            raw_storage_path=raw_path,
            cleaned_storage_path=cleaned_path,
            upload_timestamp=now,
            last_accessed_at=now,
            expires_at=expires_at,
            columns_json=json.dumps(cleaned_df.columns.tolist()),
            numeric_columns_json=json.dumps(numeric_columns),
            date_columns_json=json.dumps(date_columns),
            summary_json=json.dumps(summary),
            preview_json=json.dumps(preview),
        )
        db.add(dataset_record)
        db.commit()
        db.refresh(dataset_record)
    except Exception:
        db.rollback()
        # Clean up files if database insert fails to prevent orphaned files
        try:
            delete_dataset_storage(raw_path, cleaned_path)
        except OSError:
            logger.exception("Could not remove storage after failed dataset registration.")
        raise

    # 3. Populate memory cache
    MEMORY_CACHE[dataset_id] = cleaned_df
    RAW_MEMORY_CACHE[dataset_id] = raw_df

    logger.info("Successfully registered dataset %s for user %s", dataset_id, user_id)
    return dataset_record


def get_accessible_dataset(dataset_id: str, user_id: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None, tuple | None]:
    """
    Authorize access and retrieve (cleaned_df, raw_df, error_tuple).
    If authorized and valid, returns (cleaned_df, raw_df, None).
    Otherwise returns (None, None, (response, status_code)).
    """
    if not dataset_id:
        return None, None, _json_error("MISSING_DATASET_ID", "dataset_id is required.", 400)

    db = SessionLocal()
    dataset: Dataset = db.get(Dataset, dataset_id)

    if not dataset:
        return None, None, _json_error("DATASET_NOT_FOUND", "Dataset not found.", 404)

    # Multi-tenant ownership verification
    if dataset.user_id != user_id:
        logger.warning(
            "Access denied: user %s attempted to access dataset %s owned by %s",
            user_id,
            dataset_id,
            dataset.user_id,
        )
        return None, None, _json_error(
            "FORBIDDEN",
            "You do not have permission to access this dataset.",
            403,
        )

    if dataset.deletion_pending:
        return None, None, _json_error("DATASET_NOT_FOUND", "Dataset not found.", 404)

    # Expiration check
    now = datetime.now(timezone.utc)
    # Ensure tz-aware comparison
    dataset_expiry = dataset.expires_at
    if dataset_expiry.tzinfo is None:
        dataset_expiry = dataset_expiry.replace(tzinfo=timezone.utc)

    if dataset_expiry <= now:
        logger.info("Dataset %s has expired (expired at %s)", dataset_id, dataset_expiry)
        return None, None, _json_error("DATASET_EXPIRED", "Dataset has expired.", 404)

    # Update last_accessed_at timestamp
    try:
        dataset.last_accessed_at = now
        db.commit()
    except Exception as exc:
        logger.warning("Could not update last_accessed_at for %s: %s", dataset_id, exc)
        db.rollback()

    # Load from memory cache or restore from disk
    cleaned_df = MEMORY_CACHE.get(dataset_id)
    raw_df = RAW_MEMORY_CACHE.get(dataset_id)

    if cleaned_df is None:
        try:
            cleaned_df = load_dataset(dataset.cleaned_storage_path)
            MEMORY_CACHE[dataset_id] = cleaned_df
        except FileNotFoundError:
            logger.error("Cleaned dataset file missing on disk: %s", dataset.cleaned_storage_path)
            return None, None, _json_error("DATASET_FILE_MISSING", "Dataset file is missing on server.", 500)

    if raw_df is None:
        try:
            raw_df = load_raw_dataset(dataset.raw_storage_path)
            RAW_MEMORY_CACHE[dataset_id] = raw_df
        except FileNotFoundError:
            # Fall back to cleaned_df if raw file is missing
            raw_df = cleaned_df

    return cleaned_df, raw_df, None


def list_user_datasets(user_id: str) -> list[dict]:
    """Return non-expired datasets owned by the authenticated user without storage paths."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        datasets = (
            db.query(Dataset)
            .filter(
                Dataset.user_id == user_id,
                Dataset.expires_at > now,
                Dataset.deletion_pending.is_(False),
            )
            .order_by(Dataset.upload_timestamp.desc())
            .all()
        )
        return [dataset.to_dict() for dataset in datasets]
    finally:
        db.close()


def _finish_dataset_deletion(db, dataset: Dataset) -> None:
    dataset_id = dataset.id
    if not dataset.deletion_pending:
        dataset.deletion_pending = True
        db.commit()

    staged_paths = stage_dataset_deletion(
        dataset_id,
        dataset.raw_storage_path,
        dataset.cleaned_storage_path,
    )
    remove_staged_dataset(staged_paths)
    reports = db.query(BusinessReport).filter(BusinessReport.dataset_id == dataset_id).all()
    for report in reports:
        delete_report_storage(report.id, report.storage_path)
        db.delete(report)
    db.delete(dataset)
    db.commit()
    MEMORY_CACHE.pop(dataset_id, None)
    RAW_MEMORY_CACHE.pop(dataset_id, None)


def delete_user_dataset(dataset_id: str, user_id: str) -> tuple[bool, tuple | None]:
    """Delete an owned dataset with a durable pending marker and retryable storage cleanup."""
    db = SessionLocal()
    try:
        dataset = db.get(Dataset, dataset_id)
        if not dataset:
            return False, _json_error("DATASET_NOT_FOUND", "Dataset not found.", 404)
        if dataset.user_id != user_id:
            return False, _json_error(
                "FORBIDDEN", "You do not have permission to delete this dataset.", 403
            )
        try:
            _finish_dataset_deletion(db, dataset)
            logger.info("Deleted dataset %s for user %s", dataset_id, user_id)
            return True, None
        except Exception as exc:
            db.rollback()
            db.expire_all()
            logger.error(
                "Dataset deletion for %s remains pending and can be retried: %s",
                dataset_id,
                exc,
                exc_info=True,
            )
            return False, _json_error(
                "DATASET_DELETE_PENDING",
                "Deletion could not be completed. The dataset is inaccessible and cleanup can be retried.",
                503,
            )
    finally:
        db.close()


def cleanup_expired_datasets() -> int:
    """
    Stage expired datasets and remove their metadata only after storage succeeds.
    Failed deletions remain marked for a later retry.
    Returns count of removed datasets.
    """
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    count = 0
    failures = []
    try:
        expired_datasets = (
            db.query(Dataset)
            .filter(or_(Dataset.expires_at <= now, Dataset.deletion_pending.is_(True)))
            .all()
        )
        for ds in expired_datasets:
            try:
                _finish_dataset_deletion(db, ds)
                count += 1
            except Exception as exc:
                db.rollback()
                db.expire_all()
                logger.error(
                    "Could not finish deletion for dataset %s; it will be retried: %s",
                    ds.id,
                    exc,
                    exc_info=True,
                )
                failures.append(exc)

        if count > 0:
            logger.info("Cleaned up %d expired dataset(s)", count)
        if failures:
            raise RuntimeError(
                f"Failed to clean up {len(failures)} dataset(s); retry is pending."
            ) from failures[0]
    finally:
        db.close()
    return count
