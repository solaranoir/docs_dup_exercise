"""Manage the Solara Docs invite allowlist (ADR-009).

Usage (from backend/, with DATABASE_URL set):
    python scripts/allow_email.py add someone@example.com [--note "POTA club"]
    python scripts/allow_email.py remove someone@example.com   # also ends their sessions
    python scripts/allow_email.py list

On Render: open the API service's Shell tab and run the same commands.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.allowlist import allow, disallow, list_allowed  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the Solara Docs sign-in allowlist.")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="allow an email to sign in")
    add.add_argument("email")
    add.add_argument("--note", help="who this is, for your own reference")
    remove = sub.add_parser("remove", help="revoke an email and end its sessions")
    remove.add_argument("email")
    sub.add_parser("list", help="show allowed emails")
    args = parser.parse_args(argv)

    with get_sessionmaker()() as db:
        try:
            if args.command == "add":
                added = allow(db, args.email, args.note)
                print(("Added " if added else "Already allowed: ") + args.email.strip().lower())
            elif args.command == "remove":
                result = disallow(db, args.email)
                if not result.removed and not result.sessions_ended:
                    print(f"Not on the allowlist: {args.email}")
                    return 1
                print(f"Removed {args.email}; ended {result.sessions_ended} session(s)")
            else:
                entries = list_allowed(db)
                for entry in entries:
                    print(f"{entry.email}\t{entry.note or ''}".rstrip())
                print(f"({len(entries)} allowed)", file=sys.stderr)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
