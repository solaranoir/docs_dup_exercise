from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.seed import seed_demo_users


def test_seed_is_idempotent(db: Session) -> None:
    seed_demo_users(db)
    seed_demo_users(db)
    assert db.scalar(select(func.count()).select_from(User)) == 3


def test_demo_users_listed(client: TestClient) -> None:
    keys = [u["login_key"] for u in client.get("/api/demo/users").json()]
    assert keys == ["alice", "bob", "charlie"]


def test_identity_switch(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    for key in ("alice", "bob", "charlie"):
        assert client.get("/api/me", headers=login(key)).json()["login_key"] == key


def test_cookie_session(client: TestClient) -> None:
    client.post("/api/demo/login", json={"login_key": "bob"})
    assert client.get("/api/me").json()["login_key"] == "bob"
    client.post("/api/demo/logout")
    assert client.get("/api/me").status_code == 401


def test_unknown_user_rejected(client: TestClient) -> None:
    assert client.post("/api/demo/login", json={"login_key": "mallory"}).status_code == 404


def test_unauthenticated_and_tampered_tokens_rejected(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/me").status_code == 401
    headers = login("alice")
    headers["Authorization"] += "x"
    client.cookies.clear()
    assert client.get("/api/me", headers=headers).status_code == 401


def test_principal_cannot_be_chosen_by_client(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    headers = login("charlie") | {"X-User-Id": "1"}
    r = client.get("/api/me?user_id=1", headers=headers)
    assert r.json()["login_key"] == "charlie"
