"""Trash with 30-day recovery (DOC-031; ADR-012)."""

import io
import uuid
import zipfile
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text, update
from sqlalchemy.orm import Session

from app.models import Document, utcnow
from app.storage import MemoryStorage
from app.trash import TRASH_DAYS, purge_expired
from tests.conftest import BACKEND

Headers = dict[str, str]


@pytest.fixture
def alice(login: Callable[[str], Headers]) -> Headers:
    return login("alice")


@pytest.fixture
def bob(login: Callable[[str], Headers]) -> Headers:
    return login("bob")


def _doc(client: TestClient, headers: Headers, title: str = "Field notes") -> dict[str, Any]:
    r = client.post("/api/documents", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _share(client: TestClient, doc_id: str, owner: Headers) -> None:
    r = client.post(
        f"/api/documents/{doc_id}/grants", json={"email": "bob@demo.test"}, headers=owner
    )
    assert r.is_success, r.text


def _attach(client: TestClient, headers: Headers, doc_id: str, data: bytes) -> str:
    r = client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": ("log.txt", data, "text/plain")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]  # type: ignore[no-any-return]


def _ids(client: TestClient, headers: Headers, path: str = "/api/documents") -> list[str]:
    return [d["id"] for d in client.get(path, headers=headers).json()]


def _trash(client: TestClient, headers: Headers) -> list[dict[str, Any]]:
    r = client.get("/api/trash", headers=headers)
    assert r.status_code == 200
    assert r.json()["retention_days"] == TRASH_DAYS
    return r.json()["items"]  # type: ignore[no-any-return]


def _backdate(db: Session, doc_id: str, days: float) -> None:
    db.execute(
        update(Document)
        .where(Document.id == uuid.UUID(doc_id))
        .values(deleted_at=utcnow() - timedelta(days=days))
    )
    db.commit()


def test_delete_moves_to_trash_and_restore_brings_it_back(
    client: TestClient, alice: Headers
) -> None:
    doc = _doc(client, alice)
    url = f"/api/documents/{doc['id']}"
    assert client.delete(url, headers=alice).status_code == 204

    assert client.get(url, headers=alice).status_code == 404  # looks missing, even to the owner
    assert doc["id"] not in _ids(client, alice)
    assert doc["id"] not in _ids(client, alice, "/api/documents?archived=true")
    (item,) = _trash(client, alice)
    assert item["id"] == doc["id"] and item["title"] == "Field notes"
    assert item["updated_at"] == doc["updated_at"]  # deleting is not an edit
    deleted = item["deleted_at"]
    assert item["purge_after"] > deleted

    r = client.post(f"/api/trash/{doc['id']}/restore", headers=alice)
    assert r.status_code == 200
    back = client.get(url, headers=alice).json()
    assert (back["title"], back["revision"], back["updated_at"]) == (
        "Field notes",
        doc["revision"],
        doc["updated_at"],
    )
    assert _trash(client, alice) == []
    assert doc["id"] in _ids(client, alice)


def test_trash_hides_the_document_everywhere_and_restore_keeps_everything(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice, "Antenna plan")
    url = f"/api/documents/{doc['id']}"
    _share(client, doc["id"], alice)
    att = _attach(client, alice, doc["id"], b"1.3:1")
    folder = client.post("/api/folders", json={"name": "Antennas"}, headers=alice).json()
    client.put(f"{url}/folder", json={"folder_id": folder["id"]}, headers=alice)
    client.put(f"{url}/tags", json={"tags": ["efhw"]}, headers=alice)
    client.put(f"{url}/tags", json={"tags": ["bobs"]}, headers=bob)
    client.post(f"{url}/archive", headers=alice)
    assert client.delete(url, headers=alice).status_code == 204

    # Gone for the viewer and from every list, search, count and sub-route.
    assert client.get(url, headers=bob).status_code == 404
    assert doc["id"] not in _ids(client, bob)
    for headers in (alice, bob):
        hits = client.get("/api/documents/search", params={"q": "antenna"}, headers=headers)
        assert hits.json() == []
    assert client.get("/api/tags", headers=alice).json()["tags"] == []
    assert client.get("/api/folders", headers=alice).json()[0]["document_count"] == 0
    for suffix in ("/attachments", f"/attachments/{att}", "/grants", "/export"):
        assert client.get(f"{url}{suffix}", headers=alice).status_code == 404
    assert client.post(f"{url}/restore", headers=alice).status_code == 404  # archive restore
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=alice).content))
    assert not any("antenna-plan" in n for n in archive.namelist())

    # Restore: grants, attachments, folder, tags and the archive state all come back.
    assert client.post(f"/api/trash/{doc['id']}/restore", headers=alice).status_code == 200
    assert client.get(url, headers=bob).status_code == 200
    back = client.get(url, headers=alice).json()
    assert back["archived_at"] is not None
    assert (back["folder_id"], back["tags"]) == (folder["id"], ["efhw"])
    assert client.get(url, headers=bob).json()["tags"] == ["bobs"]
    assert client.get(f"{url}/attachments/{att}", headers=alice).content == b"1.3:1"


def test_only_the_owner_has_a_trash(
    client: TestClient, alice: Headers, bob: Headers, login: Callable[[str], Headers]
) -> None:
    charlie = login("charlie")
    doc = _doc(client, alice)
    live = _doc(client, alice, "Live")
    _share(client, doc["id"], alice)
    assert client.delete(f"/api/documents/{doc['id']}", headers=bob).status_code == 403
    assert client.delete(f"/api/documents/{doc['id']}", headers=charlie).status_code == 404
    client.delete(f"/api/documents/{doc['id']}", headers=alice)

    for headers in (bob, charlie):
        assert _trash(client, headers) == []
        for method, path in (("POST", "/restore"), ("DELETE", "")):
            r = client.request(method, f"/api/trash/{doc['id']}{path}", headers=headers)
            assert r.status_code == 404
    # A live document is not in anyone's Trash.
    assert client.post(f"/api/trash/{live['id']}/restore", headers=alice).status_code == 404
    assert client.delete(f"/api/trash/{live['id']}", headers=alice).status_code == 404
    assert client.get(f"/api/documents/{live['id']}", headers=alice).status_code == 200
    # Deleting twice: the second time it already looks missing.
    assert client.delete(f"/api/documents/{doc['id']}", headers=alice).status_code == 404
    client.cookies.clear()
    assert client.get("/api/trash").status_code == 401
    assert client.post(f"/api/trash/{doc['id']}/restore").status_code == 401


def test_delete_forever_removes_the_document_and_its_files(
    client: TestClient, alice: Headers, storage: MemoryStorage
) -> None:
    doc = _doc(client, alice)
    _attach(client, alice, doc["id"], b"x")
    client.delete(f"/api/documents/{doc['id']}", headers=alice)
    assert len(storage.objects) == 1
    assert client.delete(f"/api/trash/{doc['id']}", headers=alice).status_code == 204
    assert storage.objects == {}
    assert _trash(client, alice) == []
    assert client.post(f"/api/trash/{doc['id']}/restore", headers=alice).status_code == 404


def test_purge_removes_only_documents_past_retention(
    client: TestClient, alice: Headers, db: Session, storage: MemoryStorage
) -> None:
    old, recent, live = (
        _doc(client, alice, "Old"),
        _doc(client, alice, "Recent"),
        _doc(client, alice, "Live"),
    )
    _attach(client, alice, old["id"], b"old")
    _attach(client, alice, recent["id"], b"recent")
    for d in (old, recent):
        client.delete(f"/api/documents/{d['id']}", headers=alice)
    _backdate(db, old["id"], TRASH_DAYS + 0.01)
    _backdate(db, recent["id"], TRASH_DAYS - 1)

    result = purge_expired(db, storage)
    assert result.documents == 1 and result.orphaned_keys == []
    assert [i["title"] for i in _trash(client, alice)] == ["Recent"]
    assert [v[0] for v in storage.objects.values()] == [b"recent"]
    assert client.get(f"/api/documents/{live['id']}", headers=alice).status_code == 200


def test_listing_documents_purges_expired_trash_at_most_hourly(
    client: TestClient, alice: Headers, db: Session
) -> None:
    first, second = _doc(client, alice, "First"), _doc(client, alice, "Second")
    client.delete(f"/api/documents/{first['id']}", headers=alice)
    _backdate(db, first["id"], TRASH_DAYS + 1)
    client.get("/api/documents", headers=alice)  # runs the purge after responding
    assert _trash(client, alice) == []

    client.delete(f"/api/documents/{second['id']}", headers=alice)
    _backdate(db, second["id"], TRASH_DAYS + 1)
    client.get("/api/documents", headers=alice)  # within the hour: no second purge
    assert [i["title"] for i in _trash(client, alice)] == ["Second"]


def test_existing_documents_survive_the_migration(engine: Engine, database_url: str) -> None:
    """Acceptance: documents created before 0006 stay live (not in anyone's Trash)."""
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    engine.dispose()
    command.downgrade(cfg, "0005")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (display_name, email) VALUES ('Pre', 'pre6@x.io')")
            )
            uid = conn.execute(text("SELECT id FROM users WHERE email = 'pre6@x.io'")).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO documents (id, owner_id, title, content_json, revision, "
                    "created_at, updated_at) VALUES (:id, :uid, 'Old log', :c, 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "66666666-6666-6666-6666-666666666666",
                    "uid": uid,
                    "c": '{"type": "doc", "content": [{"type": "paragraph"}]}',
                },
            )
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT title, deleted_at FROM documents WHERE owner_id = :u"), {"u": uid}
            ).one()
            assert tuple(row) == ("Old log", None)
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM documents WHERE title = 'Old log'"))
            conn.execute(text("DELETE FROM users WHERE email = 'pre6@x.io'"))
