"""Delete the Alice/Bob/Charlie demo identities and everything they own (cut-over, ADR-009).

Usage (from backend/, with DATABASE_URL and STORAGE_* set — on Render: the API's Shell tab):
    python scripts/purge_demo_data.py          # dry run: shows what would be deleted
    python scripts/purge_demo_data.py --yes    # delete

Real (OAuth) accounts and their documents are never touched. In local development the next
API start re-seeds the demo users if ENABLE_DEMO_AUTH=true.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_sessionmaker  # noqa: E402
from app.purge import PurgeRefused, plan_purge, purge_demo_data  # noqa: E402
from app.storage import optional_storage  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove seeded demo users and their data.")
    parser.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args(argv)

    with get_sessionmaker()() as db:
        try:
            plan = plan_purge(db)
            print(plan.summary())
            if plan.empty:
                print("Nothing to purge.")
                return 0
            if not args.yes:
                print("Dry run: nothing deleted. Re-run with --yes to delete.")
                return 0
            result = purge_demo_data(db, optional_storage())
        except PurgeRefused as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 2
    print("Deleted.")
    if result.orphaned_keys:
        print(f"{len(result.orphaned_keys)} object(s) could not be deleted from storage:")
        for key in result.orphaned_keys:
            print(f"  {key}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
