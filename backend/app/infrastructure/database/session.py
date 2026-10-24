import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger("intellinotes.database")

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DATABASE_ECHO, pool_pre_ping=True)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
            logger.debug("Request transaction committed")
        except Exception as error:
            await session.rollback()
            logger.debug("Request transaction rolled back error_type=%s", type(error).__name__)
            raise
        finally:
            await session.close()


async def init_db() -> None:
    import app.domain.models  # noqa: F401

    async with engine.begin() as conn:
        # API and indexing workers may start simultaneously on the same database.
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('intellinotes-schema-init'))"))
        # PostgreSQL must have the pgvector extension installed on the server.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()
