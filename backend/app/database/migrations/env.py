"""Alembic environment. The database URL always comes from config.Settings,
so migrations target exactly the database the app would connect to."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import models  # noqa: F401 -- registers every table on Base.metadata
from app.database.connect import NO_PREPARED_STATEMENTS, Base
from config import settings

config = context.config
if config.config_file_name is not None:
    # Keep existing loggers: by default fileConfig disables them, which would
    # silence the app's own logger when tests run migrations in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure(**kwargs) -> None:
    context.configure(target_metadata=target_metadata, compare_type=True, compare_server_default=True, **kwargs)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade --sql`)."""
    _configure(url=settings.sqlalchemy_database_url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url, poolclass=pool.NullPool,
                                 connect_args=NO_PREPARED_STATEMENTS)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
