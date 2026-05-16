"""Database connection management service.

Stores encrypted credentials per user; builds connection strings for LangChain SQL agent.
"""
import base64
import hashlib
import re
import uuid
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db_connection import DbConnection


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _fernet_key() -> bytes:
    """Derive a Fernet-compatible 32-byte key from SECRET_KEY."""
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _encrypt(value: str) -> str:
    return Fernet(_fernet_key()).encrypt(value.encode()).decode()


def _decrypt(token: str) -> str:
    return Fernet(_fernet_key()).decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Connection string builder
# ---------------------------------------------------------------------------

SUPPORTED_DB_TYPES = {"postgresql", "mysql", "mssql", "sqlite"}


def build_sync_connection_string(conn: DbConnection) -> str:
    """Return a synchronous SQLAlchemy URL for the given connection record."""
    if conn.connection_string_encrypted:
        return _decrypt(conn.connection_string_encrypted)

    db_type = conn.db_type.lower()
    password = _decrypt(conn.encrypted_password) if conn.encrypted_password else ""
    username = conn.username or ""
    host = conn.host or "localhost"
    port = conn.port or _default_port(db_type)
    database = conn.database or ""

    if db_type == "postgresql":
        return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
    if db_type == "mysql":
        return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
    if db_type == "mssql":
        return f"mssql+pyodbc://{username}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
    if db_type == "sqlite":
        return f"sqlite:///{database}"
    raise ValueError(f"Unsupported db_type: {db_type}")


def _default_port(db_type: str) -> int:
    return {"postgresql": 5432, "mysql": 3306, "mssql": 1433}.get(db_type, 5432)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def save_db_connection(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    db_type: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    database: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    full_url: Optional[str] = None,
) -> DbConnection:
    """Persist a new DB connection with encrypted credentials."""
    if db_type.lower() not in SUPPORTED_DB_TYPES:
        raise ValueError(f"Unsupported db_type '{db_type}'. Supported: {SUPPORTED_DB_TYPES}")

    conn = DbConnection(
        user_id=user_id,
        name=name,
        db_type=db_type.lower(),
        host=host,
        port=port,
        database=database,
        username=username,
        encrypted_password=_encrypt(password) if password else None,
        connection_string_encrypted=_encrypt(full_url) if full_url else None,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


async def list_db_connections(db: AsyncSession, user_id: uuid.UUID) -> list[DbConnection]:
    result = await db.execute(select(DbConnection).where(DbConnection.user_id == user_id))
    return list(result.scalars().all())


async def get_db_connection(
    db: AsyncSession, connection_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[DbConnection]:
    result = await db.execute(
        select(DbConnection).where(
            DbConnection.id == connection_id,
            DbConnection.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_db_connection(
    db: AsyncSession, connection_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    conn = await get_db_connection(db, connection_id, user_id)
    if not conn:
        return False
    await db.delete(conn)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Connection string parsing (from chat command)
# ---------------------------------------------------------------------------

def parse_connect_command(text: str) -> dict:
    """Parse /connect-db command arguments into a connection dict.

    Supports both key=value syntax and full URL syntax:
      /connect-db postgresql://user:pass@host:5432/db name="My DB"
      /connect-db type=postgresql host=localhost port=5432 database=mydb user=admin password=secret name="My DB"
    """
    # Strip the command prefix
    body = re.sub(r"^/connect[\-_]?db\s*", "", text.strip(), flags=re.IGNORECASE).strip()

    # Try full URL syntax first
    url_match = re.match(r"^(postgresql|mysql|mssql|sqlite)(\+\w+)?://([^\s]+)", body)
    if url_match:
        full_url = url_match.group(0)
        # Extract optional name= after URL
        name_match = re.search(r'name=["\']?([^"\']+)["\']?', body)
        return {
            "full_url": full_url,
            "name": name_match.group(1) if name_match else "My Database",
            "db_type": url_match.group(1),
        }

    # Key=value syntax
    result: dict = {}
    for match in re.finditer(r'(\w+)=["\']?([^"\'"\s]+)["\']?', body):
        key, val = match.group(1).lower(), match.group(2)
        result[key] = val

    # Support aliases
    if "type" in result:
        result["db_type"] = result.pop("type")
    if "user" in result:
        result["username"] = result.pop("user")
    if "pass" in result:
        result["password"] = result.pop("pass")
    if "db" in result:
        result["database"] = result.pop("db")

    if "port" in result:
        result["port"] = int(result["port"])

    if "name" not in result:
        result["name"] = result.get("database", "My Database")

    return result
