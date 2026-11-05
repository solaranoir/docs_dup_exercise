"""Cross-user isolation matrix (DOC-003, DOC-006, DOC-008; audit A10).

Every document-scoped route × {owner, viewer, stranger, anonymous}. Strangers must not learn
that a document exists (404), viewers may read but never change anything (403 on writes),
and anonymous callers are always 401. A guard test fails if a new document-scoped route is
added without a row here.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ROLES = ("owner", "viewer", "stranger", "anonymous")
USERS = {"owner": "alice", "viewer": "bob", "stranger": "charlie"}


@dataclass(frozen=True)
class Case:
    method: str
    path: str  # FastAPI route template
    expected: tuple[int, int, int, int]  # owner, viewer, stranger, anonymous
    body: str = "none"  # none | json-title | json-share | upload | import


CASES = [
    Case("GET", "/api/documents/{doc_id}", (200, 200, 404, 401)),
    Case("PATCH", "/api/documents/{doc_id}", (200, 403, 404, 401), "json-title"),
    Case("DELETE", "/api/documents/{doc_id}", (204, 403, 404, 401)),
    Case("POST", "/api/documents/{doc_id}/imports", (200, 403, 404, 401), "import"),
    Case("GET", "/api/documents/{doc_id}/attachments", (200, 200, 404, 401)),
    Case("POST", "/api/documents/{doc_id}/attachments", (201, 403, 404, 401), "upload"),
    Case("GET", "/api/documents/{doc_id}/attachments/{attachment_id}", (200, 200, 404, 401)),
    Case("DELETE", "/api/documents/{doc_id}/attachments/{attachment_id}", (204, 403, 404, 401)),
    Case("GET", "/api/documents/{doc_id}/grants", (200, 403, 404, 401)),
    Case("POST", "/api/documents/{doc_id}/grants", (200, 403, 404, 401), "json-share"),
    Case("DELETE", "/api/documents/{doc_id}/grants/{user_id}", (204, 403, 404, 401)),
]


@dataclass
class World:
    doc_id: str
    attachment_id: str
    viewer_id: int
    headers: dict[str, dict[str, str]]


@pytest.fixture
def world(client: TestClient, login) -> World:  # type: ignore[no-untyped-def]
    headers = {role: login(user) for role, user in USERS.items()}
    headers["anonymous"] = {}
    client.cookies.clear()  # only explicit per-role cookies from here on
    owner = headers["owner"]
    doc = client.post("/api/documents", json={"title": "Field notes"}, headers=owner).json()
    share = {"email": "bob@demo.test"}
    assert client.post(f"/api/documents/{doc['id']}/grants", json=share, headers=owner).is_success
    upload = client.post(
        f"/api/documents/{doc['id']}/attachments",
        files={"file": ("log.txt", b"73 de KD0ABC", "text/plain")},
        headers=owner,
    )
    assert upload.status_code == 201, upload.text
    viewer_id = client.get("/api/me", headers=headers["viewer"]).json()["id"]
    return World(doc["id"], upload.json()["id"], viewer_id, headers)


def _request(client: TestClient, case: Case, world: World, role: str) -> Any:
    url = case.path.format(
        doc_id=world.doc_id, attachment_id=world.attachment_id, user_id=world.viewer_id
    )
    kwargs: dict[str, Any] = {"headers": world.headers[role]}
    if case.body == "json-title":
        kwargs["json"] = {"expected_revision": 1, "title": "Changed"}
    elif case.body == "json-share":
        kwargs["json"] = {"email": "bob@demo.test"}  # existing grant → 200 for the owner
    elif case.body == "upload":
        kwargs["files"] = {"file": ("more.txt", b"more", "text/plain")}
    elif case.body == "import":
        kwargs["files"] = {"file": ("a.md", b"# Hi", "text/markdown")}
        kwargs["data"] = {"mode": "append", "expected_revision": "1"}
    return client.request(case.method, url, **kwargs)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.method} {c.path}")
def test_route_access(client: TestClient, world: World, case: Case, role: str) -> None:
    expected = case.expected[ROLES.index(role)]
    response = _request(client, case, world, role)
    assert response.status_code == expected, response.text

    # Denied requests change nothing: the owner still sees the original state.
    if expected >= 400:
        owner = world.headers["owner"]
        doc = client.get(f"/api/documents/{world.doc_id}", headers=owner).json()
        assert (doc["title"], doc["revision"]) == ("Field notes", 1)
        attachments = client.get(f"/api/documents/{world.doc_id}/attachments", headers=owner)
        assert [a["id"] for a in attachments.json()] == [world.attachment_id]
        grants = client.get(f"/api/documents/{world.doc_id}/grants", headers=owner).json()
        assert [g["user_id"] for g in grants] == [world.viewer_id]


def test_stranger_responses_match_missing_document(client: TestClient, world: World) -> None:
    """A stranger cannot tell a private document from one that never existed."""
    stranger = world.headers["stranger"]
    missing = "00000000-0000-0000-0000-000000000000"
    for suffix in ("", "/attachments", f"/attachments/{world.attachment_id}", "/grants"):
        real = client.get(f"/api/documents/{world.doc_id}{suffix}", headers=stranger)
        fake = client.get(f"/api/documents/{missing}{suffix}", headers=stranger)
        assert (real.status_code, real.json()) == (fake.status_code, fake.json())


def test_listing_shows_only_own_and_shared(client: TestClient, world: World) -> None:
    def ids(role: str) -> list[str]:
        return [d["id"] for d in client.get("/api/documents", headers=world.headers[role]).json()]

    assert ids("owner") == [world.doc_id]
    assert ids("viewer") == [world.doc_id]
    assert ids("stranger") == []
    assert client.get("/api/documents", headers={}).status_code == 401


def test_attachment_ids_do_not_cross_documents(client: TestClient, world: World) -> None:
    """Owning document B doesn't unlock document A's attachment via B's URL."""
    stranger = world.headers["stranger"]
    own = client.post("/api/documents", json={"title": "Mine"}, headers=stranger).json()
    url = f"/api/documents/{own['id']}/attachments/{world.attachment_id}"
    assert client.get(url, headers=stranger).status_code == 404
    assert client.delete(url, headers=stranger).status_code == 404


def test_every_document_route_is_in_the_matrix() -> None:
    # The OpenAPI schema is the flattened route table (app.routes nests included routers).
    paths = create_app().openapi()["paths"]
    routes = {
        (method.upper(), path)
        for path, operations in paths.items()
        if "{doc_id}" in path
        for method in operations
    }
    covered = {(c.method, c.path) for c in CASES}
    assert routes - covered == set(), "add the new route(s) to CASES"
    assert covered - routes == set(), "CASES lists routes that no longer exist"
