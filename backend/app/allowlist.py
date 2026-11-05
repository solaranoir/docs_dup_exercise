"""Invite allowlist (ADR-009): only listed, verified emails may sign in."""

import re
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AllowedEmail, User, UserSession

EMAIL_MAX = 320
# Deliberately loose: providers have already verified the address; this only rejects typos
# in the CLI (missing @, spaces, no dot in the domain).
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > EMAIL_MAX or not _EMAIL.fullmatch(email):
        raise ValueError(f"Not a valid email address: {raw!r}")
    return email


def is_allowed(db: Session, email: str) -> bool:
    return db.get(AllowedEmail, normalize_email(email)) is not None


def allow(db: Session, email: str, note: str | None = None) -> bool:
    """Add an email. Returns False if it was already allowed (the note is then updated)."""
    email = normalize_email(email)
    entry = db.get(AllowedEmail, email)
    if entry is not None:
        if note is not None:
            entry.note = note
            db.commit()
        return False
    db.add(AllowedEmail(email=email, note=note))
    db.commit()
    return True


@dataclass(frozen=True)
class Revocation:
    removed: bool
    sessions_ended: int


def disallow(db: Session, email: str) -> Revocation:
    """Remove an email and end the matching user's sessions immediately.

    The user row and their documents are kept, so re-inviting restores access.
    """
    email = normalize_email(email)
    entry = db.get(AllowedEmail, email)
    if entry is not None:
        db.delete(entry)
    ended = 0
    user_id = db.scalar(select(User.id).where(User.email == email))
    if user_id is not None:
        result = db.execute(delete(UserSession).where(UserSession.user_id == user_id))
        ended = result.rowcount  # type: ignore[attr-defined]
    db.commit()
    return Revocation(removed=entry is not None, sessions_ended=ended)


def list_allowed(db: Session) -> list[AllowedEmail]:
    return list(db.scalars(select(AllowedEmail).order_by(AllowedEmail.email)))
