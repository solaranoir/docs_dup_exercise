"""Archive/restore, duplicate, recently opened and list metadata (DOC-019..022)."""

from collections.abc import Callable

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.routes.documents import TITLE_MAX, copy_title
from tests.conftest import BACKEND

Headers = dict[str, str]


@pytest.fixture
def alice(login: Callable[[str], Headers]) -> Headers:
    return login("alice")


@pytest.fixture
def bob(login: Callable[[str], Headers]) -> Headers:
    return login("bob")


def _doc(client: TestClient, headers: Headers, title: str = "Field notes") -> dict:  # type: ignore[type-arg]
    content = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "73"}]}],
    }
    r = client.post(
        "/api/documents", json={"title": title, "content_json": content}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _share(client: TestClient, doc_id: str, owner: Headers) -> None:
    r = client.post(
        f"/api/documents/{doc_id}/grants", json={"email": "bob@demo.test"}, headers=owner
    )
    assert r.is_success, r.text


def _ids(client: TestClient, headers: Headers, archived: bool = False) -> list[str]:
    r = client.get("/api/documents", params={"archived": archived}, headers=headers)
    return [d["id"] for d in r.json()]


def test_summary_has_timestamps_for_sorting(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice)
    [item] = client.get("/api/documents", headers=alice).json()
    assert item["id"] == doc["id"]
    assert {"created_at", "updated_at", "archived_at", "last_opened_at"} <= item.keys()
    assert item["archived_at"] is None


def test_archive_hides_for_everyone_and_restore_brings_it_back(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice)
    _share(client, doc["id"], alice)
    before = client.get(f"/api/documents/{doc['id']}", headers=alice).json()

    r = client.post(f"/api/documents/{doc['id']}/archive", headers=alice)
    assert r.status_code == 200 and r.json()["archived_at"] is not None
    # Archiving is not an edit: revision and updated_at are unchanged.
    assert (r.json()["revision"], r.json()["updated_at"]) == (
        before["revision"],
        before["updated_at"],
    )
    assert client.post(f"/api/documents/{doc['id']}/archive", headers=alice).status_code == 200

    assert _ids(client, alice) == [] and _ids(client, bob) == []
    assert _ids(client, alice, archived=True) == [doc["id"]]
    assert _ids(client, bob, archived=True) == [doc["id"]]
    # Still reachable by link, for the owner and the viewer.
    for who in (alice, bob):
        got = client.get(f"/api/documents/{doc['id']}", headers=who)
        assert got.status_code == 200 and got.json()["archived_at"] is not None

    r = client.post(f"/api/documents/{doc['id']}/restore", headers=alice)
    assert r.status_code == 200 and r.json()["archived_at"] is None
    assert _ids(client, alice) == [doc["id"]] and _ids(client, bob) == [doc["id"]]
    assert _ids(client, alice, archived=True) == []


def test_archived_documents_are_read_only_until_restored(
    client: TestClient, alice: Headers
) -> None:
    doc = _doc(client, alice)
    client.post(f"/api/documents/{doc['id']}/archive", headers=alice)
    base = f"/api/documents/{doc['id']}"

    patch = client.patch(base, json={"expected_revision": 1, "title": "New"}, headers=alice)
    assert patch.status_code == 409 and "archived" in patch.json()["detail"]
    upload = client.post(
        f"{base}/attachments", files={"file": ("a.txt", b"x", "text/plain")}, headers=alice
    )
    assert upload.status_code == 409
    imported = client.post(
        f"{base}/imports",
        files={"file": ("a.md", b"# Hi", "text/markdown")},
        data={"mode": "append", "expected_revision": "1"},
        headers=alice,
    )
    assert imported.status_code == 409

    client.post(f"{base}/restore", headers=alice)
    patch = client.patch(base, json={"expected_revision": 1, "title": "New"}, headers=alice)
    assert patch.status_code == 200


def test_only_the_owner_archives_or_restores(
    client: TestClient, alice: Headers, bob: Headers, login: Callable[[str], Headers]
) -> None:
    doc = _doc(client, alice)
    _share(client, doc["id"], alice)
    charlie = login("charlie")
    for action in ("archive", "restore"):
        assert client.post(f"/api/documents/{doc['id']}/{action}", headers=bob).status_code == 403
        assert (
            client.post(f"/api/documents/{doc['id']}/{action}", headers=charlie).status_code == 404
        )
    assert client.get(f"/api/documents/{doc['id']}", headers=alice).json()["archived_at"] is None


def test_duplicate_copies_title_and_content_only(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice)
    _share(client, doc["id"], alice)
    client.post(
        f"/api/documents/{doc['id']}/attachments",
        files={"file": ("log.txt", b"73", "text/plain")},
        headers=alice,
    )
    client.post(f"/api/documents/{doc['id']}/archive", headers=alice)

    r = client.post(f"/api/documents/{doc['id']}/duplicate", headers=alice)
    assert r.status_code == 201, r.text
    copy = r.json()
    assert copy["id"] != doc["id"]
    assert copy["title"] == "Copy of Field notes"
    assert copy["content_json"] == doc["content_json"]
    assert (copy["permission"], copy["revision"], copy["archived_at"]) == ("owner", 1, None)
    assert client.get(f"/api/documents/{copy['id']}/attachments", headers=alice).json() == []
    assert client.get(f"/api/documents/{copy['id']}/grants", headers=alice).json() == []
    assert client.get(f"/api/documents/{copy['id']}", headers=bob).status_code == 404


def test_viewer_can_duplicate_into_their_own_document(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice)
    _share(client, doc["id"], alice)
    copy = client.post(f"/api/documents/{doc['id']}/duplicate", headers=bob).json()
    assert copy["permission"] == "owner" and copy["owner"]["display_name"].startswith("Bob")
    edit = client.patch(
        f"/api/documents/{copy['id']}", json={"expected_revision": 1, "title": "Mine"}, headers=bob
    )
    assert edit.status_code == 200
    assert client.get(f"/api/documents/{doc['id']}", headers=alice).json()["title"] == "Field notes"


def test_copy_title_fits_the_limit() -> None:
    long = "x" * TITLE_MAX
    assert len(copy_title(long)) == TITLE_MAX
    assert copy_title("Plan") == "Copy of Plan"


def test_opening_records_a_per_user_visit(client: TestClient, alice: Headers, bob: Headers) -> None:
    first = _doc(client, alice, "First")
    _doc(client, alice, "Second")
    _share(client, first["id"], alice)

    def opened(headers: Headers) -> dict[str, str | None]:
        return {
            d["title"]: d["last_opened_at"]
            for d in client.get("/api/documents", headers=headers).json()
        }

    assert opened(alice) == {"First": None, "Second": None}
    got = client.get(f"/api/documents/{first['id']}", headers=alice).json()
    assert got["last_opened_at"] is not None
    client.get(f"/api/documents/{first['id']}", headers=alice)  # second open: upsert, no error
    after = opened(alice)
    assert after["First"] is not None and after["Second"] is None
    assert opened(bob) == {"First": None}  # Alice's visits are hers alone

    client.get(f"/api/documents/{first['id']}", headers=bob)
    assert opened(bob)["First"] is not None


def test_existing_documents_survive_the_migration(engine: Engine, database_url: str) -> None:
    """Acceptance: records created before 0003 stay visible and unarchived afterwards."""
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    engine.dispose()
    command.downgrade(cfg, "0002")
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (display_name, email) VALUES ('Pre', 'pre@x.io')"))
            uid = conn.execute(text("SELECT id FROM users WHERE email = 'pre@x.io'")).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO documents (id, owner_id, title, content_json, revision, "
                    "created_at, updated_at) VALUES (:id, :uid, 'Old log', :c, 3, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "uid": uid,
                    "c": '{"type": "doc", "content": [{"type": "paragraph"}]}',
                },
            )
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT title, revision, archived_at FROM documents WHERE owner_id = :u"),
                {"u": uid},
            ).one()
        assert tuple(row) == ("Old log", 3, None)
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM documents WHERE title = 'Old log'"))
            conn.execute(text("DELETE FROM users WHERE email = 'pre@x.io'"))
