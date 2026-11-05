"""Identity schema and invite allowlist (ADR-009, DOC-002)."""

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.allowlist import allow, disallow, is_allowed, list_allowed, normalize_email
from app.models import AllowedEmail, Document, User, UserIdentity, UserSession, utcnow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import allow_email  # noqa: E402


def _oauth_user(db: Session, email: str = "op@example.com") -> User:
    user = User(email=email, display_name="Operator")
    db.add(user)
    db.commit()
    return user


def _session(db: Session, user: User, token_hash: str) -> UserSession:
    s = UserSession(token_hash=token_hash, user_id=user.id, expires_at=utcnow() + timedelta(days=1))
    db.add(s)
    db.commit()
    return s


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Op@Example.COM ", "op@example.com"),
        ("a.b+tag@sub.example.org", "a.b+tag@sub.example.org"),
    ],
)
def test_normalize_email(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["", "no-at-sign", "two@@example.com", "sp ace@example.com", "a@b"])
def test_normalize_email_rejects_typos(raw: str) -> None:
    with pytest.raises(ValueError, match="valid email"):
        normalize_email(raw)


def test_allow_is_idempotent_and_case_insensitive(db: Session) -> None:
    assert allow(db, "Op@Example.com", note="club") is True
    assert allow(db, "op@example.com") is False
    assert is_allowed(db, "OP@EXAMPLE.COM")
    assert [(e.email, e.note) for e in list_allowed(db)] == [("op@example.com", "club")]


def test_disallow_ends_sessions_but_keeps_user_and_documents(db: Session) -> None:
    allow(db, "op@example.com")
    user = _oauth_user(db)
    other = _oauth_user(db, "other@example.com")
    _session(db, user, "a" * 64)
    _session(db, user, "b" * 64)
    _session(db, other, "c" * 64)
    db.add(Document(owner_id=user.id, title="Field notes"))
    db.commit()

    result = disallow(db, "OP@example.com")

    assert result.removed and result.sessions_ended == 2
    assert not is_allowed(db, "op@example.com")
    remaining = db.scalars(select(UserSession.user_id)).all()
    assert remaining == [other.id]
    assert db.get(User, user.id) is not None
    assert db.scalar(select(Document.title).where(Document.owner_id == user.id)) == "Field notes"


def test_disallow_unknown_email(db: Session) -> None:
    result = disallow(db, "nobody@example.com")
    assert not result.removed and result.sessions_ended == 0


def test_identity_unique_per_provider_subject(db: Session) -> None:
    user = _oauth_user(db)
    db.add(
        UserIdentity(user_id=user.id, provider="github", provider_subject="42", email=user.email)
    )
    db.commit()
    # Same subject at another provider is a different account.
    db.add(
        UserIdentity(user_id=user.id, provider="google", provider_subject="42", email=user.email)
    )
    db.commit()
    db.add(UserIdentity(user_id=user.id, provider="github", provider_subject="42", email="x@y.io"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_identity_provider_is_constrained(db: Session) -> None:
    user = _oauth_user(db)
    db.add(UserIdentity(user_id=user.id, provider="myspace", provider_subject="1", email="a@b.co"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_user_email_unique_and_lowercase(db: Session) -> None:
    _oauth_user(db, "op@example.com")
    db.add(User(email="op@example.com", display_name="Dup"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(User(email="Mixed@Example.com", display_name="Mixed"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(AllowedEmail(email="Mixed@Example.com"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_session_token_hash_unique(db: Session) -> None:
    user = _oauth_user(db)
    _session(db, user, "d" * 64)
    db.add(UserSession(token_hash="d" * 64, user_id=user.id, expires_at=utcnow()))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deleting_user_cascades_identities_and_sessions(db: Session) -> None:
    user = _oauth_user(db)
    db.add(UserIdentity(user_id=user.id, provider="google", provider_subject="s", email="o@e.co"))
    _session(db, user, "e" * 64)
    db.delete(user)
    db.commit()
    db.expire_all()
    assert db.scalar(select(UserIdentity)) is None
    assert db.scalar(select(UserSession)) is None


def test_demo_user_list_excludes_real_accounts(client: TestClient, db: Session) -> None:
    _oauth_user(db)
    keys = [u["login_key"] for u in client.get("/api/demo/users").json()]
    assert keys == ["alice", "bob", "charlie"]


def test_cli_add_list_remove(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(allow_email, "get_sessionmaker", lambda: lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)  # the CLI's `with` must not close the fixture

    assert allow_email.main(["add", "Op@Example.com", "--note", "club"]) == 0
    assert allow_email.main(["list"]) == 0
    assert allow_email.main(["remove", "op@example.com"]) == 0
    assert allow_email.main(["remove", "op@example.com"]) == 1
    assert allow_email.main(["add", "not-an-email"]) == 2
    out = capsys.readouterr()
    assert "Added op@example.com" in out.out
    assert "op@example.com\tclub" in out.out
    assert "Removed op@example.com; ended 0 session(s)" in out.out
    assert "valid email" in out.err
