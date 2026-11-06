"""Private local-filesystem and Supabase Storage for datasets and reports."""

import io
import logging
import os
import tempfile
import uuid
from urllib.parse import urlsplit

import pandas as pd
from botocore.config import Config

import config

logger = logging.getLogger("csv_dashboard")

STORAGE_DIR = os.path.join(config.UPLOAD_FOLDER, "datasets")
if config.STORAGE_BACKEND == "local":
    os.makedirs(STORAGE_DIR, exist_ok=True)

_s3_client = None
_OBJECT_PREFIX = "csv-dashboard"


def _is_supabase_location(location: str) -> bool:
    return isinstance(location, str) and location.startswith("supabase://")


def _s3_key(location: str) -> str:
    parsed = urlsplit(location)
    if (
        parsed.scheme != "supabase"
        or parsed.netloc != config.SUPABASE_BUCKET_NAME
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid Supabase storage reference.")
    key = parsed.path.lstrip("/")
    if not key or any(part in {".", ".."} for part in key.split("/")):
        raise ValueError("Invalid Supabase storage reference.")
    return key


def _supabase_location(key: str) -> str:
    return f"supabase://{config.SUPABASE_BUCKET_NAME}/{key}"


def _s3_key_for(relative_key: str) -> str:
    return f"{_OBJECT_PREFIX}/{relative_key}"


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client(
            "s3",
            endpoint_url=config.SUPABASE_S3_ENDPOINT,
            region_name=config.SUPABASE_S3_REGION,
            aws_access_key_id=config.SUPABASE_S3_ACCESS_KEY_ID,
            aws_secret_access_key=config.SUPABASE_S3_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
    return _s3_client


def _is_missing_object(error: Exception) -> bool:
    response = getattr(error, "response", {})
    details = response.get("Error", {})
    metadata = response.get("ResponseMetadata", {})
    return details.get("Code") in {"404", "NoSuchKey", "NotFound"} or metadata.get(
        "HTTPStatusCode"
    ) == 404


def _delete_object(location: str) -> None:
    key = _s3_key(location)
    try:
        _get_s3_client().delete_object(
            Bucket=config.SUPABASE_BUCKET_NAME,
            Key=key,
        )
    except Exception as exc:
        if not _is_missing_object(exc):
            raise


def get_dataset_paths(dataset_id: str) -> tuple[str, str]:
    """Return storage references for a dataset's raw and cleaned CSVs."""
    if config.STORAGE_BACKEND == "supabase":
        prefix = _s3_key_for("datasets")
        return (
            _supabase_location(f"{prefix}/{dataset_id}_raw.csv"),
            _supabase_location(f"{prefix}/{dataset_id}_cleaned.csv"),
        )
    return (
        os.path.join(STORAGE_DIR, f"{dataset_id}_raw.csv"),
        os.path.join(STORAGE_DIR, f"{dataset_id}_cleaned.csv"),
    )


def get_report_path(report_id: str) -> str:
    """Return the private storage reference for a generated report."""
    if config.STORAGE_BACKEND == "supabase":
        return _supabase_location(_s3_key_for(f"reports/{report_id}.pdf"))
    return os.path.join(STORAGE_DIR, "reports", f"{report_id}.pdf")


def persist_report(report_id: str, content: bytes) -> str:
    """Persist PDF bytes and return their private storage reference."""
    path = get_report_path(report_id)
    if _is_supabase_location(path):
        try:
            _get_s3_client().put_object(
                Bucket=config.SUPABASE_BUCKET_NAME,
                Key=_s3_key(path),
                Body=content,
                ContentType="application/pdf",
            )
        except Exception:
            try:
                _delete_object(path)
            except Exception:
                logger.error("Could not clean up a partially written report object.")
            raise
        return path

    report_dir = os.path.dirname(path)
    os.makedirs(report_dir, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{report_id}_",
        suffix=".tmp",
        dir=report_dir,
    )
    try:
        with os.fdopen(fd, "wb") as report_file:
            report_file.write(content)
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
        raise
    return path


def load_report(path: str) -> bytes:
    """Load a private report from its storage reference."""
    if _is_supabase_location(path):
        try:
            response = _get_s3_client().get_object(
                Bucket=config.SUPABASE_BUCKET_NAME,
                Key=_s3_key(path),
            )
        except Exception as exc:
            if _is_missing_object(exc):
                raise FileNotFoundError("Generated report is missing from storage.") from exc
            raise
        with response["Body"] as body:
            return body.read()

    with open(path, "rb") as report_file:
        return report_file.read()


def delete_report_storage(report_id: str, storage_path: str | None = None) -> None:
    """Delete a generated report by its opaque identifier; missing reports are already removed."""
    path = storage_path if storage_path is not None else get_report_path(report_id)
    if _is_supabase_location(path):
        _delete_object(path)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            return
    logger.info("Removed generated report %s", report_id)


def _path_exists(path: str) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False


def _object_exists(location: str) -> bool:
    try:
        _get_s3_client().head_object(
            Bucket=config.SUPABASE_BUCKET_NAME,
            Key=_s3_key(location),
        )
    except Exception as exc:
        if _is_missing_object(exc):
            return False
        raise
    return True


def _frame_csv_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def persist_dataset(
    dataset_id: str,
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
) -> tuple[str, str]:
    """Persist raw/cleaned CSVs and return their storage references."""
    raw_path, cleaned_path = get_dataset_paths(dataset_id)
    if _is_supabase_location(raw_path):
        if _object_exists(raw_path) or _object_exists(cleaned_path):
            raise FileExistsError(f"Dataset storage already exists for {dataset_id}")

        client = _get_s3_client()
        written_keys = []
        try:
            for frame, path in zip((raw_df, cleaned_df), (raw_path, cleaned_path)):
                key = _s3_key(path)
                written_keys.append(key)
                client.put_object(
                    Bucket=config.SUPABASE_BUCKET_NAME,
                    Key=key,
                    Body=_frame_csv_bytes(frame),
                    ContentType="text/csv; charset=utf-8",
                )
        except Exception:
            for key in written_keys:
                try:
                    client.delete_object(
                        Bucket=config.SUPABASE_BUCKET_NAME,
                        Key=key,
                    )
                except Exception:
                    logger.error("Could not clean up a partially written dataset object.")
            raise
        logger.info("Persisted dataset %s to Supabase Storage", dataset_id)
        return raw_path, cleaned_path

    os.makedirs(STORAGE_DIR, exist_ok=True)
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

    logger.info(
        "Persisted dataset %s to disk (raw=%s, cleaned=%s)",
        dataset_id,
        raw_path,
        cleaned_path,
    )
    return raw_path, cleaned_path


def _load_dataset(path: str, kind: str) -> pd.DataFrame:
    if _is_supabase_location(path):
        try:
            response = _get_s3_client().get_object(
                Bucket=config.SUPABASE_BUCKET_NAME,
                Key=_s3_key(path),
            )
        except Exception as exc:
            if _is_missing_object(exc):
                raise FileNotFoundError(
                    f"{kind.capitalize()} dataset is missing from storage."
                ) from exc
            raise
        with response["Body"] as body:
            content = body.read()
        return pd.read_csv(io.BytesIO(content), encoding="utf-8")

    if not os.path.isfile(path):
        raise FileNotFoundError(f"{kind.capitalize()} dataset file not found at {path}")
    return pd.read_csv(path, encoding="utf-8")


def load_dataset(cleaned_path: str) -> pd.DataFrame:
    """Load a cleaned DataFrame from its storage reference."""
    return _load_dataset(cleaned_path, "cleaned")


def load_raw_dataset(raw_path: str) -> pd.DataFrame:
    """Load a raw DataFrame from its storage reference."""
    return _load_dataset(raw_path, "raw")


def delete_dataset_storage(raw_path: str, cleaned_path: str) -> None:
    """Remove dataset objects/files, ignoring missing objects and surfacing other failures."""
    if _is_supabase_location(raw_path) or _is_supabase_location(cleaned_path):
        for path in (raw_path, cleaned_path):
            if path:
                _delete_object(path)
        return

    for path in (raw_path, cleaned_path):
        if path:
            try:
                os.remove(path)
            except FileNotFoundError:
                continue
            logger.info("Removed dataset file: %s", path)


def stage_dataset_deletion(
    dataset_id: str,
    raw_path: str | None = None,
    cleaned_path: str | None = None,
) -> tuple[str, str]:
    """Stage local files; Supabase references remain inaccessible while deletion is pending."""
    if (raw_path is None) != (cleaned_path is None):
        raise ValueError("Both raw and cleaned storage paths must be provided together.")
    if raw_path is None:
        raw_path, cleaned_path = get_dataset_paths(dataset_id)
    if _is_supabase_location(raw_path):
        return raw_path, cleaned_path

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
    """Permanently remove staged files or Supabase objects; failures remain retryable."""
    if any(_is_supabase_location(path) for path in staged_paths):
        delete_dataset_storage(*staged_paths)
        return

    for path in staged_paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
