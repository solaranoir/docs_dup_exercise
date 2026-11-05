"""OAuth 2.0 / OIDC providers for sign-in (ADR-009).

Authorization-code flow with `state` and PKCE (S256). Profiles come from the providers' own
APIs over TLS using the access token we just obtained from their token endpoint, so no ID
token signature handling is needed. Only verified emails are accepted.
"""

import base64
import hashlib
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings

HTTP_TIMEOUT = httpx.Timeout(10.0)


class OAuthError(Exception):
    """Sign-in failed. `code` is a short, user-safe reason shown on the sign-in page."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class Profile:
    subject: str  # stable provider account id, never the email
    email: str  # verified
    display_name: str


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    scope: str
    fetch_profile: Callable[[httpx.Client, str], Profile]

    def credentials(self, settings: Settings) -> tuple[str, str]:
        client_id = getattr(settings, f"{self.name}_client_id")
        secret = getattr(settings, f"{self.name}_client_secret")
        if not client_id or not secret:
            raise OAuthError("unavailable", f"{self.name} is not configured")
        return client_id, secret


def redirect_uri(settings: Settings, provider: str) -> str:
    return f"{settings.app_origin}/api/auth/{provider}/callback"


def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(
    provider: Provider, settings: Settings, state: str, code_challenge: str
) -> str:
    client_id, _ = provider.credentials(settings)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(settings, provider.name),
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if provider.name == "google":
        params["prompt"] = "select_account"
    if provider.name == "github":
        params["allow_signup"] = "false"
    return f"{provider.authorize_url}?{urlencode(params)}"


def exchange_code(
    http: httpx.Client, provider: Provider, settings: Settings, code: str, verifier: str
) -> str:
    client_id, secret = provider.credentials(settings)
    response = _call(
        http,
        "POST",
        provider.token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(settings, provider.name),
            "client_id": client_id,
            "client_secret": secret,
            "code_verifier": verifier,
        },
        headers={"Accept": "application/json"},
    )
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        # GitHub reports errors as 200 + {"error": ...}.
        raise OAuthError("failed", f"token exchange: {response.get('error', 'no access_token')}")
    return token


def _call(http: httpx.Client, method: str, url: str, **kwargs: Any) -> Any:
    try:
        response = http.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise OAuthError("failed", f"{url}: {exc.__class__.__name__}") from None
    if response.status_code >= 400:
        raise OAuthError("failed", f"{url}: HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise OAuthError("failed", f"{url}: invalid JSON") from None


def _name(*candidates: object) -> str:
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return "Solara Docs user"


def _github_profile(http: httpx.Client, token: str) -> Profile:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    user = _call(http, "GET", "https://api.github.com/user", headers=headers)
    emails = _call(http, "GET", "https://api.github.com/user/emails", headers=headers)
    verified = [e for e in emails if isinstance(e, dict) and e.get("verified") and e.get("email")]
    primary = next((e for e in verified if e.get("primary")), None)
    if primary is None:
        raise OAuthError("unverified_email", "no verified primary email on GitHub account")
    if not user.get("id"):
        raise OAuthError("failed", "GitHub user has no id")
    return Profile(
        subject=str(user["id"]),
        email=str(primary["email"]),
        display_name=_name(user.get("name"), user.get("login")),
    )


def _google_profile(http: httpx.Client, token: str) -> Profile:
    info = _call(
        http,
        "GET",
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    if info.get("email_verified") is not True or not info.get("email"):
        raise OAuthError("unverified_email", "Google email not verified")
    if not info.get("sub"):
        raise OAuthError("failed", "Google userinfo has no sub")
    return Profile(
        subject=str(info["sub"]),
        email=str(info["email"]),
        display_name=_name(info.get("name"), info["email"].split("@")[0]),
    )


PROVIDERS: dict[str, Provider] = {
    "github": Provider(
        name="github",
        label="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",  # noqa: S106
        scope="read:user user:email",
        fetch_profile=_github_profile,
    ),
    "google": Provider(
        name="google",
        label="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",  # noqa: S106
        scope="openid email profile",
        fetch_profile=_google_profile,
    ),
}


def get_http_client() -> Iterator[httpx.Client]:
    """FastAPI dependency; tests override it with an httpx.MockTransport client."""
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
        yield client
