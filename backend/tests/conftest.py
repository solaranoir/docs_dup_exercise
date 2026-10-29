"""Tests run against TEST_DATABASE_URL (PostgreSQL in CI). Locally it falls back to SQLite so the
suite runs without a database server; CI is the source of truth for PostgreSQL behaviour."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db
from app.main import create_app
from app.seed import seed_demo_users
from app.storage import MemoryStorage, get_storage, optional_storage

FIXTURES = Path(__file__).parent / "fixtures"

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    return f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"


@pytest.fixture(scope="session")
def engine(database_url: str):  # type: ignore[no-untyped-def]
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_demo_users(session)
    yield session
    session.close()
    with engine.begin() as conn:
        for table in ("attachments", "document_grants", "documents", "users"):
            conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def client(db: Session, storage: MemoryStorage) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[optional_storage] = lambda: storage
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client: TestClient):  # type: ignore[no-untyped-def]
    def _login(key: str) -> dict[str, str]:
        r = client.post("/api/demo/login", json={"login_key": key})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return _login
