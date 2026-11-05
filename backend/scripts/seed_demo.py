"""Idempotently seed the demo identities. Usage (from backend/): python scripts/seed_demo.py

Does nothing unless demo auth is enabled (ENABLE_DEMO_AUTH=true, never in production).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.seed import seed_demo_users  # noqa: E402


def main() -> int:
    if not get_settings().demo_auth_enabled:
        print("Demo auth disabled; not seeding demo users.")
        return 0
    with get_sessionmaker()() as db:
        users = seed_demo_users(db)
    print("Seeded:", ", ".join(f"{u.login_key}#{u.id}" for u in users))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
