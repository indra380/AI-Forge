"""add advanced features: db_connections, image_rules, thread_context

Revision ID: a2b3c4d5e6f7
Revises: d9303bb5868b
Create Date: 2026-05-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "c4a6f8b2d1e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add context JSON column to chat_threads
    op.add_column(
        "chat_threads",
        sa.Column("context", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )

    # Create db_connections table
    op.create_table(
        "db_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("db_type", sa.String(50), nullable=False),
        sa.Column("host", sa.String(500), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database", sa.String(255), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("connection_string_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_db_connections_user_id", "db_connections", ["user_id"])

    # Create image_rules table
    op.create_table(
        "image_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rules", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_image_rules_user_id", "image_rules", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_image_rules_user_id", table_name="image_rules")
    op.drop_table("image_rules")
    op.drop_index("ix_db_connections_user_id", table_name="db_connections")
    op.drop_table("db_connections")
    op.drop_column("chat_threads", "context")
