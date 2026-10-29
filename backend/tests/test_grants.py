"""Alice/Bob/Charlie sharing journey from the roadmap demo script (steps 5–8)."""

from fastapi.testclient import TestClient


def _ids(client: TestClient, login) -> dict[str, int]:  # type: ignore[no-untyped-def]
    return {
        k: client.get("/api/me", headers=login(k)).json()["id"] for k in ("alice", "bob", "charlie")
    }


def test_share_read_only_and_revoke(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob, charlie = login("alice"), login("bob"), login("charlie")
    ids = _ids(client, login)
    doc = client.post("/api/documents", json={"title": "Quarterly Notes"}, headers=alice).json()
    doc_url = f"/api/documents/{doc['id']}"
    grants_url = f"{doc_url}/grants"

    r = client.post(grants_url, json={"user_id": ids["bob"]}, headers=alice)
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"
    # Idempotent: granting again does not duplicate.
    assert client.post(grants_url, json={"user_id": ids["bob"]}, headers=alice).status_code == 200
    assert [g["user_id"] for g in client.get(grants_url, headers=alice).json()] == [ids["bob"]]

    shared = client.get("/api/documents", headers=bob).json()
    assert [(d["title"], d["permission"], d["owner"]["id"]) for d in shared] == [
        ("Quarterly Notes", "viewer", ids["alice"])
    ]
    assert client.get(doc_url, headers=bob).status_code == 200
    patch = {"expected_revision": 1, "title": "Bob was here"}
    assert client.patch(doc_url, json=patch, headers=bob).status_code == 403

    assert client.get(doc_url, headers=charlie).status_code == 404
    assert client.get("/api/documents", headers=charlie).json() == []

    assert client.delete(f"{grants_url}/{ids['bob']}", headers=alice).status_code == 204
    assert client.get("/api/documents", headers=bob).json() == []
    assert client.get(doc_url, headers=bob).status_code == 404
    assert client.delete(f"{grants_url}/{ids['bob']}", headers=alice).status_code == 404


def test_only_owner_manages_grants(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob, charlie = login("alice"), login("bob"), login("charlie")
    ids = _ids(client, login)
    doc = client.post("/api/documents", json={}, headers=alice).json()
    grants_url = f"/api/documents/{doc['id']}/grants"
    client.post(grants_url, json={"user_id": ids["bob"]}, headers=alice)

    # Viewer cannot re-share, list or revoke.
    assert client.post(grants_url, json={"user_id": ids["charlie"]}, headers=bob).status_code == 403
    assert client.get(grants_url, headers=bob).status_code == 403
    assert client.delete(f"{grants_url}/{ids['bob']}", headers=bob).status_code == 403
    # Non-grantee cannot even learn the document exists.
    assert (
        client.post(grants_url, json={"user_id": ids["charlie"]}, headers=charlie).status_code
        == 404
    )


def test_grant_validation(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    ids = _ids(client, login)
    doc = client.post("/api/documents", json={}, headers=alice).json()
    grants_url = f"/api/documents/{doc['id']}/grants"
    assert client.post(grants_url, json={"user_id": 99999}, headers=alice).status_code == 422
    assert client.post(grants_url, json={"user_id": ids["alice"]}, headers=alice).status_code == 422
    # Editor grants are deferred post-MVP (decision #7).
    editor = {"user_id": ids["bob"], "role": "editor"}
    assert client.post(grants_url, json=editor, headers=alice).status_code == 422


def test_deleting_document_removes_grants(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob = login("alice"), login("bob")
    ids = _ids(client, login)
    doc = client.post("/api/documents", json={}, headers=alice).json()
    client.post(f"/api/documents/{doc['id']}/grants", json={"user_id": ids["bob"]}, headers=alice)
    assert client.delete(f"/api/documents/{doc['id']}", headers=alice).status_code == 204
    assert client.get("/api/documents", headers=bob).json() == []
