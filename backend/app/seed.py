from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

DEMO_USERS: tuple[tuple[str, str], ...] = (
    ("alice", "Alice (owner)"),
    ("bob", "Bob (recipient)"),
    ("charlie", "Charlie (no access)"),
)


def seed_demo_users(db: Session) -> list[User]:
    """Insert missing demo users; safe to run any number of times."""
    existing = {u.login_key: u for u in db.scalars(select(User))}
    for key, name in DEMO_USERS:
        user = existing.get(key)
        if user is None:
            db.add(User(login_key=key, display_name=name))
        elif user.display_name != name:
            user.display_name = name
    db.commit()
    return list(db.scalars(select(User).order_by(User.id)))
