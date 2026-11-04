"""
storage.py – Safe filesystem storage abstraction for raw and cleaned datasets.

Avoids storing large binary DataFrames directly in database rows.
Persists both raw (uncleaned) and cleaned representations as CSV files,
enabling fast reloads across backend restarts and multi-worker setups.
"""

import logging
import os
import tempfile
import pandas as pd

import config

logger = logging.getLogger("csv_dashboard")

STORAGE_DIR = os.path.join(config.UPLOAD_FOLDER, "datasets")
os.makedirs(STORAGE_DIR, exist_ok=True)


def get_dataset_paths(dataset_id: str) -> tuple[str, str]:
    """Return (raw_storage_path, cleaned_storage_path) for a dataset ID."""
    raw_path = os.path.join(STORAGE_DIR, f"{dataset_id}_raw.csv")
    cleaned_path = os.path.join(STORAGE_DIR, f"{dataset_id}_cleaned.csv")
    return raw_path, cleaned_path


def get_report_path(report_id: str) -> str:
    """Return the private storage path for a generated report identifier."""
    return os.path.join(STORAGE_DIR, "reports", f"{report_id}.pdf")


def delete_report_storage(report_id: str) -> None:
    """Delete a generated report by its opaque identifier; missing reports are already removed."""
    try:
        os.remove(get_report_path(report_id))
    except FileNotFoundError:
        return
    logger.info("Removed generated report %s", report_id)


def _path_exists(path: str) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False


def persist_dataset(dataset_id: str, raw_df: pd.DataFrame, cleaned_df: pd.DataFrame) -> tuple[str, str]:
    """
    Persist both raw and cleaned DataFrames to disk.
    Returns (raw_path, cleaned_path).
    """
    os.makedirs(STORAGE_DIR, exist_ok=True)
    raw_path, cleaned_path = get_dataset_paths(dataset_id)
    if _path_exists(raw_path) or _path_exists(cleaned_path):
        raise FileExistsError(f"Dataset storage already exists for {dataset_id}")

    temp_paths = []
    created_paths = []
    try:
        for frame in (raw_df, cleaned_df):
            fd, temp_path = tempfile.mkstemp(
                prefix=f".{dataset_id}_",
                suffix=".tmp",
                dir=STORAGE_DIR,
            )
            os.close(fd)
            temp_paths.append(temp_path)
            frame.to_csv(temp_path, index=False, encoding="utf-8")

        for temp_path, path in zip(temp_paths, (raw_path, cleaned_path)):
            os.replace(temp_path, path)
            created_paths.append(path)
    except Exception:
        for path in (*temp_paths, *created_paths):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        raise

    logger.info("Persisted dataset %s to disk (raw=%s, cleaned=%s)", dataset_id, raw_path, cleaned_path)
    return raw_path, cleaned_path


def load_dataset(cleaned_path: str) -> pd.DataFrame:
    """Load cleaned DataFrame from disk. Raises FileNotFoundError if missing."""
    if not os.path.isfile(cleaned_path):
        raise FileNotFoundError(f"Cleaned dataset file not found at {cleaned_path}")
    return pd.read_csv(cleaned_path, encoding="utf-8")


def load_raw_dataset(raw_path: str) -> pd.DataFrame:
    """Load raw DataFrame from disk. Raises FileNotFoundError if missing."""
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(f"Raw dataset file not found at {raw_path}")
    return pd.read_csv(raw_path, encoding="utf-8")


def delete_dataset_storage(raw_path: str, cleaned_path: str) -> None:
    """Remove dataset files, ignoring missing files and surfacing other failures."""
    for path in (raw_path, cleaned_path):
        if path:
            try:
                os.remove(path)
            except FileNotFoundError:
                continue
            logger.info("Removed dataset file: %s", path)


def stage_dataset_deletion(dataset_id: str) -> tuple[str, str]:
    """Atomically move files out of normal paths so deletion can be retried."""
    raw_path, cleaned_path = get_dataset_paths(dataset_id)
    staged_paths = (f"{raw_path}.deleting", f"{cleaned_path}.deleting")
    for source, staged in zip((raw_path, cleaned_path), staged_paths):
        if _path_exists(staged):
            if _path_exists(source):
                raise FileExistsError(f"Both source and staged storage exist for {dataset_id}")
            continue
        if _path_exists(source):
            os.replace(source, staged)
    return staged_paths


def remove_staged_dataset(staged_paths: tuple[str, str]) -> None:
    """Permanently remove staged files; errors leave the deletion retryable."""
    for path in staged_paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
