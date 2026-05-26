"""enable RLS on all tables

Revision ID: a1b2c3d4e5f6
Revises: d9303bb5868b
Create Date: 2026-05-07 00:00:00.000000

Enables Row Level Security on users, chat_threads, and chat_messages so that
Supabase's public Data API (PostgREST / anon role) cannot read or write any
rows directly.  The FastAPI backend connects as the postgres superuser and is
NOT subject to RLS, so application behaviour is unchanged.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d9303bb5868b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = ("users", "chat_threads", "chat_messages")


def upgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
