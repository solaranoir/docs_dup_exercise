"""Server-side sessions (ADR-009).

The browser holds a random 256-bit token in an httpOnly cookie; the database holds only its
SHA-256. A session ends at logout, after `session_idle_seconds` without use, after
`session_absolute_seconds` regardless of use, or when the user's invite is revoked.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User, UserSession, utcnow


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    # SQLite (local test fallback) returns naive datetimes; PostgreSQL returns aware ones.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def create_session(
    db: Session, user: User, settings: Settings, user_agent: str | None = None
) -> str:
    """Start a session for `user` and return the cookie token (shown to no one else)."""
    now = utcnow()
    db.execute(delete(UserSession).where(UserSession.expires_at <= now))  # opportunistic purge
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=settings.session_absolute_seconds),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    user.last_login_at = now
    db.commit()
    return token


def resolve_session(db: Session, token: str, settings: Settings) -> User | None:
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None:
        return None
    now = utcnow()
    last_seen = _aware(session.last_seen_at)
    idle_limit = last_seen + timedelta(seconds=settings.session_idle_seconds)
    if _aware(session.expires_at) <= now or idle_limit <= now:
        db.delete(session)
        db.commit()
        return None
    if now - last_seen >= timedelta(seconds=settings.session_touch_seconds):
        session.last_seen_at = now
        db.commit()
    return db.get(User, session.user_id)


def end_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()


def end_all_sessions(db: Session, user_id: int) -> int:
    result = db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.commit()
    return result.rowcount  # type: ignore[attr-defined, no-any-return]
