"""SEC-01 / OPS: rate limits, request ids, security headers, commit reporting, restart."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import get_db
from app.main import create_app
from app.observability import JsonFormatter, request_id_var
from app.ratelimit import SlidingWindowLimiter
from app.storage import MemoryStorage, get_storage, optional_storage


def test_sliding_window_limiter() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=10)
    assert limiter.hit("k", now=0) is None
    assert limiter.hit("k", now=1) is None
    assert limiter.hit("k", now=2) == pytest.approx(8)
    assert limiter.hit("other", now=2) is None
    assert limiter.hit("k", now=10.5) is None  # first hit expired


def test_login_is_rate_limited(client: TestClient) -> None:
    limit = get_settings().login_rate_limit_per_minute
    for _ in range(limit):
        assert client.post("/api/demo/login", json={"login_key": "alice"}).status_code == 200
    r = client.post("/api/demo/login", json={"login_key": "alice"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1


def test_uploads_are_rate_limited_per_user(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob = login("alice"), login("bob")
    files = {"file": ("a.txt", b"hello", "text/plain")}
    limit = get_settings().upload_rate_limit_per_minute
    for _ in range(limit):
        assert client.post("/api/imports", files=files, headers=alice).status_code == 200
    assert client.post("/api/imports", files=files, headers=alice).status_code == 429
    assert client.post("/api/imports", files=files, headers=bob).status_code == 200


def test_security_headers_and_request_id(client: TestClient) -> None:
    r = client.get("/health/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert len(r.headers["x-request-id"]) == 32
    unsafe = client.get("/health/live", headers={"X-Request-ID": "bad id\r\nx: y"})
    assert unsafe.headers["x-request-id"] != "bad id\r\nx: y"


def test_live_reports_commit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc1234")
    get_settings.cache_clear()
    try:
        assert client.get("/health/live").json() == {"status": "ok", "commit": "abc1234"}
    finally:
        get_settings.cache_clear()


def test_json_logs_carry_request_id() -> None:
    record = logging.makeLogRecord(
        {"name": "app.access", "levelno": 20, "levelname": "INFO", "msg": "request"}
    )
    record.status = 200
    token = request_id_var.set("rid-1")
    try:
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["request_id"] == "rid-1"
    assert line["status"] == 200
    assert line["msg"] == "request"


def test_data_survives_api_restart(engine: Engine, login, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    """Demo step 9: content, formatting and grants persist across a fresh app + DB session."""
    alice = login("alice")
    content = {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "H"}]},
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "b", "marks": [{"type": "bold"}]}],
            },
        ],
    }
    doc = client.post(
        "/api/documents", json={"title": "Persist", "content_json": content}, headers=alice
    ).json()
    bob_id = client.get("/api/me", headers=login("bob")).json()["id"]
    client.post(f"/api/documents/{doc['id']}/grants", json={"user_id": bob_id}, headers=alice)

    # "Restart": brand-new app instance and a brand-new DB session on the same database.
    fresh_session = sessionmaker(bind=engine, expire_on_commit=False)()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: fresh_session
    app.dependency_overrides[get_storage] = MemoryStorage
    app.dependency_overrides[optional_storage] = MemoryStorage
    try:
        with TestClient(app) as restarted:
            reopened = restarted.get(f"/api/documents/{doc['id']}", headers=alice).json()
            assert reopened["content_json"] == content
            shared = restarted.get("/api/documents", headers=login("bob")).json()
            assert [d["id"] for d in shared] == [doc["id"]]
    finally:
        fresh_session.close()
