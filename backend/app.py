"""
app.py – CSV Analytics Dashboard backend (Phase 3 hardened).

Phase 3 enhancements:
  - Database persistence via SQLAlchemy (SQLite for local dev, PostgreSQL in deployment).
  - Secure backend authentication (NIST-approved password hashing, HTTP-only session cookies).
  - Multi-tenant tenant isolation and strict dataset ownership enforcement.
  - Transparent persistence: datasets survive backend process restarts and multi-worker setups.
  - Safe dataset lifecycle management and configurable expiration.
  - Full backwards compatibility with all Phase 1 & Phase 2 analytical contracts.
"""

from datetime import datetime, timezone
import hmac
import io
import json
import logging
import os
import re
import uuid

import pandas as pd
from flask import Flask, g, jsonify, request, send_file
from flask_cors import CORS
from urllib.parse import urlsplit
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

import config
from auth import (
    clear_auth_cookie,
    generate_auth_token,
    generate_csrf_token,
    hash_password,
    login_required,
    revoke_auth_token,
    set_auth_cookie,
    validate_email_format,
    verify_password,
    verify_csrf_token,
)
from database import SessionLocal, init_app_db
from dataset_service import (
    MEMORY_CACHE,
    RAW_MEMORY_CACHE,
    cleanup_expired_datasets,
    delete_user_dataset,
    get_accessible_dataset,
    list_user_datasets,
    save_user_dataset,
)
from models import BusinessReport, Dataset, User
from rate_limiter import clear_login_attempts, consume_login_attempt
from report_service import create_business_report
from storage import get_report_path
from analytics.data_quality import (
    compute_column_profiling,
    compute_dataset_overview,
    detect_date_columns,
    generate_quality_report,
)
from analytics.business_intelligence import (
    calculate_business_kpis,
    calculate_date_trends,
    calculate_group_analysis,
    calculate_period_over_period,
    discover_business_kpis,
    generate_deterministic_insights,
)
from analytics.ai_analyst import analyze_question
from analytics.forecasting import forecast_series
from analytics.root_cause import analyze_root_cause

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
logger = logging.getLogger("csv_dashboard")

# Upload size limit (enforced before any handler runs)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
app.config["SECRET_KEY"] = config.SECRET_KEY

# CORS – Configured with explicit origins and credentials support
allowed_cors_origins = (
    config.ALLOWED_ORIGINS
    if config.FLASK_ENV == "production"
    else list(set(list(config.ALLOWED_ORIGINS) + ["http://localhost:5173", "http://127.0.0.1:5173"]))
)

CORS(
    app,
    resources={r"/*": {"origins": allowed_cors_origins}},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-CSRF-Token"],
    supports_credentials=True,
)

# Ensure upload and storage folders exist
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Initialize database
init_app_db(app)

# In-memory dictionary references for full backwards compatibility
DATASETS = MEMORY_CACHE
RAW_DATASETS = RAW_MEMORY_CACHE

# Allowlist of valid chart types
ALLOWED_CHART_TYPES: frozenset = frozenset({"Bar", "Line", "Pie", "Scatter", "Histogram"})

# UUID pattern for dataset_id validation
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@app.teardown_appcontext
def remove_db_session(exception=None):
    """Ensure database sessions are removed and returned to the pool after each request."""
    SessionLocal.remove()


@app.before_request
def enforce_cookie_csrf():
    """Require a signed CSRF token and trusted browser origin for unsafe cookie requests."""
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return None

    origin = request.headers.get("Origin", "").rstrip("/")
    if not origin:
        referer = request.headers.get("Referer")
        if referer:
            parsed = urlsplit(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""

    if origin and origin not in allowed_cors_origins:
        return _error("CSRF_ORIGIN_INVALID", "Request origin is not trusted.", 403)

    session_token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not session_token:
        return None

    if request.endpoint in {"login", "register"}:
        return None

    if not origin or origin not in allowed_cors_origins:
        return _error("CSRF_ORIGIN_INVALID", "A trusted Origin or Referer is required.", 403)
    if not verify_csrf_token(
        session_token,
        request.headers.get("X-CSRF-Token", ""),
    ):
        return _error("CSRF_TOKEN_INVALID", "A valid CSRF token is required.", 403)
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(code: str, message: str, http_status: int):
    """Return a structured JSON error response."""
    return jsonify({"error": {"code": code, "message": message}}), http_status


def _is_valid_uuid(value: str) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _allowed_extension(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[-1].lower() in config.ALLOWED_EXTENSIONS
    )


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply standard data-cleaning policy:
      1. Strip whitespace from column names.
      2. Drop duplicate rows.
      3. Drop all-empty rows.
      4. Fill numeric NaN with column mean.
      5. Fill text NaN with 'Unknown'.
    """
    df = df.copy()
    normalized_columns = [
        column.strip() if isinstance(column, str) else column
        for column in df.columns
    ]
    unique_columns = []
    seen_columns = set()
    for column in normalized_columns:
        candidate = column
        suffix = 2
        while candidate in seen_columns:
            candidate = f"{column}_{suffix}"
            suffix += 1
        unique_columns.append(candidate)
        seen_columns.add(candidate)
    df.columns = unique_columns
    df = df.drop_duplicates()
    df = df.dropna(how="all")

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].fillna(df[col].mean())
        else:
            df[col] = df[col].fillna("Unknown")

    return df


def _resolve_dataset(raw_dataset_id: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None, tuple | None]:
    """
    Validate dataset ID and authorize ownership for the current authenticated user.
    Returns (cleaned_df, raw_df, None) or (None, None, (response, status)).
    """
    if not raw_dataset_id:
        return None, None, _error("MISSING_DATASET_ID", "dataset_id is required.", 400)
    if not _is_valid_uuid(raw_dataset_id):
        return None, None, _error("INVALID_DATASET_ID", "dataset_id must be a valid UUID.", 400)

    user_id = getattr(g, "current_user", None)
    current_uid = user_id.id if user_id else None

    cleaned_df, raw_df, err = get_accessible_dataset(raw_dataset_id, current_uid)
    if err:
        return None, None, err

    return cleaned_df, raw_df, None


# ---------------------------------------------------------------------------
# Centralised error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(400)
def bad_request(e):
    logger.warning("400 Bad Request: %s", e)
    return _error("BAD_REQUEST", str(e), 400)


@app.errorhandler(404)
def not_found(e):
    return _error("NOT_FOUND", "The requested resource was not found.", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return _error("METHOD_NOT_ALLOWED", "HTTP method not allowed for this route.", 405)


@app.errorhandler(413)
@app.errorhandler(RequestEntityTooLarge)
def file_too_large(e):
    limit_mb = config.MAX_UPLOAD_BYTES / (1024 * 1024)
    logger.warning("413 – upload exceeds %.1f MB limit", limit_mb)
    return _error(
        "FILE_TOO_LARGE",
        f"The uploaded file exceeds the permitted size limit of {limit_mb:.0f} MB.",
        413,
    )


@app.errorhandler(415)
def unsupported_media(e):
    return _error("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type.", 415)


@app.errorhandler(500)
def internal_error(e):
    logger.error("500 Internal Server Error: %s", e, exc_info=True)
    return _error("INTERNAL_ERROR", "An unexpected server error occurred.", 500)


# ---------------------------------------------------------------------------
# Health Check Endpoint
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    """Health check / root endpoint."""
    return jsonify({"message": "Backend is running"})


# ---------------------------------------------------------------------------
# Phase 3 Authentication Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/auth/register", methods=["POST"])
def register():
    """
    POST /api/auth/register
    Body (JSON): email, password
    Registers a new user and sets a secure HTTP-only session cookie.
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("INVALID_REQUEST", "Request body must be a JSON object.", 400)

    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str):
        return _error("INVALID_EMAIL", "Email must be a string.", 400)
    if not isinstance(password, str):
        return _error("INVALID_PASSWORD", "Password must be a string.", 400)
    email = email.strip().lower()

    if not email:
        return _error("MISSING_EMAIL", "Email is required.", 400)
    if not validate_email_format(email):
        return _error("INVALID_EMAIL", "Please enter a valid email address.", 400)
    if not password:
        return _error("MISSING_PASSWORD", "Password is required.", 400)
    if len(password) < 6:
        return _error("WEAK_PASSWORD", "Password must be at least 6 characters.", 400)

    db = SessionLocal()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return _error("USER_EXISTS", "An account with this email already exists.", 409)

    user = User(
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = generate_auth_token(user.id)
    response = jsonify({
        "message": "Registration successful.",
        "user": user.to_dict(),
        "csrf_token": generate_csrf_token(token),
    })
    return set_auth_cookie(response, token), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    """
    POST /api/auth/login
    Body (JSON): email, password
    Authenticates user and returns an HTTP-only session cookie.
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("INVALID_REQUEST", "Request body must be a JSON object.", 400)

    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str):
        return _error("INVALID_EMAIL", "Email must be a string.", 400)
    if not isinstance(password, str):
        return _error("INVALID_PASSWORD", "Password must be a string.", 400)
    email = email.strip().lower()

    if not email or not password:
        return _error("INVALID_CREDENTIALS", "Email and password are required.", 400)

    allowed, retry_after = consume_login_attempt(email, request.remote_addr)
    if not allowed:
        response, status = _error(
            "RATE_LIMITED",
            "Too many login attempts. Please wait before trying again.",
            429,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response, status

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(user.password_hash, password):
        return _error("INVALID_CREDENTIALS", "Invalid email or password.", 401)

    clear_login_attempts(email, request.remote_addr)
    token = generate_auth_token(user.id)
    response = jsonify({
        "message": "Login successful.",
        "user": user.to_dict(),
        "csrf_token": generate_csrf_token(token),
    })
    return set_auth_cookie(response, token), 200


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """
    POST /api/auth/logout
    Invalidates session by clearing the authentication cookie.
    """
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    revoke_auth_token(token)

    response = jsonify({"message": "Logged out successfully."})
    return clear_auth_cookie(response), 200


@app.route("/api/auth/me", methods=["GET"])
@login_required
def get_current_user_profile():
    """
    GET /api/auth/me
    Returns current authenticated user details.
    """
    session_token = request.cookies.get(config.SESSION_COOKIE_NAME, "")
    return jsonify({
        "user": g.current_user.to_dict(),
        "csrf_token": generate_csrf_token(session_token),
    }), 200


@app.route("/api/auth/csrf", methods=["GET"])
@login_required
def get_csrf_token():
    session_token = request.cookies.get(config.SESSION_COOKIE_NAME, "")
    return jsonify({"csrf_token": generate_csrf_token(session_token)}), 200


@app.route("/api/datasets/cleanup", methods=["POST"])
def trigger_dataset_cleanup():
    """
    POST /api/datasets/cleanup
    Administrative/cron endpoint to safely clean up expired datasets.
    """
    configured_token = config.DATASET_CLEANUP_TOKEN
    auth_header = request.headers.get("Authorization", "")
    supplied_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not supplied_token:
        if request.cookies.get(config.SESSION_COOKIE_NAME):
            return _error("FORBIDDEN", "Administrator authorization is required.", 403)
        return _error("UNAUTHORIZED", "Administrator authorization is required.", 401)
    if not configured_token:
        return _error("CLEANUP_DISABLED", "Administrative cleanup is not configured.", 503)
    if not hmac.compare_digest(supplied_token, configured_token):
        return _error("FORBIDDEN", "Administrator authorization is required.", 403)

    count = cleanup_expired_datasets()
    return jsonify({"cleaned_datasets": count})


@app.route("/api/datasets", methods=["GET"])
@login_required
def list_datasets_endpoint():
    """List non-expired datasets owned by the authenticated user."""
    return jsonify({"datasets": list_user_datasets(g.current_user.id)})


@app.route("/api/datasets/<dataset_id>", methods=["DELETE"])
@login_required
def delete_dataset_endpoint(dataset_id):
    """Safely delete one dataset owned by the authenticated user."""
    if not _is_valid_uuid(dataset_id):
        return _error("INVALID_DATASET_ID", "dataset_id must be a valid UUID.", 400)
    deleted, error = delete_user_dataset(dataset_id, g.current_user.id)
    if error:
        return error
    return jsonify({"message": "Dataset deleted.", "dataset_id": dataset_id}), 200


# ---------------------------------------------------------------------------
# Core Analytical Endpoints (Phase 1 & Phase 2 Protected)
# ---------------------------------------------------------------------------

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    """
    POST /upload
    Accepts multipart/form-data upload with field name 'file'.
    Stores metadata in database, persists raw & cleaned CSVs to disk,
    and caches in memory for immediate query availability.
    """
    if "file" not in request.files:
        logger.warning("Upload attempt without a file part")
        return _error("NO_FILE", "No file was included in the request.", 400)

    file = request.files["file"]

    if not file.filename:
        return _error("NO_FILENAME", "No filename provided.", 400)

    original_name = file.filename
    safe_name = secure_filename(original_name)

    if not safe_name or not _allowed_extension(safe_name):
        logger.warning("Rejected upload with unsupported extension: %s", original_name)
        return _error(
            "UNSUPPORTED_FORMAT",
            "Only CSV (.csv) and Excel (.xlsx) files are accepted.",
            400,
        )

    ext = safe_name.rsplit(".", 1)[-1].lower()

    file_bytes = file.read()
    if not file_bytes:
        return _error("EMPTY_FILE", "The uploaded file is empty.", 400)

    try:
        if ext == "csv":
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")
        else:  # xlsx
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
            except Exception as exc:
                logger.warning("Failed to read XLSX: %s", exc)
                return _error(
                    "INVALID_XLSX",
                    "The Excel file could not be read. It may be corrupt or use an unsupported format.",
                    400,
                )

        if df.empty or df.shape[1] == 0:
            return _error(
                "EMPTY_DATASET",
                "The file contains no data or no columns.",
                400,
            )

        if df.shape[1] < 1:
            return _error("INVALID_STRUCTURE", "The file has no usable columns.", 400)

        duplicate_rows = int(df.duplicated().sum())
        missing_values = int(df.isnull().sum().sum())

        cleaned_df = clean_data(df)
        dataset_id = str(uuid.uuid4())

        numeric_columns = cleaned_df.select_dtypes(include=["number"]).columns.tolist()
        date_columns = detect_date_columns(df)
        summary = {
            "total_rows": int(cleaned_df.shape[0]),
            "total_columns": int(cleaned_df.shape[1]),
            "duplicate_rows_removed": duplicate_rows,
            "missing_values_handled": missing_values,
        }
        preview = cleaned_df.head(20).to_dict(orient="records")

        # Persist to database & storage
        save_user_dataset(
            user_id=g.current_user.id,
            dataset_id=dataset_id,
            original_filename=safe_name,
            file_size_bytes=len(file_bytes),
            raw_df=df,
            cleaned_df=cleaned_df,
            numeric_columns=numeric_columns,
            date_columns=date_columns,
            summary=summary,
            preview=preview,
        )

        logger.info(
            "Uploaded dataset %s for user %s – rows=%d cols=%d",
            dataset_id,
            g.current_user.id,
            cleaned_df.shape[0],
            cleaned_df.shape[1],
        )

        return jsonify(
            {
                "dataset_id": dataset_id,
                "columns": cleaned_df.columns.tolist(),
                "numeric_columns": numeric_columns,
                "date_columns": date_columns,
                "summary": summary,
                "preview": preview,
            }
        )

    except pd.errors.ParserError as exc:
        logger.warning("CSV parse error: %s", exc)
        return _error(
            "PARSE_ERROR",
            "The CSV file could not be parsed. Check that it is a valid CSV.",
            400,
        )
    except Exception as exc:
        logger.error("Unexpected error during upload: %s", exc, exc_info=True)
        return _error("UPLOAD_FAILED", "File processing failed. Please try again.", 500)


@app.route("/chart-data", methods=["POST"])
@login_required
def chart_data():
    """
    POST /chart-data
    Body (JSON): dataset_id, chart_type, x_axis, y_axis
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    chart_type = data.get("chart_type")
    x_axis = data.get("x_axis")
    y_axis = data.get("y_axis")

    if not chart_type:
        return _error("MISSING_CHART_TYPE", "chart_type is required.", 400)
    if chart_type not in ALLOWED_CHART_TYPES:
        return _error(
            "INVALID_CHART_TYPE",
            f"chart_type must be one of: {', '.join(sorted(ALLOWED_CHART_TYPES))}.",
            400,
        )
    if not x_axis:
        return _error("MISSING_X_AXIS", "x_axis is required.", 400)

    if x_axis not in cleaned_df.columns:
        return _error(
            "INVALID_COLUMN",
            f"Column '{x_axis}' does not exist in the dataset.",
            400,
        )

    try:
        if chart_type == "Histogram":
            values = cleaned_df[x_axis].dropna().tolist()
            return jsonify({"labels": list(range(len(values))), "values": values})

        if not y_axis:
            return _error("MISSING_Y_AXIS", "y_axis is required for this chart type.", 400)
        if y_axis not in cleaned_df.columns:
            return _error(
                "INVALID_COLUMN",
                f"Column '{y_axis}' does not exist in the dataset.",
                400,
            )

        if chart_type == "Pie":
            chart_df = cleaned_df.groupby(x_axis)[y_axis].sum().reset_index()
            labels = chart_df[x_axis].astype(str).tolist()
            values = chart_df[y_axis].tolist()
        else:
            labels = cleaned_df[x_axis].astype(str).tolist()
            values = cleaned_df[y_axis].tolist()

        return jsonify({"labels": labels, "values": values})

    except Exception as exc:
        logger.error("Chart generation error: %s", exc, exc_info=True)
        return _error("CHART_ERROR", "Failed to generate chart data.", 500)


@app.route("/insights", methods=["POST"])
@login_required
def insights():
    """
    POST /insights
    Body (JSON): dataset_id, x_axis, y_axis
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    x_axis = data.get("x_axis")
    y_axis = data.get("y_axis")
    insights_list = []

    try:
        if y_axis and y_axis in cleaned_df.columns and pd.api.types.is_numeric_dtype(cleaned_df[y_axis]):
            insights_list.append(f"Total {y_axis}: {cleaned_df[y_axis].sum():,.2f}")
            insights_list.append(f"Average {y_axis}: {cleaned_df[y_axis].mean():,.2f}")
            insights_list.append(f"Maximum {y_axis}: {cleaned_df[y_axis].max():,.2f}")
            insights_list.append(f"Minimum {y_axis}: {cleaned_df[y_axis].min():,.2f}")

            if x_axis and x_axis in cleaned_df.columns:
                grouped = cleaned_df.groupby(x_axis)[y_axis].sum().sort_values(ascending=False)
                if not grouped.empty:
                    insights_list.append(
                        f"Top {x_axis}: {grouped.index[0]} with {grouped.iloc[0]:,.2f}"
                    )

        insights_list.append(f"Dataset rows: {cleaned_df.shape[0]}")
        insights_list.append(f"Dataset columns: {cleaned_df.shape[1]}")

        return jsonify({"insights": insights_list})

    except Exception as exc:
        logger.error("Insights error: %s", exc, exc_info=True)
        return _error("INSIGHTS_ERROR", "Failed to generate insights.", 500)


@app.route("/ask", methods=["POST"])
@login_required
def ask_data():
    """
    POST /ask
    Body (JSON): dataset_id, question
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    question_raw = data.get("question", "")
    if not isinstance(question_raw, str):
        return _error("INVALID_QUESTION", "question must be a string.", 400)

    question = question_raw.strip().lower()
    if not question:
        return _error("EMPTY_QUESTION", "question cannot be empty.", 400)

    try:
        numeric_columns = cleaned_df.select_dtypes(include=["number"]).columns.tolist()
        text_columns = cleaned_df.select_dtypes(include=["object", "string"]).columns.tolist()

        if "how many" in question or ("count" in question and "rows" not in question):
            metric_keywords = [
                "hundred", "hundreds", "century", "centuries",
                "fifty", "fifties", "wicket", "wickets",
            ]
            metric_col = None
            for col in numeric_columns:
                col_lower = col.lower()
                if any(kw in col_lower for kw in metric_keywords):
                    metric_col = col
                    break

            filtered_df = cleaned_df.copy()
            matched_value = None
            question_words = question.split()

            for text_col in text_columns:
                unique_values = cleaned_df[text_col].unique()
                for val in unique_values:
                    val_str = str(val).lower()
                    for q_word in question_words:
                        if q_word in val_str or val_str in q_word:
                            filtered_df = cleaned_df[cleaned_df[text_col].str.lower() == val_str]
                            matched_value = val
                            break
                    if 0 < len(filtered_df) < len(cleaned_df):
                        break
                if 0 < len(filtered_df) < len(cleaned_df):
                    break

            if metric_col:
                count = int(filtered_df[metric_col].sum())
                metric_name = metric_col
            else:
                count = len(filtered_df)
                metric_name = "records"

            if matched_value:
                answer = f"There are {count} {metric_name} in {matched_value} format."
            else:
                answer = f"Found {count} {metric_name} matching your criteria."

            return jsonify({"answer": answer, "table": []})

        if "count" in question or "rows" in question:
            return jsonify({"answer": f"Total rows: {cleaned_df.shape[0]}", "table": []})

        if "columns" in question:
            return jsonify({"answer": f"Columns: {', '.join(cleaned_df.columns)}", "table": []})

        if not numeric_columns:
            return jsonify({"answer": "No numeric column found.", "table": []})

        number_col = numeric_columns[0]
        text_col = text_columns[0] if text_columns else None

        for col in numeric_columns:
            if col.lower() in question:
                number_col = col

        for col in text_columns:
            if col.lower() in question:
                text_col = col

        if "average" in question or "avg" in question:
            return jsonify(
                {"answer": f"Average {number_col}: {cleaned_df[number_col].mean():,.2f}", "table": []}
            )

        if "total" in question or "sum" in question:
            return jsonify(
                {"answer": f"Total {number_col}: {cleaned_df[number_col].sum():,.2f}", "table": []}
            )

        if "maximum" in question or "max" in question or "highest" in question:
            return jsonify(
                {"answer": f"Maximum {number_col}: {cleaned_df[number_col].max():,.2f}", "table": []}
            )

        if "minimum" in question or "min" in question or "lowest" in question:
            return jsonify(
                {"answer": f"Minimum {number_col}: {cleaned_df[number_col].min():,.2f}", "table": []}
            )

        if "top" in question and text_col:
            n = 5
            for word in question.split():
                if word.isdigit():
                    n = int(word)

            result = (
                cleaned_df.groupby(text_col)[number_col]
                .sum()
                .sort_values(ascending=False)
                .head(n)
                .reset_index()
            )
            return jsonify(
                {
                    "answer": f"Top {n} {text_col} by {number_col}",
                    "table": result.to_dict(orient="records"),
                }
            )

        return jsonify(
            {
                "answer": (
                    "Try: how many hundreds in t20, count centuries by format, "
                    "top 5 products by sales, average sales, total revenue, "
                    "count rows, show columns."
                ),
                "table": [],
            }
        )

    except Exception as exc:
        logger.error("Ask error: %s", exc, exc_info=True)
        return _error("ASK_ERROR", "Failed to process your question.", 500)


@app.route("/download/<dataset_id>", methods=["GET"])
@login_required
def download(dataset_id):
    """
    GET /download/<dataset_id>
    Streams the cleaned CSV dataset for the authenticated user.
    """
    cleaned_df, _, err = _resolve_dataset(dataset_id)
    if err:
        return err

    try:
        buffer = io.BytesIO()
        cleaned_df.to_csv(buffer, index=False, encoding="utf-8")
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name="cleaned_data.csv",
            mimetype="text/csv",
        )
    except Exception as exc:
        logger.error("Download error for dataset %s: %s", dataset_id, exc, exc_info=True)
        return _error("DOWNLOAD_FAILED", "Failed to prepare the download.", 500)


@app.route("/api/data-quality", methods=["GET", "POST"])
@login_required
def data_quality_endpoint():
    """
    GET /api/data-quality?dataset_id=<uuid>
    POST /api/data-quality  Body: {"dataset_id": "<uuid>"}
    """
    if request.method == "POST":
        if not request.is_json:
            return _error("NOT_JSON", "Request body must be JSON.", 415)
        data = request.get_json(silent=True) or {}
        raw_id = data.get("dataset_id")
    else:
        raw_id = request.args.get("dataset_id")

    cleaned_df, raw_df, err = _resolve_dataset(raw_id)
    if err:
        return err

    try:
        # Prefer raw uncleaned dataset to assess true missingness and duplicates
        target_df = raw_df if raw_df is not None else cleaned_df
        report = generate_quality_report(target_df)
        return jsonify(report)
    except Exception as exc:
        logger.error("Data quality report failed: %s", exc, exc_info=True)
        return _error("DATA_QUALITY_ERROR", "Failed to generate data quality report.", 500)


@app.route("/api/data-profile", methods=["GET", "POST"])
@login_required
def data_profile_endpoint():
    """
    GET /api/data-profile?dataset_id=<uuid>
    POST /api/data-profile  Body: {"dataset_id": "<uuid>"}
    """
    if request.method == "POST":
        if not request.is_json:
            return _error("NOT_JSON", "Request body must be JSON.", 415)
        data = request.get_json(silent=True) or {}
        raw_id = data.get("dataset_id")
    else:
        raw_id = request.args.get("dataset_id")

    cleaned_df, raw_df, err = _resolve_dataset(raw_id)
    if err:
        return err

    try:
        target_df = raw_df if raw_df is not None else cleaned_df
        return jsonify({
            "overview": compute_dataset_overview(target_df),
            "column_profiles": compute_column_profiling(target_df),
        })
    except Exception as exc:
        logger.error("Data profiling failed: %s", exc, exc_info=True)
        return _error("DATA_PROFILE_ERROR", "Failed to profile dataset.", 500)


@app.route("/api/bi/kpis", methods=["POST"])
@login_required
def bi_kpis_endpoint():
    """
    POST /api/bi/kpis
    Body: {"dataset_id": "...", "revenue_col": "...", "profit_col": "...", ...}
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    revenue_col = data.get("revenue_col")
    profit_col = data.get("profit_col")
    quantity_col = data.get("quantity_col")
    order_id_col = data.get("order_id_col")
    discount_col = data.get("discount_col")

    for name, val in [
        ("revenue_col", revenue_col),
        ("profit_col", profit_col),
        ("quantity_col", quantity_col),
        ("order_id_col", order_id_col),
        ("discount_col", discount_col),
    ]:
        if val and val not in cleaned_df.columns:
            return _error("INVALID_COLUMN", f"Column '{val}' specified in '{name}' does not exist.", 400)

    try:
        discovery = discover_business_kpis(cleaned_df)
        kpis = calculate_business_kpis(
            df=cleaned_df,
            revenue_col=revenue_col,
            profit_col=profit_col,
            quantity_col=quantity_col,
            order_id_col=order_id_col,
            discount_col=discount_col,
        )
        insights_res = generate_deterministic_insights(
            df=cleaned_df,
            revenue_col=revenue_col,
            profit_col=profit_col,
        )
        return jsonify({
            "discovery": discovery,
            "kpis": kpis,
            "insights": insights_res,
        })
    except Exception as exc:
        logger.error("BI KPI calculation failed: %s", exc, exc_info=True)
        return _error("BI_KPI_ERROR", "Failed to calculate business KPIs.", 500)


@app.route("/api/bi/group-analysis", methods=["POST"])
@login_required
def bi_group_analysis_endpoint():
    """
    POST /api/bi/group-analysis
    Body: {"dataset_id": "...", "group_col": "...", "measure_col": "...", "aggregation": "sum"}
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    group_col = data.get("group_col")
    measure_col = data.get("measure_col")
    aggregation = data.get("aggregation", "sum")
    limit = data.get("limit", 50)

    if not group_col:
        return _error("MISSING_GROUP_COL", "group_col is required.", 400)
    if not measure_col:
        return _error("MISSING_MEASURE_COL", "measure_col is required.", 400)

    if group_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", f"Group column '{group_col}' does not exist in dataset.", 400)
    if measure_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", f"Measure column '{measure_col}' does not exist in dataset.", 400)

    valid_aggs = {"sum", "mean", "median", "count", "min", "max"}
    if str(aggregation).lower() not in valid_aggs:
        return _error(
            "INVALID_AGGREGATION",
            f"aggregation must be one of: {', '.join(sorted(valid_aggs))}.",
            400,
        )

    try:
        res = calculate_group_analysis(
            df=cleaned_df,
            group_col=group_col,
            measure_col=measure_col,
            aggregation=aggregation,
            limit=limit,
        )
        return jsonify(res)
    except Exception as exc:
        logger.error("Group analysis error: %s", exc, exc_info=True)
        return _error("GROUP_ANALYSIS_ERROR", "Failed to perform group analysis.", 500)


@app.route("/api/bi/trends", methods=["POST"])
@login_required
def bi_trends_endpoint():
    """
    POST /api/bi/trends
    Body: {"dataset_id": "...", "date_col": "...", "measure_col": "...", "granularity": "monthly", "aggregation": "sum"}
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    date_col = data.get("date_col")
    measure_col = data.get("measure_col")
    granularity = data.get("granularity", "monthly")
    aggregation = data.get("aggregation", "sum")

    if not date_col:
        return _error("MISSING_DATE_COL", "date_col is required.", 400)
    if not measure_col:
        return _error("MISSING_MEASURE_COL", "measure_col is required.", 400)

    if date_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", f"Date column '{date_col}' does not exist.", 400)
    if measure_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", f"Measure column '{measure_col}' does not exist.", 400)

    valid_granularities = {"daily", "weekly", "monthly", "quarterly", "yearly"}
    if str(granularity).lower() not in valid_granularities:
        return _error(
            "INVALID_GRANULARITY",
            f"granularity must be one of: {', '.join(sorted(valid_granularities))}.",
            400,
        )

    valid_aggs = {"sum", "mean", "median", "count", "min", "max"}
    if str(aggregation).lower() not in valid_aggs:
        return _error(
            "INVALID_AGGREGATION",
            f"aggregation must be one of: {', '.join(sorted(valid_aggs))}.",
            400,
        )

    try:
        trends = calculate_date_trends(
            df=cleaned_df,
            date_col=date_col,
            measure_col=measure_col,
            aggregation=aggregation,
            granularity=granularity,
        )
        return jsonify(trends)
    except Exception as exc:
        logger.error("Date trends error: %s", exc, exc_info=True)
        return _error("TRENDS_ERROR", "Failed to calculate trends.", 500)


@app.route("/api/bi/period-comparison", methods=["POST"])
@login_required
def bi_period_comparison_endpoint():
    """
    POST /api/bi/period-comparison
    Body: {"dataset_id": "...", "date_col": "...", "measure_col": "...", "granularity": "monthly", "aggregation": "sum"}
    """
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err

    date_col = data.get("date_col")
    measure_col = data.get("measure_col")
    granularity = data.get("granularity", "monthly")
    aggregation = data.get("aggregation", "sum")

    if not date_col:
        return _error("MISSING_DATE_COL", "date_col is required.", 400)
    if not measure_col:
        return _error("MISSING_MEASURE_COL", "measure_col is required.", 400)

    if date_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", f"Date column '{date_col}' does not exist.", 400)
    if measure_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", f"Measure column '{measure_col}' does not exist.", 400)

    try:
        pop = calculate_period_over_period(
            df=cleaned_df,
            date_col=date_col,
            measure_col=measure_col,
            aggregation=aggregation,
            granularity=granularity,
        )
        return jsonify(pop)
    except Exception as exc:
        logger.error("Period comparison error: %s", exc, exc_info=True)
        return _error("PERIOD_COMPARISON_ERROR", "Failed to calculate period comparison.", 500)


@app.route("/api/ai/analyze", methods=["POST"])
@login_required
def ai_analyze_endpoint():
    """Answer a supported natural-language question using calculated dataset evidence."""
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err
    question = data.get("question")
    if not isinstance(question, str) or not question.strip():
        return _error("INVALID_QUESTION", "A non-empty question is required.", 400)

    try:
        return jsonify(analyze_question(cleaned_df, question))
    except ValueError as exc:
        return _error("UNSUPPORTED_ANALYSIS", str(exc), 400)
    except RuntimeError as exc:
        logger.error("Configured AI explanation provider failed: %s", exc)
        return _error("AI_PROVIDER_ERROR", str(exc), 502)
    except Exception as exc:
        logger.error("AI analysis failed: %s", exc, exc_info=True)
        return _error("AI_ANALYSIS_ERROR", "Failed to analyze the question.", 500)


@app.route("/api/analytics/root-cause", methods=["POST"])
@login_required
def root_cause_endpoint():
    """Compare two observed periods and decompose change by selected dimensions."""
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err
    date_col = data.get("date_col")
    measure_col = data.get("measure_col")
    dimensions = data.get("dimensions")
    if not isinstance(date_col, str) or not date_col:
        return _error("MISSING_DATE_COL", "date_col is required.", 400)
    if not isinstance(measure_col, str) or not measure_col:
        return _error("MISSING_MEASURE_COL", "measure_col is required.", 400)
    if dimensions is not None and (
        not isinstance(dimensions, list)
        or any(not isinstance(item, str) for item in dimensions)
    ):
        return _error("INVALID_DIMENSIONS", "dimensions must be a list of column names.", 400)
    if date_col not in cleaned_df.columns or measure_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", "The selected date or measure column does not exist.", 400)

    try:
        result = analyze_root_cause(
            cleaned_df,
            date_col=date_col,
            measure_col=measure_col,
            dimensions=dimensions,
            granularity=data.get("granularity", "monthly"),
            top_n=data.get("top_n", 10),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error("ROOT_CAUSE_UNAVAILABLE", str(exc), 400)
    except Exception as exc:
        logger.error("Root-cause analysis failed: %s", exc, exc_info=True)
        return _error("ROOT_CAUSE_ERROR", "Failed to calculate root-cause contributors.", 500)


@app.route("/api/analytics/forecast", methods=["POST"])
@login_required
def forecast_endpoint():
    """Generate an evaluated naive baseline forecast for the authenticated dataset."""
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, _, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err
    date_col = data.get("date_col")
    measure_col = data.get("measure_col")
    if not isinstance(date_col, str) or not isinstance(measure_col, str):
        return _error("INVALID_COLUMN", "date_col and measure_col are required.", 400)
    if date_col not in cleaned_df.columns or measure_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", "The selected date or measure column does not exist.", 400)

    try:
        return jsonify(
            forecast_series(
                cleaned_df,
                date_col=date_col,
                measure_col=measure_col,
                granularity=data.get("granularity", "monthly"),
                aggregation=data.get("aggregation", "sum"),
                horizon=data.get("horizon", 3),
            )
        )
    except ValueError as exc:
        return _error("FORECAST_UNAVAILABLE", str(exc), 400)
    except Exception as exc:
        logger.error("Forecast calculation failed: %s", exc, exc_info=True)
        return _error("FORECAST_ERROR", "Failed to calculate the forecast.", 500)


@app.route("/api/reports", methods=["POST"])
@login_required
def create_report_endpoint():
    """Generate an owner-scoped business report for the selected dataset."""
    if not request.is_json:
        return _error("NOT_JSON", "Request body must be JSON.", 415)

    data = request.get_json(silent=True) or {}
    cleaned_df, raw_df, err = _resolve_dataset(data.get("dataset_id"))
    if err:
        return err
    date_col = data.get("date_col")
    measure_col = data.get("measure_col")
    dimensions = data.get("dimensions")
    if date_col is not None and date_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", "The selected date column does not exist.", 400)
    if measure_col is not None and measure_col not in cleaned_df.columns:
        return _error("INVALID_COLUMN", "The selected measure column does not exist.", 400)
    if dimensions is not None and (
        not isinstance(dimensions, list)
        or any(not isinstance(item, str) or item not in cleaned_df.columns for item in dimensions)
    ):
        return _error("INVALID_DIMENSIONS", "dimensions must contain valid column names.", 400)
    horizon = data.get("horizon", 3)
    if not isinstance(horizon, int) or isinstance(horizon, bool) or not 1 <= horizon <= 24:
        return _error("INVALID_HORIZON", "horizon must be an integer from 1 to 24.", 400)
    options = {
        "date_col": date_col,
        "measure_col": measure_col,
        "dimensions": dimensions,
        "granularity": data.get("granularity", "monthly"),
        "horizon": horizon,
    }

    db = SessionLocal()
    try:
        dataset = db.get(Dataset, data.get("dataset_id"))
        if not dataset or dataset.user_id != g.current_user.id:
            return _error("DATASET_NOT_FOUND", "Dataset not found.", 404)
        owned_dataset_id = dataset.id
        dataset_name = dataset.original_filename
    finally:
        db.close()

    try:
        report = create_business_report(
            user_id=g.current_user.id,
            dataset_id=owned_dataset_id,
            dataset_name=dataset_name,
            raw_df=raw_df if raw_df is not None else cleaned_df,
            cleaned_df=cleaned_df,
            options=options,
        )
        return jsonify(
            {
                "report_id": report.id,
                "dataset_id": owned_dataset_id,
                "dataset_name": dataset_name,
                "created_at": report.created_at.isoformat(),
                "download_url": f"/api/reports/{report.id}/download",
            }
        ), 201
    except LookupError:
        return _error("DATASET_NOT_FOUND", "Dataset not found.", 404)
    except Exception as exc:
        logger.error("Could not generate business report: %s", exc, exc_info=True)
        return _error("REPORT_GENERATION_FAILED", "Could not generate the business report.", 500)


@app.route("/api/reports", methods=["GET"])
@login_required
def list_reports_endpoint():
    """List reports belonging to the authenticated user and still-active datasets."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        rows = (
            db.query(BusinessReport, Dataset.original_filename)
            .join(Dataset, BusinessReport.dataset_id == Dataset.id)
            .filter(
                BusinessReport.user_id == g.current_user.id,
                Dataset.user_id == g.current_user.id,
                Dataset.deletion_pending.is_(False),
                Dataset.expires_at > now,
            )
            .order_by(BusinessReport.created_at.desc())
            .all()
        )
        return jsonify(
            {
                "reports": [
                    {
                        "report_id": report.id,
                        "dataset_id": report.dataset_id,
                        "dataset_name": dataset_name,
                        "created_at": report.created_at.isoformat(),
                    }
                    for report, dataset_name in rows
                ]
            }
        )
    finally:
        db.close()


@app.route("/api/reports/<report_id>/download", methods=["GET"])
@login_required
def download_report_endpoint(report_id):
    """Download a generated report only when its user and dataset ownership match."""
    if not _is_valid_uuid(report_id):
        return _error("INVALID_REPORT_ID", "report_id must be a valid UUID.", 400)

    db = SessionLocal()
    try:
        report = db.get(BusinessReport, report_id)
        if not report or report.user_id != g.current_user.id:
            return _error("REPORT_NOT_FOUND", "Report not found.", 404)
        dataset = db.get(Dataset, report.dataset_id)
        if (
            not dataset
            or dataset.user_id != g.current_user.id
            or dataset.deletion_pending
        ):
            return _error("REPORT_NOT_FOUND", "Report not found.", 404)
        dataset_expiry = dataset.expires_at
        if dataset_expiry.tzinfo is None:
            dataset_expiry = dataset_expiry.replace(tzinfo=timezone.utc)
        if dataset_expiry <= datetime.now(timezone.utc):
            return _error("REPORT_NOT_FOUND", "Report not found.", 404)
        report_path = get_report_path(report.id)
    finally:
        db.close()

    if not os.path.isfile(report_path):
        logger.error("Generated report file is missing for report %s.", report_id)
        return _error("REPORT_FILE_MISSING", "The generated report is unavailable.", 404)
    try:
        return send_file(
            report_path,
            as_attachment=True,
            download_name=f"business_report_{report_id}.pdf",
            mimetype="application/pdf",
        )
    except OSError as exc:
        logger.error("Could not read generated report %s: %s", report_id, exc, exc_info=True)
        return _error("REPORT_DOWNLOAD_FAILED", "Could not read the generated report.", 500)


# ---------------------------------------------------------------------------
# Entry point (development only)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=config.PORT,
        debug=config.FLASK_DEBUG,
    )