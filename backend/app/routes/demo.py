"""Seeded demo identities (ADR-004). Mounted only when `Settings.demo_auth_enabled`, which is
never true in production. Kept for local development and the Playwright suite."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import start_session
from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.ratelimit import limit_login
from app.routes.account import UserOut, user_out

router = APIRouter(prefix="/api/demo", tags=["demo-auth"])


class LoginIn(BaseModel):
    login_key: str


class LoginOut(BaseModel):
    # The session token is set as an httpOnly cookie only; never returned here.
    user: UserOut


@router.get("/users")
def list_demo_users(db: Annotated[Session, Depends(get_db)]) -> list[UserOut]:
    # Demo identities only: never list real (OAuth) accounts.
    demo = select(User).where(User.login_key.is_not(None)).order_by(User.id)
    return [user_out(u) for u in db.scalars(demo)]


@router.post("/login", dependencies=[Depends(limit_login)])
def demo_login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    user = db.scalar(select(User).where(User.login_key == body.login_key))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown demo user")
    start_session(request, response, db, user, settings)
    return LoginOut(user=user_out(user))
