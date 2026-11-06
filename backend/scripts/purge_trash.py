"""Permanently remove documents that have been in the Trash for 30 days (DOC-031, ADR-012).

The API already does this at most hourly, after a list request. Run this to do it now, or to
check what is due.

Usage (from backend/, with DATABASE_URL and STORAGE_* set; on Render: the API's Shell tab):
    python scripts/purge_trash.py          # dry run: counts what is due
    python scripts/purge_trash.py --yes    # delete documents past their 30 days
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.db import get_sessionmaker  # noqa: E402
from app.models import Document, utcnow  # noqa: E402
from app.storage import optional_storage  # noqa: E402
from app.trash import TRASH_DAYS, purge_expired  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Purge documents past their Trash retention.")
    parser.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args(argv)

    with get_sessionmaker()() as db:
        cutoff = utcnow() - timedelta(days=TRASH_DAYS)
        in_trash = db.scalar(select(func.count()).where(Document.deleted_at.is_not(None))) or 0
        due = (
            db.scalar(
                select(func.count()).where(
                    Document.deleted_at.is_not(None), Document.deleted_at <= cutoff
                )
            )
            or 0
        )
        print(f"{in_trash} documents in Trash; {due} older than {TRASH_DAYS} days.")
        if not due or not args.yes:
            if due:
                print("Dry run: nothing deleted. Re-run with --yes to delete.")
            return 0
        result = purge_expired(db, optional_storage())
        print(f"Removed {result.documents} documents.")
        if result.orphaned_keys:
            print(f"{len(result.orphaned_keys)} attachment objects could not be deleted:")
            for key in result.orphaned_keys:
                print(f"  {key}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
