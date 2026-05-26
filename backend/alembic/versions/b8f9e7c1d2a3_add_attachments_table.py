"""add attachments table

Revision ID: b8f9e7c1d2a3
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8f9e7c1d2a3"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("attachment_type", sa.String(length=50), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attachments_attachment_type"), "attachments", ["attachment_type"], unique=False)
    op.create_index(op.f("ix_attachments_message_id"), "attachments", ["message_id"], unique=False)
    op.create_index(op.f("ix_attachments_session_id"), "attachments", ["session_id"], unique=False)
    op.create_index(op.f("ix_attachments_user_id"), "attachments", ["user_id"], unique=False)

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE attachments ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE attachments FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.drop_index(op.f("ix_attachments_user_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_session_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_message_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_attachment_type"), table_name="attachments")
    op.drop_table("attachments")