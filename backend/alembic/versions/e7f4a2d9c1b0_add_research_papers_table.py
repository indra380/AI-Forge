"""add research_papers table for persisted research results

Revision ID: e7f4a2d9c1b0
Revises: a2b3c4d5e6f7
Create Date: 2026-05-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7f4a2d9c1b0"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("arxiv_id", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("authors", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("published", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("url", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_research_papers_user_id", "research_papers", ["user_id"])
    op.create_index("ix_research_papers_thread_id", "research_papers", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_research_papers_thread_id", table_name="research_papers")
    op.drop_index("ix_research_papers_user_id", table_name="research_papers")
    op.drop_table("research_papers")
