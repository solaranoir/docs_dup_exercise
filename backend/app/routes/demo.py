from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, CurrentUser, issue_token, set_session_cookie
from app.config import Settings, get_settings
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api", tags=["demo-auth"])


class UserOut(BaseModel):
    id: int
    login_key: str
    display_name: str


class LoginIn(BaseModel):
    login_key: str


class LoginOut(BaseModel):
    user: UserOut
    token: str


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, login_key=user.login_key, display_name=user.display_name)


@router.get("/demo/users")
def list_demo_users(db: Annotated[Session, Depends(get_db)]) -> list[UserOut]:
    return [_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/demo/login")
def demo_login(
    body: LoginIn,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    user = db.scalar(select(User).where(User.login_key == body.login_key))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user")
    token = issue_token(user, settings)
    set_session_cookie(response, token, settings)
    return LoginOut(user=_out(user), token=token)


@router.post("/demo/logout", status_code=status.HTTP_204_NO_CONTENT)
def demo_logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return _out(user)
