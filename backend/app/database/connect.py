from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# Supabase's transaction pooler hands each transaction to whichever server
# connection is free, so a statement prepared on one is missing on the next.
# Every connection we open turns psycopg's automatic preparing off.
NO_PREPARED_STATEMENTS = {"prepare_threshold": None}

# pool_pre_ping drops connections the server (or Supabase's pooler) closed
# while idle, instead of failing the next request on a dead socket.
engine = create_async_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    connect_args=NO_PREPARED_STATEMENTS,
)

# Each call creates a new session bound to the engine.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    # Deterministic constraint/index names, so Alembic migrations can refer to
    # (and drop) them by name instead of whatever Postgres auto-generated.
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


# FastAPI dependency: one session per request, closed afterwards.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session