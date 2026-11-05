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

    r = client.post(grants_url, json={"email": "bob@demo.test"}, headers=alice)
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"
    # Idempotent: granting again does not duplicate.
    assert (
        client.post(grants_url, json={"email": "bob@demo.test"}, headers=alice).status_code == 200
    )
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
    client.post(grants_url, json={"email": "bob@demo.test"}, headers=alice)

    # Viewer cannot re-share, list or revoke.
    assert (
        client.post(grants_url, json={"email": "charlie@demo.test"}, headers=bob).status_code == 403
    )
    assert client.get(grants_url, headers=bob).status_code == 403
    assert client.delete(f"{grants_url}/{ids['bob']}", headers=bob).status_code == 403
    # Non-grantee cannot even learn the document exists.
    assert (
        client.post(grants_url, json={"email": "charlie@demo.test"}, headers=charlie).status_code
        == 404
    )


def test_grant_validation(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    ids = _ids(client, login)
    doc = client.post("/api/documents", json={}, headers=alice).json()
    grants_url = f"/api/documents/{doc['id']}/grants"

    def share(body: dict[str, object]):  # type: ignore[no-untyped-def]
        return client.post(grants_url, json=body, headers=alice)

    unknown = share({"email": "nobody@example.com"})
    assert unknown.status_code == 422
    assert "sign in once" in unknown.json()["detail"]
    assert share({"email": "not-an-email"}).status_code == 422
    assert share({"email": "alice@demo.test"}).status_code == 422  # the owner
    # Editor grants are deferred post-MVP (decision #7).
    assert share({"email": "bob@demo.test", "role": "editor"}).status_code == 422
    # The old id-based body is no longer accepted (no sharing by guessable ids).
    assert share({"user_id": ids["bob"]}).status_code == 422
    # Emails are matched case-insensitively and the grant shows who it went to.
    r = share({"email": "  Bob@Demo.TEST "})
    assert r.status_code == 201
    assert (r.json()["user_id"], r.json()["email"]) == (ids["bob"], "bob@demo.test")


def test_deleting_document_removes_grants(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob = login("alice"), login("bob")
    doc = client.post("/api/documents", json={}, headers=alice).json()
    client.post(
        f"/api/documents/{doc['id']}/grants", json={"email": "bob@demo.test"}, headers=alice
    )
    assert client.delete(f"/api/documents/{doc['id']}", headers=alice).status_code == 204
    assert client.get("/api/documents", headers=bob).json() == []
