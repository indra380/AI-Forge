"""add user_onboarding_logs table

Revision ID: f3b9d7a1c2e4
Revises: e7f4a2d9c1b0
Create Date: 2026-05-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3b9d7a1c2e4"
down_revision: Union[str, None] = "e7f4a2d9c1b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_onboarding_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("onboarding_status", sa.String(length=50), nullable=False, server_default="completed"),
        sa.Column("email_notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("slack_notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("workflow_execution_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_onboarding_logs_user_id", "user_onboarding_logs", ["user_id"])
    op.create_index("ix_user_onboarding_logs_created_at", "user_onboarding_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_onboarding_logs_created_at", table_name="user_onboarding_logs")
    op.drop_index("ix_user_onboarding_logs_user_id", table_name="user_onboarding_logs")
    op.drop_table("user_onboarding_logs")
