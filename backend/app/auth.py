"""Request authentication: the principal comes only from a server-side session (ADR-009).

The session token travels only in an httpOnly cookie. It is never accepted from a header or
returned in a response body, and no route trusts a client-supplied user id.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.sessions import create_session, resolve_session


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_absolute_seconds,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def start_session(
    request: Request, response: Response, db: Session, user: User, settings: Settings
) -> None:
    token = create_session(db, user, settings, request.headers.get("user-agent"))
    set_session_cookie(response, token, settings)


def current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    user = resolve_session(db, token, settings) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
