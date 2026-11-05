"""Personal folders and tags (DOC-016, DOC-018; ADR-010)."""

from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.organization import normalize_tag
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


def _folder(client: TestClient, headers: Headers, name: str) -> dict[str, Any]:
    r = client.post("/api/folders", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _share(client: TestClient, doc_id: str, owner: Headers) -> None:
    grant = client.post(
        f"/api/documents/{doc_id}/grants", json={"email": "bob@demo.test"}, headers=owner
    )
    assert grant.is_success, grant.text


def _listed(client: TestClient, headers: Headers) -> dict[str, dict[str, Any]]:
    return {d["title"]: d for d in client.get("/api/documents", headers=headers).json()}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("POTA", "pota"), ("  field day ", "field-day"), ("K-4389", "k-4389"), ("c#/2m+", "c#/2m+")],
)
def test_normalize_tag(raw: str, expected: str) -> None:
    assert normalize_tag(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "x" * 33, "no<script>", "semi;colon"])
def test_normalize_tag_rejects(raw: str) -> None:
    with pytest.raises(ValueError, match="Tags"):
        normalize_tag(raw)


def test_folder_crud_and_unique_names(client: TestClient, alice: Headers) -> None:
    pota = _folder(client, alice, "  2026   POTA ")
    assert pota == {"id": pota["id"], "name": "2026 POTA", "document_count": 0}
    dup = client.post("/api/folders", json={"name": "2026 pota"}, headers=alice)
    assert dup.status_code == 409
    sats = _folder(client, alice, "Satellites")
    assert [f["name"] for f in client.get("/api/folders", headers=alice).json()] == [
        "2026 POTA",
        "Satellites",
    ]
    renamed = client.patch(f"/api/folders/{sats['id']}", json={"name": "Sats"}, headers=alice)
    assert renamed.status_code == 200 and renamed.json()["name"] == "Sats"
    clash = client.patch(f"/api/folders/{sats['id']}", json={"name": "2026 POTA"}, headers=alice)
    assert clash.status_code == 409
    assert client.post("/api/folders", json={"name": " "}, headers=alice).status_code == 422


def test_file_tag_and_list(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice)
    folder = _folder(client, alice, "POTA")
    before = client.get(f"/api/documents/{doc['id']}", headers=alice).json()

    r = client.put(
        f"/api/documents/{doc['id']}/folder", json={"folder_id": folder["id"]}, headers=alice
    )
    assert r.status_code == 200 and r.json() == {"folder_id": folder["id"]}
    r = client.put(
        f"/api/documents/{doc['id']}/tags",
        json={"tags": ["CW", "pota", "Pota", " cw "]},
        headers=alice,
    )
    assert r.json() == {"tags": ["cw", "pota"]}

    item = _listed(client, alice)["Field notes"]
    assert (item["folder_id"], item["tags"]) == (folder["id"], ["cw", "pota"])
    got = client.get(f"/api/documents/{doc['id']}", headers=alice).json()
    assert (got["folder_id"], got["tags"]) == (folder["id"], ["cw", "pota"])
    # Organising is not an edit.
    assert (got["revision"], got["updated_at"]) == (before["revision"], before["updated_at"])

    assert client.get("/api/folders", headers=alice).json()[0]["document_count"] == 1
    summary = client.get("/api/tags", headers=alice).json()
    assert summary["tags"] == [{"tag": "cw", "count": 1}, {"tag": "pota", "count": 1}]
    assert "satellite" in summary["suggestions"]

    client.put(f"/api/documents/{doc['id']}/folder", json={"folder_id": None}, headers=alice)
    client.put(f"/api/documents/{doc['id']}/tags", json={"tags": []}, headers=alice)
    item = _listed(client, alice)["Field notes"]
    assert (item["folder_id"], item["tags"]) == (None, [])


def test_too_many_tags_rejected(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice)
    tags = [f"t{i}" for i in range(21)]
    r = client.put(f"/api/documents/{doc['id']}/tags", json={"tags": tags}, headers=alice)
    assert r.status_code == 422


def test_organisation_is_personal(client: TestClient, alice: Headers, bob: Headers) -> None:
    """Owner and viewer each organise the same shared document; neither sees the other's."""
    doc = _doc(client, alice)
    _share(client, doc["id"], alice)
    a_folder, b_folder = _folder(client, alice, "Mine"), _folder(client, bob, "Mine")
    url = f"/api/documents/{doc['id']}"
    client.put(f"{url}/folder", json={"folder_id": a_folder["id"]}, headers=alice)
    client.put(f"{url}/tags", json={"tags": ["owner-tag"]}, headers=alice)
    client.put(f"{url}/folder", json={"folder_id": b_folder["id"]}, headers=bob)
    client.put(f"{url}/tags", json={"tags": ["viewer-tag"]}, headers=bob)

    a, b = _listed(client, alice)["Field notes"], _listed(client, bob)["Field notes"]
    assert (a["folder_id"], a["tags"]) == (a_folder["id"], ["owner-tag"])
    assert (b["folder_id"], b["tags"]) == (b_folder["id"], ["viewer-tag"])
    assert client.get(url, headers=bob).json()["tags"] == ["viewer-tag"]
    assert [t["tag"] for t in client.get("/api/tags", headers=bob).json()["tags"]] == ["viewer-tag"]


def test_other_users_folders_look_missing(client: TestClient, alice: Headers, bob: Headers) -> None:
    doc = _doc(client, bob, "Bob's")
    alices = _folder(client, alice, "Private")
    missing = 999_999
    for folder_id in (alices["id"], missing):
        assert (
            client.patch(f"/api/folders/{folder_id}", json={"name": "x"}, headers=bob).status_code
            == 404
        )
        assert client.delete(f"/api/folders/{folder_id}", headers=bob).status_code == 404
        filed = client.put(
            f"/api/documents/{doc['id']}/folder", json={"folder_id": folder_id}, headers=bob
        )
        assert filed.status_code == 404
    assert [f["name"] for f in client.get("/api/folders", headers=bob).json()] == []
    client.cookies.clear()  # anonymous: no jar cookie from the logins above
    assert client.get("/api/folders").status_code == 401
    assert client.get("/api/folders", headers=alice).json()[0]["name"] == "Private"


def test_deleting_a_folder_ungroups_documents(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice)
    folder = _folder(client, alice, "Temp")
    client.put(
        f"/api/documents/{doc['id']}/folder", json={"folder_id": folder["id"]}, headers=alice
    )
    assert client.delete(f"/api/folders/{folder['id']}", headers=alice).status_code == 204
    item = _listed(client, alice)["Field notes"]
    assert item["folder_id"] is None
    assert client.get(f"/api/documents/{doc['id']}", headers=alice).status_code == 200


def test_counts_skip_archived_and_revoked(client: TestClient, alice: Headers, bob: Headers) -> None:
    kept, archived, shared = (
        _doc(client, alice, "Kept"),
        _doc(client, alice, "Old"),
        _doc(client, alice, "Shared"),
    )
    _share(client, shared["id"], alice)
    a_folder, b_folder = _folder(client, alice, "F"), _folder(client, bob, "F")
    for d in (kept, archived):
        client.put(
            f"/api/documents/{d['id']}/folder", json={"folder_id": a_folder["id"]}, headers=alice
        )
        client.put(f"/api/documents/{d['id']}/tags", json={"tags": ["x"]}, headers=alice)
    client.post(f"/api/documents/{archived['id']}/archive", headers=alice)
    client.put(
        f"/api/documents/{shared['id']}/folder", json={"folder_id": b_folder["id"]}, headers=bob
    )
    client.put(f"/api/documents/{shared['id']}/tags", json={"tags": ["y"]}, headers=bob)

    assert client.get("/api/folders", headers=alice).json()[0]["document_count"] == 1
    assert client.get("/api/tags", headers=alice).json()["tags"] == [{"tag": "x", "count": 1}]
    assert client.get("/api/folders", headers=bob).json()[0]["document_count"] == 1

    bob_id = client.get("/api/me", headers=bob).json()["id"]
    client.delete(f"/api/documents/{shared['id']}/grants/{bob_id}", headers=alice)
    assert client.get("/api/folders", headers=bob).json()[0]["document_count"] == 0
    assert client.get("/api/tags", headers=bob).json()["tags"] == []


def test_archived_documents_can_still_be_organised(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice)
    client.post(f"/api/documents/{doc['id']}/archive", headers=alice)
    r = client.put(f"/api/documents/{doc['id']}/tags", json={"tags": ["retired"]}, headers=alice)
    assert r.status_code == 200


def test_duplicate_copies_the_callers_organisation(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice)
    _share(client, doc["id"], alice)
    a_folder, b_folder = _folder(client, alice, "A"), _folder(client, bob, "B")
    url = f"/api/documents/{doc['id']}"
    client.put(f"{url}/folder", json={"folder_id": a_folder["id"]}, headers=alice)
    client.put(f"{url}/tags", json={"tags": ["alice"]}, headers=alice)
    client.put(f"{url}/folder", json={"folder_id": b_folder["id"]}, headers=bob)
    client.put(f"{url}/tags", json={"tags": ["bob"]}, headers=bob)

    mine = client.post(f"{url}/duplicate", headers=alice).json()
    assert (mine["folder_id"], mine["tags"]) == (a_folder["id"], ["alice"])
    bobs = client.post(f"{url}/duplicate", headers=bob).json()
    assert (bobs["folder_id"], bobs["tags"]) == (b_folder["id"], ["bob"])
    plain = client.post(
        f"/api/documents/{_doc(client, alice, 'Plain')['id']}/duplicate", headers=alice
    )
    assert (plain.json()["folder_id"], plain.json()["tags"]) == (None, [])


def test_existing_documents_survive_the_migration(engine: Engine, database_url: str) -> None:
    """Acceptance: documents created before 0005 stay readable, unfiled and untagged."""
    # Inserted at 0004 (after the search migration), so 0005 is the only step under test.
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    engine.dispose()
    command.downgrade(cfg, "0004")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (display_name, email) VALUES ('Pre', 'pre5@x.io')")
            )
            uid = conn.execute(text("SELECT id FROM users WHERE email = 'pre5@x.io'")).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO documents (id, owner_id, title, content_json, revision, "
                    "created_at, updated_at) VALUES (:id, :uid, 'Old plan', :c, 2, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "uid": uid,
                    "c": '{"type": "doc", "content": [{"type": "paragraph"}]}',
                },
            )
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            title = conn.execute(
                text("SELECT title FROM documents WHERE owner_id = :u"), {"u": uid}
            )
            assert title.scalar_one() == "Old plan"
            for table in ("document_folders", "document_tags", "folders"):
                n = conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE user_id = :u"), {"u": uid}
                )  # noqa: S608
                assert n.scalar_one() == 0
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM documents WHERE title = 'Old plan'"))
            conn.execute(text("DELETE FROM users WHERE email = 'pre5@x.io'"))


def test_search_filters_by_the_callers_folder_and_tag(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    filed, loose = _doc(client, alice, "Antenna filed"), _doc(client, alice, "Antenna loose")
    folder = _folder(client, alice, "Antennas")
    client.put(
        f"/api/documents/{filed['id']}/folder", json={"folder_id": folder["id"]}, headers=alice
    )
    client.put(f"/api/documents/{filed['id']}/tags", json={"tags": ["efhw"]}, headers=alice)

    def titles(**params: str) -> list[str]:
        r = client.get("/api/documents/search", params={"q": "antenna", **params}, headers=alice)
        assert r.status_code == 200, r.text
        return sorted(d["title"] for d in r.json())

    assert titles() == ["Antenna filed", "Antenna loose"]
    assert titles(folder=str(folder["id"])) == ["Antenna filed"]
    assert titles(folder="unfiled") == ["Antenna loose"]
    assert titles(tag="EFHW") == ["Antenna filed"]
    assert titles(tag="nope") == [] and titles(tag="bad<tag") == []
    hit = client.get("/api/documents/search", params={"q": "filed"}, headers=alice).json()[0]
    assert (hit["folder_id"], hit["tags"]) == (folder["id"], ["efhw"])
    bad = client.get("/api/documents/search", params={"q": "a", "folder": "x"}, headers=alice)
    assert bad.status_code == 422

    # Bob's view of Alice's folder id finds nothing, even for a document shared with him.
    _share(client, filed["id"], alice)
    r = client.get(
        "/api/documents/search", params={"q": "antenna", "folder": str(folder["id"])}, headers=bob
    )
    assert r.json() == []
    assert loose  # unfiled doc exists for the "unfiled" assertion above
