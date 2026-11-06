"""The deploy's migration step (Render pre-deploy command; RUNBOOK → Rollback and migrations).

``alembic upgrade head``, except when the database is already *ahead* of this code: a rollback
or a reverted PR redeploys code that doesn't have the newest migration file, and a plain
``alembic upgrade head`` would then fail with "Can't locate revision" and fail the rollback.
Migrations follow expand/contract (the previous release runs against the new schema), so
skipping is safe: the schema stays where it is and the older code runs on it.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

BACKEND = Path(__file__).resolve().parents[1]
log = logging.getLogger(__name__)


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def current_revisions(database_url: str) -> tuple[str, ...]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return tuple(MigrationContext.configure(conn).get_current_heads())
    finally:
        engine.dispose()


def migrate(database_url: str) -> str:
    """Upgrade to head, or skip when the database is at a revision this code doesn't know.

    Returns ``"upgraded"`` or ``"ahead"``.
    """
    cfg = alembic_config(database_url)
    known = {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
    unknown = [rev for rev in current_revisions(database_url) if rev not in known]
    if unknown:
        log.warning(
            "migrate: database is at %s, newer than this code's migrations; leaving the schema "
            "as it is (rollback; expand/contract keeps it compatible)",
            ", ".join(unknown),
        )
        return "ahead"
    command.upgrade(cfg, "head")
    return "upgraded"
