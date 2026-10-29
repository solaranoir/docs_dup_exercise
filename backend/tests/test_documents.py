from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DocumentGrant, User

RICH: dict[str, Any] = {
    "type": "doc",
    "content": [
        {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Q3"}]},
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "bold", "marks": [{"type": "bold"}]},
                {
                    "type": "text",
                    "text": " big",
                    "marks": [{"type": "textStyle", "attrs": {"fontSize": "1.5rem"}}],
                },
            ],
        },
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}],
                }
            ],
        },
        {"type": "orderedList", "attrs": {"start": 1, "type": None}, "content": []},
    ],
}


def _create(client: TestClient, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    r = client.post("/api/documents", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_create_defaults_to_untitled_empty_draft(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    doc = _create(client, login("alice"))
    assert doc["title"] == "Untitled document"
    assert doc["revision"] == 1
    assert doc["permission"] == "owner"
    assert doc["content_json"]["type"] == "doc"


def test_create_save_reopen_preserves_structure(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc = _create(client, alice, title="  Quarterly Notes  ")
    assert doc["title"] == "Quarterly Notes"
    r = client.patch(
        f"/api/documents/{doc['id']}",
        json={"expected_revision": 1, "content_json": RICH},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    assert r.json()["revision"] == 2
    reopened = client.get(f"/api/documents/{doc['id']}", headers=alice).json()
    assert reopened["content_json"] == RICH
    assert reopened["revision"] == 2


def test_list_is_scoped_to_principal(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    _create(client, login("alice"), title="Alice doc")
    _create(client, login("bob"), title="Bob doc")
    titles = [d["title"] for d in client.get("/api/documents", headers=login("alice")).json()]
    assert titles == ["Alice doc"]


def test_rename_validates_title(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc = _create(client, alice)
    url = f"/api/documents/{doc['id']}"
    for bad in ("   ", "x" * 161):
        r = client.patch(url, json={"expected_revision": 1, "title": bad}, headers=alice)
        assert r.status_code == 422
    r = client.patch(url, json={"expected_revision": 1, "title": "x" * 160}, headers=alice)
    assert r.status_code == 200


def test_stale_revision_is_rejected_with_409(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc = _create(client, alice)
    url = f"/api/documents/{doc['id']}"
    assert client.patch(url, json={"expected_revision": 1, "title": "A"}, headers=alice).is_success
    r = client.patch(url, json={"expected_revision": 1, "title": "B"}, headers=alice)
    assert r.status_code == 409
    assert r.json()["detail"]["current_revision"] == 2
    assert client.get(url, headers=alice).json()["title"] == "A"


@pytest.mark.parametrize(
    "content",
    [
        {"type": "doc", "content": [{"type": "html", "text": "<script>alert(1)</script>"}]},
        {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 4}}]},
        {"type": "doc", "content": [{"type": "paragraph", "attrs": {"onclick": "x"}}]},
        {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text"}]}]},
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "x", "marks": [{"type": "link"}]}],
                }
            ],
        },
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "x",
                            "marks": [{"type": "textStyle", "attrs": {"fontSize": "99px"}}],
                        }
                    ],
                }
            ],
        },
        {"type": "paragraph"},
        "not an object",
    ],
)
def test_malformed_content_rejected(client: TestClient, login, content: Any) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    r = client.post("/api/documents", json={"title": "x", "content_json": content}, headers=alice)
    assert r.status_code == 422


def test_other_users_get_privacy_preserving_404(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    doc = _create(client, login("alice"))
    url = f"/api/documents/{doc['id']}"
    charlie = login("charlie")
    assert client.get(url, headers=charlie).status_code == 404
    patch = {"expected_revision": 1, "title": "pwned"}
    assert client.patch(url, json=patch, headers=charlie).status_code == 404
    assert client.delete(url, headers=charlie).status_code == 404
    missing = "/api/documents/00000000-0000-0000-0000-000000000000"
    assert client.get(missing, headers=charlie).status_code == 404


def test_viewer_can_read_not_write(client: TestClient, login, db: Session) -> None:  # type: ignore[no-untyped-def]
    doc = _create(client, login("alice"), title="Shared")
    users = {u.login_key: u for u in db.query(User)}
    db.add(
        DocumentGrant(
            document_id=doc["id"], grantee_id=users["bob"].id, granted_by=users["alice"].id
        )
    )
    db.commit()
    bob = login("bob")
    url = f"/api/documents/{doc['id']}"
    r = client.get(url, headers=bob)
    assert r.status_code == 200
    assert r.json()["permission"] == "viewer"
    listed = client.get("/api/documents", headers=bob).json()
    assert [(d["title"], d["permission"]) for d in listed] == [("Shared", "viewer")]
    assert (
        client.patch(url, json={"expected_revision": 1, "title": "x"}, headers=bob).status_code
        == 403
    )
    assert client.delete(url, headers=bob).status_code == 403


def test_owner_can_delete(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc = _create(client, alice)
    assert client.delete(f"/api/documents/{doc['id']}", headers=alice).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=alice).status_code == 404


def test_requires_session(client: TestClient) -> None:
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/documents", json={}).status_code == 401
