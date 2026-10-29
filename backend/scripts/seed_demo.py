"""Idempotently seed the demo identities. Usage (from backend/): python scripts/seed_demo.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_sessionmaker  # noqa: E402
from app.seed import seed_demo_users  # noqa: E402

if __name__ == "__main__":
    with get_sessionmaker()() as db:
        users = seed_demo_users(db)
    print("Seeded:", ", ".join(f"{u.login_key}#{u.id}" for u in users))
