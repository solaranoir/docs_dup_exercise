from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

DEMO_USERS: tuple[tuple[str, str], ...] = (
    ("alice", "Alice (owner)"),
    ("bob", "Bob (recipient)"),
    ("charlie", "Charlie (no access)"),
)
# Reserved .test domain (RFC 2606): no provider can verify these, so OAuth can never claim them.
DEMO_EMAIL_DOMAIN = "demo.test"


def seed_demo_users(db: Session) -> list[User]:
    """Insert missing demo users; safe to run any number of times."""
    existing = {u.login_key: u for u in db.scalars(select(User))}
    for key, name in DEMO_USERS:
        user = existing.get(key)
        email = f"{key}@{DEMO_EMAIL_DOMAIN}"
        if user is None:
            db.add(User(login_key=key, display_name=name, email=email))
        else:
            user.display_name = name
            user.email = email
    db.commit()
    return list(db.scalars(select(User).order_by(User.id)))
