"""Demo-only session handling (ADR-004).

The principal is always derived from a server-signed token; no route accepts a user id
from the client. Replace with real authentication before any public deployment.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User

SESSION_COOKIE = "dw_session"
_SALT = "demo-session"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=_SALT)


def issue_token(user: User, settings: Settings) -> str:
    return _serializer(settings).dumps({"uid": user.id})


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


def _read_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    token = _read_token(request)
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    if not token:
        raise unauthorized
    try:
        payload = _serializer(settings).loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        raise unauthorized from None
    user = db.get(User, payload.get("uid"))
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]
