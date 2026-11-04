from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_phase3_initial"
down_revision = None
branch_labels = None
depends_on = None


def _tables():
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table_name):
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}


def _create_index(table_name, name, columns):
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns)


def upgrade():
    tables = _tables()
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "revoked_sessions" not in tables:
        op.create_table(
            "revoked_sessions",
            sa.Column("token_hash", sa.String(length=64), primary_key=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "datasets" not in tables:
        op.create_table(
            "datasets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False),
            sa.Column("raw_storage_path", sa.String(length=512), nullable=False),
            sa.Column("cleaned_storage_path", sa.String(length=512), nullable=False),
            sa.Column("upload_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deletion_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("columns_json", sa.Text()),
            sa.Column("numeric_columns_json", sa.Text()),
            sa.Column("date_columns_json", sa.Text()),
            sa.Column("summary_json", sa.Text()),
            sa.Column("preview_json", sa.Text()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
    elif "deletion_pending" not in {
        column["name"] for column in inspect(op.get_bind()).get_columns("datasets")
    }:
        op.add_column(
            "datasets",
            sa.Column("deletion_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    tables = _tables()
    if "login_rate_limits" not in tables:
        op.create_table(
            "login_rate_limits",
            sa.Column("key", sa.String(length=64), primary_key=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        )

    _create_index("revoked_sessions", "ix_revoked_sessions_expires_at", ["expires_at"])
    _create_index("datasets", "ix_datasets_user_id", ["user_id"])
    _create_index("datasets", "ix_datasets_expires_at", ["expires_at"])
    _create_index(
        "login_rate_limits",
        "ix_login_rate_limits_window_started_at",
        ["window_started_at"],
    )
    if "ix_users_email" not in _indexes("users"):
        op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade():
    tables = _tables()
    if "login_rate_limits" in tables:
        op.drop_table("login_rate_limits")
    if "datasets" in tables:
        op.drop_table("datasets")
    if "revoked_sessions" in tables:
        op.drop_table("revoked_sessions")
    if "users" in tables:
        op.drop_table("users")
