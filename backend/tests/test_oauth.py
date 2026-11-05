"""OAuth sign-in with GitHub and Google against fake providers (ADR-009, DOC-001/002)."""

import base64
import hashlib
import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.allowlist import allow, disallow
from app.config import Settings, get_settings
from app.db import get_db
from app.main import create_app
from app.models import User, UserIdentity, UserSession
from app.oauth import get_http_client

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCESS_TOKEN = "at-secret-123"


class FakeProviders:
    """Just enough of GitHub's and Google's OAuth + profile APIs."""

    def __init__(self) -> None:
        self.github_user: dict[str, Any] = {"id": 101, "login": "kd0abc", "name": "Op Erator"}
        self.github_emails: list[dict[str, Any]] = [
            {"email": "old@example.com", "primary": False, "verified": True},
            {"email": "Op@Example.com", "primary": True, "verified": True},
        ]
        self.google: dict[str, Any] = {
            "sub": "g-555",
            "email": "op@example.com",
            "email_verified": True,
            "name": "Op on Google",
        }
        self.token_response: httpx.Response | None = None
        self.fail_with: Exception | None = None
        self.token_requests: list[dict[str, list[str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.fail_with is not None:
            raise self.fail_with
        url = str(request.url)
        if url in (GITHUB_TOKEN_URL, GOOGLE_TOKEN_URL):
            self.token_requests.append(parse_qs(request.content.decode()))
            return self.token_response or httpx.Response(200, json={"access_token": ACCESS_TOKEN})
        assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
        if url == "https://api.github.com/user":
            return httpx.Response(200, json=self.github_user)
        if url == "https://api.github.com/user/emails":
            return httpx.Response(200, json=self.github_emails)
        if url == "https://openidconnect.googleapis.com/v1/userinfo":
            return httpx.Response(200, json=self.google)
        return httpx.Response(404)


@pytest.fixture
def fake() -> FakeProviders:
    return FakeProviders()


@pytest.fixture
def oauth_client(
    db: Session, fake: FakeProviders, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    for name in ("GITHUB", "GOOGLE"):
        monkeypatch.setenv(f"{name}_CLIENT_ID", f"{name.lower()}-id")
        monkeypatch.setenv(f"{name}_CLIENT_SECRET", f"{name.lower()}-secret")
    get_settings.cache_clear()
    try:
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db

        def http() -> Iterator[httpx.Client]:
            with httpx.Client(transport=httpx.MockTransport(fake)) as client:
                yield client

        app.dependency_overrides[get_http_client] = http
        with TestClient(app) as c:
            yield c
    finally:
        get_settings.cache_clear()


def _start(client: TestClient, provider: str) -> dict[str, list[str]]:
    r = client.get(f"/api/auth/{provider}/start", follow_redirects=False)
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)


def sign_in(client: TestClient, provider: str = "github") -> httpx.Response:
    params = _start(client, provider)
    return client.get(
        f"/api/auth/{provider}/callback",
        params={"code": "auth-code", "state": params["state"][0]},
        follow_redirects=False,
    )


def _error(r: httpx.Response) -> str | None:
    assert r.status_code == 302
    query = parse_qs(urlparse(r.headers["location"]).query)
    return query.get("auth_error", [None])[0]


def _users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.email.is_not(None))) or 0


# --- discovery and redirect ---------------------------------------------------------------


def test_methods_lists_configured_providers(oauth_client: TestClient) -> None:
    body = oauth_client.get("/api/auth/methods").json()
    assert body == {
        "providers": [{"name": "github", "label": "GitHub"}, {"name": "google", "label": "Google"}],
        "demo": True,
    }


def test_no_providers_when_unconfigured(client: TestClient) -> None:
    assert client.get("/api/auth/methods").json()["providers"] == []
    assert client.get("/api/auth/github/start", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/github/callback?code=x&state=y").status_code == 404


def test_unknown_provider_404(oauth_client: TestClient) -> None:
    assert oauth_client.get("/api/auth/myspace/start", follow_redirects=False).status_code == 404


@pytest.mark.parametrize(
    ("provider", "host", "scope"),
    [
        ("github", "github.com", "read:user user:email"),
        ("google", "accounts.google.com", "openid email profile"),
    ],
)
def test_start_redirects_with_state_and_pkce(
    oauth_client: TestClient, provider: str, host: str, scope: str
) -> None:
    r = oauth_client.get(f"/api/auth/{provider}/start", follow_redirects=False)
    location = urlparse(r.headers["location"])
    params = parse_qs(location.query)
    assert location.scheme == "https" and location.hostname == host
    assert params["client_id"] == [f"{provider}-id"]
    assert params["redirect_uri"] == [f"http://localhost:5173/api/auth/{provider}/callback"]
    assert params["scope"] == [scope]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["state"][0]) >= 32
    assert "client_secret" not in params
    cookie = r.headers["set-cookie"].lower()
    assert "sd_oauth=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert r.headers["cache-control"] == "no-store"


def test_pkce_verifier_matches_challenge(
    oauth_client: TestClient, fake: FakeProviders, db: Session
) -> None:
    allow(db, "op@example.com")
    params = _start(oauth_client, "github")
    oauth_client.get(
        "/api/auth/github/callback",
        params={"code": "auth-code", "state": params["state"][0]},
        follow_redirects=False,
    )
    sent = fake.token_requests[0]
    verifier = sent["code_verifier"][0]
    digest = hashlib.sha256(verifier.encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == params["code_challenge"][0]
    assert sent["client_secret"] == ["github-secret"]
    assert sent["redirect_uri"] == ["http://localhost:5173/api/auth/github/callback"]


# --- account resolution -------------------------------------------------------------------


def test_uninvited_email_gets_nothing(oauth_client: TestClient, db: Session) -> None:
    r = sign_in(oauth_client)
    assert _error(r) == "not_invited"
    assert "sd_session" not in r.headers.get("set-cookie", "")
    assert _users(db) == 0
    assert db.scalar(select(func.count()).select_from(UserIdentity)) == 0


def test_first_sign_in_creates_account_and_session(oauth_client: TestClient, db: Session) -> None:
    allow(db, "op@example.com")
    r = sign_in(oauth_client)
    assert r.headers["location"] == "/"
    assert r.headers["cache-control"] == "no-store"
    me = oauth_client.get("/api/me").json()
    assert me["email"] == "op@example.com"  # verified *primary* email, lowercased
    assert me["display_name"] == "Op Erator"
    assert me["login_key"] is None
    identity = db.scalar(select(UserIdentity))
    assert identity is not None
    assert (identity.provider, identity.provider_subject) == ("github", "101")
    assert 'sd_oauth=""' in r.headers["set-cookie"] or "sd_oauth=;" in r.headers["set-cookie"]


def test_returning_sign_in_reuses_account(
    oauth_client: TestClient, db: Session, fake: FakeProviders
) -> None:
    allow(db, "op@example.com")
    sign_in(oauth_client)
    first = oauth_client.get("/api/me").json()["id"]
    # Same GitHub account, new primary email: still the same user (keyed by provider id).
    fake.github_emails = [{"email": "new@example.com", "primary": True, "verified": True}]
    sign_in(oauth_client)
    assert oauth_client.get("/api/me").json()["id"] == first
    assert _users(db) == 1
    identity = db.scalar(select(UserIdentity))
    assert identity is not None and identity.email == "new@example.com"


def test_second_provider_links_by_verified_email(oauth_client: TestClient, db: Session) -> None:
    allow(db, "op@example.com")
    sign_in(oauth_client, "github")
    github_id = oauth_client.get("/api/me").json()["id"]
    sign_in(oauth_client, "google")
    assert oauth_client.get("/api/me").json()["id"] == github_id
    providers = db.scalars(select(UserIdentity.provider).order_by(UserIdentity.provider)).all()
    assert providers == ["github", "google"]


def test_different_email_is_a_different_account(
    oauth_client: TestClient, db: Session, fake: FakeProviders
) -> None:
    allow(db, "op@example.com")
    allow(db, "other@example.com")
    sign_in(oauth_client, "github")
    fake.google |= {"sub": "g-other", "email": "other@example.com"}
    sign_in(oauth_client, "google")
    assert _users(db) == 2


def test_revoked_invite_blocks_returning_user(oauth_client: TestClient, db: Session) -> None:
    allow(db, "op@example.com")
    sign_in(oauth_client)
    disallow(db, "op@example.com")
    assert oauth_client.get("/api/me").status_code == 401  # sessions ended
    assert _error(sign_in(oauth_client)) == "not_invited"


def test_re_sign_in_replaces_previous_session(oauth_client: TestClient, db: Session) -> None:
    allow(db, "op@example.com")
    sign_in(oauth_client)
    old = oauth_client.cookies["sd_session"]
    sign_in(oauth_client)
    assert oauth_client.cookies["sd_session"] != old
    assert db.scalar(select(func.count()).select_from(UserSession)) == 1


@pytest.mark.parametrize(
    ("provider", "change"),
    [
        (
            "github",
            {"github_emails": [{"email": "op@example.com", "primary": True, "verified": False}]},
        ),
        (
            "github",
            {"github_emails": [{"email": "op@example.com", "primary": False, "verified": True}]},
        ),
        ("github", {"github_emails": []}),
        ("google", {"google": {"sub": "g", "email": "op@example.com", "email_verified": False}}),
        ("google", {"google": {"sub": "g", "email": "op@example.com", "email_verified": "true"}}),
    ],
)
def test_unverified_email_rejected(
    oauth_client: TestClient,
    db: Session,
    fake: FakeProviders,
    provider: str,
    change: dict[str, Any],
) -> None:
    allow(db, "op@example.com")
    for key, value in change.items():
        setattr(fake, key, value)
    assert _error(sign_in(oauth_client, provider)) == "unverified_email"
    assert _users(db) == 0


# --- flow integrity and provider failures -------------------------------------------------


def test_state_mismatch_rejected(
    oauth_client: TestClient, db: Session, fake: FakeProviders
) -> None:
    allow(db, "op@example.com")
    _start(oauth_client, "github")
    r = oauth_client.get(
        "/api/auth/github/callback",
        params={"code": "auth-code", "state": "attacker-state"},
        follow_redirects=False,
    )
    assert _error(r) == "failed"
    assert fake.token_requests == []  # never exchanged the code


def test_callback_without_flow_cookie_is_expired(oauth_client: TestClient, db: Session) -> None:
    allow(db, "op@example.com")
    params = _start(oauth_client, "github")
    oauth_client.cookies.clear()  # e.g. a login-CSRF link sent to a victim
    r = oauth_client.get(
        "/api/auth/github/callback",
        params={"code": "auth-code", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert _error(r) == "expired"


def test_flow_cookie_is_bound_to_provider(oauth_client: TestClient, db: Session) -> None:
    allow(db, "op@example.com")
    params = _start(oauth_client, "github")
    r = oauth_client.get(
        "/api/auth/google/callback",
        params={"code": "auth-code", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert _error(r) == "failed"


def test_user_cancelled(oauth_client: TestClient) -> None:
    _start(oauth_client, "google")
    r = oauth_client.get("/api/auth/google/callback?error=access_denied", follow_redirects=False)
    assert _error(r) == "cancelled"


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(200, json={"error": "bad_verification_code"}),  # GitHub style
        httpx.Response(400, json={"error": "invalid_grant"}),  # Google style
        httpx.Response(200, text="<html>"),
        httpx.ConnectError("boom"),
    ],
)
def test_provider_failures_are_handled(
    oauth_client: TestClient, db: Session, fake: FakeProviders, failure: object
) -> None:
    allow(db, "op@example.com")
    if isinstance(failure, Exception):
        fake.fail_with = failure
    else:
        assert isinstance(failure, httpx.Response)
        fake.token_response = failure
    assert _error(sign_in(oauth_client)) == "failed"
    assert _users(db) == 0


def test_logs_never_contain_tokens_or_emails(
    oauth_client: TestClient, db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    allow(db, "op@example.com")
    # create_app() -> configure_logging() replaced the root handlers, including caplog's.
    logging.getLogger().addHandler(caplog.handler)
    with caplog.at_level(logging.DEBUG):
        sign_in(oauth_client)
        sign_in(oauth_client, "google")
    # Skip the test client's own request lines (it is an httpx client calling testserver);
    # everything the app logs, including its outgoing provider calls, is checked.
    text = "\n".join(
        r.getMessage().lower()
        for r in caplog.records
        if not (r.name == "httpx" and "testserver" in r.getMessage())
    )
    assert "github.com/login/oauth/access_token" in text  # provider calls are logged…
    assert "sign-in ok provider=github" in text
    for secret in (ACCESS_TOKEN, "auth-code", "github-secret", "op@example.com"):  # …secrets aren't
        assert secret not in text


def test_production_requires_https_public_origin() -> None:
    settings = Settings(
        environment="production",
        session_secret="s" * 48,
        enable_demo_auth=False,
        cors_origins=["https://docworkspace-web.onrender.com"],
        public_base_url="http://docworkspace-web.onrender.com",
    )
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        settings.check_production()
    ok = Settings(
        environment="production",
        session_secret="s" * 48,
        enable_demo_auth=False,
        cors_origins=["https://docworkspace-web.onrender.com"],
    )
    ok.check_production()
    assert ok.app_origin == "https://docworkspace-web.onrender.com"
