"""Map a verified OAuth profile to a Solara Docs user (ADR-009).

Accounts are found by (provider, provider_subject), never by email alone. A first sign-in with
a new provider links to an existing user only when the verified email matches. Nobody gets an
account, or a session, unless their email is on the invite allowlist.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.allowlist import is_allowed, normalize_email
from app.models import User, UserIdentity, utcnow
from app.oauth import OAuthError, Profile


def resolve_user(db: Session, provider: str, profile: Profile) -> User:
    try:
        email = normalize_email(profile.email)
    except ValueError:
        raise OAuthError("failed", "provider returned an invalid email") from None

    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider, UserIdentity.provider_subject == profile.subject
        )
    )
    if identity is not None:
        user = db.get(User, identity.user_id)
        assert user is not None
        # The account's own email is what was invited; the provider's may have changed since.
        if not is_allowed(db, user.email or email):
            raise OAuthError("not_invited")
        identity.email = email
        identity.last_used_at = utcnow()
        db.commit()
        return user

    if not is_allowed(db, email):
        raise OAuthError("not_invited")  # nothing is created for uninvited people
    user = db.scalar(select(User).where(User.email == email))
    try:
        if user is None:
            user = User(email=email, display_name=profile.display_name)
            db.add(user)
            db.flush()
        db.add(
            UserIdentity(
                user_id=user.id, provider=provider, provider_subject=profile.subject, email=email
            )
        )
        db.commit()
    except IntegrityError:
        # Concurrent first sign-in for the same person; the other request won. Retry works.
        db.rollback()
        raise OAuthError("failed", "concurrent first sign-in") from None
    return user
