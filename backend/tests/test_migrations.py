"""The deploy migration step (app/migrations.py; RUNBOOK → Rollback and migrations)."""

import pytest
from sqlalchemy import text

from app.migrations import current_revisions, migrate


@pytest.fixture
def url(engine) -> str:  # type: ignore[no-untyped-def]
    return engine.url.render_as_string(hide_password=False)


def test_upgrades_to_head(url: str) -> None:
    before = current_revisions(url)
    assert migrate(url) == "upgraded"
    assert current_revisions(url) == before  # already at head: a no-op


def test_rollback_with_a_newer_database_is_not_an_error(engine, url: str) -> None:  # type: ignore[no-untyped-def]
    """Older code (no file for the newest migration) deploys against the newer schema."""
    (head,) = current_revisions(url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '9999_from_the_future'"))
    try:
        assert migrate(url) == "ahead"
        assert current_revisions(url) == ("9999_from_the_future",)  # schema left alone
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :v"), {"v": head})
