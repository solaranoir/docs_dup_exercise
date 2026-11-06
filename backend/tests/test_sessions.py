"""Server-side sessions, cookie hardening, CSRF origin check, demo gating (ADR-009, DOC-004/005)."""

import sys
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.allowlist import allow, disallow
from app.auth import set_session_cookie
from app.config import Settings, get_settings
from app.db import get_db
from app.main import create_app
from app.models import User, UserSession, utcnow
from app.sessions import hash_token

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_demo  # noqa: E402

WEB = "http://localhost:5173"


def _cookie(headers: dict[str, str]) -> str:
    return headers["Cookie"].split("=", 1)[1]


def _row(db: Session, token: str) -> UserSession | None:
    db.expire_all()
    return db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))


# --- sessions -----------------------------------------------------------------------------


def test_login_sets_hardened_cookie_and_never_returns_token(client: TestClient) -> None:
    r = client.post("/api/demo/login", json={"login_key": "alice"})
    assert r.status_code == 200
    assert "token" not in r.json()
    set_cookie = r.headers["set-cookie"].lower()
    for attribute in ("sd_session=", "httponly", "samesite=lax", "path=/"):
        assert attribute in set_cookie
    assert r.cookies["sd_session"] not in r.text


def test_only_token_hash_is_stored(client: TestClient, db: Session, login) -> None:  # type: ignore[no-untyped-def]
    token = _cookie(login("alice"))
    row = _row(db, token)
    assert row is not None
    assert row.token_hash == hash_token(token) != token
    assert db.scalar(select(func.count()).where(UserSession.token_hash == token)) == 0
    user = db.get(User, row.user_id)
    assert user is not None and user.last_login_at is not None


def test_bearer_tokens_are_not_accepted(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    token = _cookie(login("alice"))
    client.cookies.clear()
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_logout_ends_session_server_side(client: TestClient, db: Session, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob = login("alice"), login("bob")
    r = client.post("/api/auth/logout", headers=alice)
    assert r.status_code == 204
    assert 'sd_session=""' in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"]
    # Replaying the copied cookie no longer works; other users' sessions are untouched.
    assert client.get("/api/me", headers=alice).status_code == 401
    assert _row(db, _cookie(alice)) is None
    assert client.get("/api/me", headers=bob).status_code == 200


def test_logout_without_session_is_harmless(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 204


def test_absolute_expiry(client: TestClient, db: Session, login) -> None:  # type: ignore[no-untyped-def]
    headers = login("alice")
    row = _row(db, _cookie(headers))
    assert row is not None
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/me", headers=headers).status_code == 401
    assert _row(db, _cookie(headers)) is None


def test_idle_expiry(client: TestClient, db: Session, login) -> None:  # type: ignore[no-untyped-def]
    headers = login("alice")
    row = _row(db, _cookie(headers))
    assert row is not None
    row.last_seen_at = utcnow() - timedelta(seconds=get_settings().session_idle_seconds + 1)
    db.commit()
    assert client.get("/api/me", headers=headers).status_code == 401


def test_activity_refreshes_last_seen_but_not_on_every_request(
    client: TestClient,
    db: Session,
    login,  # type: ignore[no-untyped-def]
) -> None:
    headers = login("alice")
    row = _row(db, _cookie(headers))
    assert row is not None
    fresh = row.last_seen_at
    client.get("/api/me", headers=headers)
    row = _row(db, _cookie(headers))
    assert row is not None and row.last_seen_at == fresh  # within touch interval: no write

    stale = utcnow() - timedelta(days=6)
    row.last_seen_at = stale
    db.commit()
    assert client.get("/api/me", headers=headers).status_code == 200
    row = _row(db, _cookie(headers))
    assert row is not None and row.last_seen_at > stale


def test_revoking_invite_signs_user_out(client: TestClient, db: Session, login) -> None:  # type: ignore[no-untyped-def]
    headers = login("alice")
    alice = db.scalar(select(User).where(User.login_key == "alice"))
    assert alice is not None
    alice.email = "alice@example.com"
    db.commit()
    allow(db, "alice@example.com")
    disallow(db, "alice@example.com")
    assert client.get("/api/me", headers=headers).status_code == 401


# --- CSRF origin check --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Origin": WEB}, 201),
        ({"Origin": WEB + "/"}, 201),
        ({}, 201),  # non-browser client: no ambient cookies to abuse
        ({"Sec-Fetch-Site": "same-origin"}, 201),
        ({"Origin": "https://evil.example"}, 403),
        ({"Origin": "null"}, 403),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Sec-Fetch-Site": "same-site"}, 403),
    ],
)
def test_csrf_origin_check_on_writes(
    client: TestClient,
    login,  # type: ignore[no-untyped-def]
    headers: dict[str, str],
    expected: int,
) -> None:
    r = client.post("/api/documents", json={"title": "x"}, headers=login("alice") | headers)
    assert r.status_code == expected
    if expected == 403:
        assert r.json() == {"detail": "Cross-site request blocked"}
        assert "x-request-id" in r.headers


def test_csrf_blocks_cross_site_multipart_upload(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    files = {"file": ("a.txt", b"hello", "text/plain")}
    evil = login("alice") | {"Origin": "https://evil.example"}
    assert client.post("/api/imports", files=files, headers=evil).status_code == 403


def test_csrf_allows_cross_site_reads(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    headers = login("alice") | {"Origin": "https://evil.example"}
    assert client.get("/api/documents", headers=headers).status_code == 200


# --- demo gating and production safety ----------------------------------------------------


@pytest.fixture
def demo_disabled(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ENABLE_DEMO_AUTH", "false")
    get_settings.cache_clear()
    try:
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as c:
            yield c
    finally:
        get_settings.cache_clear()


def test_demo_routes_absent_when_disabled(demo_disabled: TestClient) -> None:
    assert demo_disabled.get("/api/demo/users").status_code == 404
    login = demo_disabled.post("/api/demo/login", json={"login_key": "alice"})
    assert login.status_code == 404
    assert demo_disabled.get("/api/me").status_code == 401


def test_seed_skips_when_demo_disabled(
    demo_disabled: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert seed_demo.main() == 0
    assert "not seeding" in capsys.readouterr().out


def _prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "session_secret": "s" * 48,
        "cors_origins": ["https://docworkspace-web.onrender.com"],
        "enable_demo_auth": False,
    }
    return Settings(**(values | overrides))  # type: ignore[arg-type]


def test_production_settings_are_safe() -> None:
    settings = _prod()
    settings.check_production()
    assert settings.session_cookie_name == "__Host-sd_session"
    assert not _prod(enable_demo_auth=True).demo_auth_enabled


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"enable_demo_auth": True}, "ENABLE_DEMO_AUTH"),
        ({"cors_origins": ["http://localhost:5173"]}, "CORS_ORIGINS"),
        ({"cors_origins": []}, "CORS_ORIGINS"),
        ({"session_secret": "dev-only-insecure-secret-change-me"}, "SESSION_SECRET"),
        ({"session_secret": "change-me-to-a-long-random-string"}, "SESSION_SECRET"),  # .env.example
        ({"session_secret": "short-but-not-a-placeholder"}, "SESSION_SECRET"),
    ],
)
def test_production_refuses_unsafe_config(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(RuntimeError, match=message):
        _prod(**overrides).check_production()


def test_production_cookie_is_host_prefixed_and_secure() -> None:
    response = Response()
    set_session_cookie(response, "tok", _prod())
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-sd_session=tok")
    assert "Secure" in cookie and "HttpOnly" in cookie and "Path=/" in cookie
    assert "Domain" not in cookie
