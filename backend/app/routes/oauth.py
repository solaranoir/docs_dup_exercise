"""OAuth sign-in routes (ADR-009).

    GET /api/auth/methods             which sign-in methods this deployment offers
    GET /api/auth/{provider}/start    redirect to the provider (sets a short-lived flow cookie)
    GET /api/auth/{provider}/callback provider redirects back here; starts a session

Both redirects reach this service through the web origin's /api rewrite (ADR-007), so the
flow and session cookies are first-party. Failures redirect to `/?auth_error=<code>`.
"""

import logging
import secrets
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import start_session
from app.config import Settings, get_settings
from app.db import get_db
from app.identity import resolve_user
from app.oauth import (
    PROVIDERS,
    OAuthError,
    Provider,
    authorization_url,
    exchange_code,
    get_http_client,
    new_pkce,
)
from app.ratelimit import limit_login
from app.sessions import end_session

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)
SettingsDep = Annotated[Settings, Depends(get_settings)]

FLOW_MAX_AGE_SECONDS = 600
_FLOW_SALT = "oauth-flow"


class MethodOut(BaseModel):
    name: str
    label: str


class MethodsOut(BaseModel):
    providers: list[MethodOut]
    demo: bool


def _flow_cookie(settings: Settings) -> str:
    return "__Host-sd_oauth" if settings.is_production else "sd_oauth"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=_FLOW_SALT)


def _provider(name: str, settings: Settings) -> Provider:
    if name not in settings.oauth_providers:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown sign-in provider")
    return PROVIDERS[name]


def _read_flow(request: Request, settings: Settings) -> dict[str, Any]:
    raw = request.cookies.get(_flow_cookie(settings))
    if not raw:
        raise OAuthError("expired", "no flow cookie")
    try:
        flow = _serializer(settings).loads(raw, max_age=FLOW_MAX_AGE_SECONDS)
    except BadSignature:  # includes SignatureExpired
        raise OAuthError("expired", "flow cookie invalid or expired") from None
    if not isinstance(flow, dict):
        raise OAuthError("expired", "malformed flow cookie")
    return flow


@router.get("/methods")
def methods(settings: SettingsDep) -> MethodsOut:
    return MethodsOut(
        providers=[MethodOut(name=n, label=PROVIDERS[n].label) for n in settings.oauth_providers],
        demo=settings.demo_auth_enabled,
    )


@router.get("/{provider}/start", dependencies=[Depends(limit_login)])
def start(provider: str, settings: SettingsDep) -> RedirectResponse:
    p = _provider(provider, settings)
    state = secrets.token_urlsafe(32)
    verifier, challenge = new_pkce()
    response = RedirectResponse(
        authorization_url(p, settings, state, challenge), status.HTTP_302_FOUND
    )
    response.set_cookie(
        _flow_cookie(settings),
        _serializer(settings).dumps({"p": p.name, "s": state, "v": verifier}),
        max_age=FLOW_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",  # sent on the provider's top-level redirect back to us
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/{provider}/callback")
def callback(  # noqa: PLR0913
    provider: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: SettingsDep,
    http: Annotated[httpx.Client, Depends(get_http_client)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    p = _provider(provider, settings)
    try:
        if error is not None:
            raise OAuthError("cancelled" if error == "access_denied" else "failed", error[:64])
        flow = _read_flow(request, settings)
        expected = flow.get("s")
        if (
            flow.get("p") != p.name
            or not isinstance(expected, str)
            or not state
            or not code
            or not secrets.compare_digest(expected, state)
        ):
            raise OAuthError("failed", "state mismatch")
        token = exchange_code(http, p, settings, code, str(flow.get("v", "")))
        profile = p.fetch_profile(http, token)
        user = resolve_user(db, p.name, profile)
    except OAuthError as exc:
        # Never log emails or tokens; the provider and reason are enough to debug.
        log.warning("sign-in failed provider=%s reason=%s detail=%s", p.name, exc.code, exc)
        response = RedirectResponse(f"/?auth_error={exc.code}", status.HTTP_302_FOUND)
    else:
        response = RedirectResponse("/", status.HTTP_302_FOUND)
        previous = request.cookies.get(settings.session_cookie_name)
        if previous:
            end_session(db, previous)  # no session fixation / stale sessions on re-sign-in
        start_session(request, response, db, user, settings)
        log.info("sign-in ok provider=%s user=%s", p.name, user.id)
    response.delete_cookie(
        _flow_cookie(settings),
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
