"""Add user-owned generated business reports."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_business_reports"
down_revision = "0001_phase3_initial"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "business_reports" not in tables:
        op.create_table(
            "business_reports",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("dataset_id", sa.String(length=36), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        )
    existing_indexes = {
        index["name"] for index in inspect(op.get_bind()).get_indexes("business_reports")
    }
    if "ix_business_reports_user_id" not in existing_indexes:
        op.create_index("ix_business_reports_user_id", "business_reports", ["user_id"])
    if "ix_business_reports_dataset_id" not in existing_indexes:
        op.create_index("ix_business_reports_dataset_id", "business_reports", ["dataset_id"])


def downgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "business_reports" not in tables:
        return
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("business_reports")}
    if "ix_business_reports_dataset_id" in indexes:
        op.drop_index("ix_business_reports_dataset_id", table_name="business_reports")
    if "ix_business_reports_user_id" in indexes:
        op.drop_index("ix_business_reports_user_id", table_name="business_reports")
    op.drop_table("business_reports")
