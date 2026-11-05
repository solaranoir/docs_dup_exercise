"""The signed-in account: who am I, and sign out. Independent of how the user signed in."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, clear_session_cookie
from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.sessions import end_session

router = APIRouter(prefix="/api", tags=["account"])


class UserOut(BaseModel):
    id: int
    display_name: str
    email: str | None
    login_key: str | None  # demo identities only


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, display_name=user.display_name, email=user.email, login_key=user.login_key
    )


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """End this session on the server, not just in the browser. Idempotent."""
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        end_session(db, token)
    clear_session_cookie(response, settings)
