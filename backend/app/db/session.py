from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def build_async_engine_config(database_url: str) -> tuple[str, dict[str, str]]:
    """Return a sanitized asyncpg URL plus connect_args.

    asyncpg does not accept "sslmode" in URL query params. When present,
    move it to connect_args["ssl"]. For Supabase hosts, default SSL to require.
    """
    try:
        url = make_url(database_url)
    except Exception:
        return database_url, {}

    if url.drivername != "postgresql+asyncpg":
        return database_url, {}

    connect_args: dict[str, str] = {}
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode:
        connect_args["ssl"] = sslmode
    elif (url.host or "").endswith("supabase.com"):
        connect_args["ssl"] = "require"

    if query != dict(url.query):
        url = url.set(query=query)

    return str(url), connect_args


_database_url, _connect_args = build_async_engine_config(settings.DATABASE_URL)
engine = create_async_engine(_database_url, echo=False, connect_args=_connect_args)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session
