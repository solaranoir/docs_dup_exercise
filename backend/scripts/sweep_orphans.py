"""Find and remove attachment objects that no attachment points at (audit A12, app/orphans.py).

Usage (from backend/, with DATABASE_URL and STORAGE_* set; on Render: the API's Shell tab):
    python scripts/sweep_orphans.py          # dry run: lists orphaned objects
    python scripts/sweep_orphans.py --yes    # delete them

Objects younger than an hour are skipped (an upload may still be committing).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_sessionmaker  # noqa: E402
from app.orphans import find_orphans, sweep  # noqa: E402
from app.storage import optional_storage  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove orphaned attachment objects.")
    parser.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args(argv)

    storage = optional_storage()
    if storage is None:
        print("Storage is not configured (STORAGE_*); nothing to sweep.")
        return 1
    with get_sessionmaker()() as db:
        result = find_orphans(db, storage)
    print(f"{result.scanned} objects scanned; {len(result.orphans)} orphaned.")
    for key in result.orphans:
        print(f"  {key}")
    if not result.orphans or not args.yes:
        if result.orphans:
            print("Dry run: nothing deleted. Re-run with --yes to delete.")
        return 0
    sweep(storage, result)
    print(f"Deleted {result.deleted}.")
    if result.failed:
        print(f"{len(result.failed)} could not be deleted; run again later:")
        for key in result.failed:
            print(f"  {key}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
