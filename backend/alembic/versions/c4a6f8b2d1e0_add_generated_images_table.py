"""add generated_images table

Revision ID: c4a6f8b2d1e0
Revises: b8f9e7c1d2a3
Create Date: 2026-05-08 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4a6f8b2d1e0"
down_revision: Union[str, None] = "b8f9e7c1d2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_images",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("style", sa.String(length=50), server_default="realistic", nullable=False),
        sa.Column("size", sa.String(length=20), server_default="1024x1024", nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generated_images_message_id"), "generated_images", ["message_id"], unique=False)
    op.create_index(op.f("ix_generated_images_provider"), "generated_images", ["provider"], unique=False)
    op.create_index(op.f("ix_generated_images_session_id"), "generated_images", ["session_id"], unique=False)
    op.create_index(op.f("ix_generated_images_thread_id"), "generated_images", ["thread_id"], unique=False)
    op.create_index(op.f("ix_generated_images_user_id"), "generated_images", ["user_id"], unique=False)

    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE generated_images ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE generated_images FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.drop_index(op.f("ix_generated_images_user_id"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_thread_id"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_session_id"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_provider"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_message_id"), table_name="generated_images")
    op.drop_table("generated_images")
