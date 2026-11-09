"""Test fixtures: a migrated Postgres test database, wiped after each test,
and an API client signed in as a fixed user."""

import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import require_user
from app.database import models  # noqa: F401 -- registers every table on Base.metadata
from app.database.connect import AsyncSessionLocal, Base, get_db
from app.main import create_app
from app.supabase_auth import AuthUser
from config import settings

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def make_user(name: str, *, admin: bool = False) -> AuthUser:
    return AuthUser(id=uuid.uuid4(), email=f"{name.lower()}@example.com", name=name, is_admin=admin)


def _create_database_if_missing() -> None:
    dbname = conninfo_to_dict(settings.database_url)["dbname"]
    with psycopg.connect(make_conninfo(settings.database_url, dbname="postgres"), autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """The test database at the Alembic head, through the same migrations production runs."""
    _create_database_if_missing()
    command.upgrade(AlembicConfig(str(_ALEMBIC_INI)), "head")
    # Code that opens its own sessions (the shop agent's store) runs on the
    # test client's event loop: pooled async connections must not cross loops.
    AsyncSessionLocal.configure(bind=create_async_engine(settings.sqlalchemy_database_url, poolclass=NullPool))


@pytest.fixture(autouse=True)
def no_watcher(monkeypatch):
    """Tests drive the payment watcher themselves, never on a timer."""
    monkeypatch.setattr(settings, "watcher_enabled", False)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    tables = sql.SQL(", ").join(sql.Identifier(t.name) for t in Base.metadata.sorted_tables)
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(tables))


@pytest.fixture
def user() -> AuthUser:
    return make_user("Owner")


@pytest.fixture
def client(user: AuthUser):
    """The real app, signed in as `user`; `client.sign_in(other)` switches the
    caller and `client.sign_out()` sends no token. NullPool because TestClient
    runs requests on its own event loop."""
    engine = create_async_engine(settings.sqlalchemy_database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_db():
        async with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = _get_db
    signed_in: dict[str, AuthUser | None] = {"user": user}

    def _current() -> AuthUser:
        if signed_in["user"] is None:
            raise HTTPException(401, "Sign in first.")
        return signed_in["user"]

    app.dependency_overrides[require_user] = _current
    with TestClient(app, base_url="http://test") as test_client:
        test_client.sign_in = lambda who: signed_in.update(user=who)
        test_client.sign_out = lambda: signed_in.update(user=None)
        yield test_client
