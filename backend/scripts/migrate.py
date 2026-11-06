"""Deploy migration step: ``alembic upgrade head`` that tolerates a rollback (app/migrations.py).

Usage (from backend/, with DATABASE_URL set): python scripts/migrate.py
Render runs it as the API's pre-deploy command.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.migrations import migrate  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = migrate(get_settings().database_url)
    print(f"migrate: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
