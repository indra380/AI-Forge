from app.db.session import Base, engine
from app.models import ChatMessage, User  # noqa: F401


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
