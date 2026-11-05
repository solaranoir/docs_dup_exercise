"""Title and body search, permission-filtered (DOC-017)."""

from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.content import plain_text
from app.search import query_terms, snippet, tsquery_text
from tests.conftest import BACKEND

Headers = dict[str, str]


@pytest.fixture
def alice(login: Callable[[str], Headers]) -> Headers:
    return login("alice")


@pytest.fixture
def bob(login: Callable[[str], Headers]) -> Headers:
    return login("bob")


@pytest.fixture
def charlie(login: Callable[[str], Headers]) -> Headers:
    return login("charlie")


def _content(*paragraphs: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs
        ],
    }


def _doc(client: TestClient, headers: Headers, title: str, *body: str) -> dict[str, Any]:
    r = client.post(
        "/api/documents",
        json={"title": title, "content_json": _content(*body)},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _search(client: TestClient, headers: Headers, q: str) -> list[dict[str, Any]]:
    r = client.get("/api/documents/search", params={"q": q}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _titles(client: TestClient, headers: Headers, q: str) -> list[str]:
    return [d["title"] for d in _search(client, headers, q)]


def _share(client: TestClient, doc_id: str, owner: Headers) -> None:
    r = client.post(
        f"/api/documents/{doc_id}/grants", json={"email": "bob@demo.test"}, headers=owner
    )
    assert r.is_success, r.text


# --- helpers ------------------------------------------------------------------------------


def test_plain_text_joins_blocks_and_skips_markup() -> None:
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "POTA K-4392"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Worked ", "marks": [{"type": "bold"}]},
                    {"type": "text", "text": "AO-91"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "on 14.074"},
                ],
            },
            {"type": "paragraph"},
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "dipole"}]}
                        ],
                    }
                ],
            },
        ],
    }
    assert plain_text(doc) == "POTA K-4392\nWorked AO-91\non 14.074\ndipole"
    assert plain_text({"type": "doc", "content": [{"type": "paragraph"}]}) == ""
    assert plain_text(None) == ""
    assert plain_text({"content": "nonsense"}) == ""


def test_query_building_quotes_user_input() -> None:
    assert query_terms("  K-43   ao-9 -- ") == ["K-43", "ao-9"]
    assert tsquery_text(["K-43", "ant"]) == "('K' <-> '43':*) & ('ant':*)"
    assert tsquery_text(["it's"]) == "('it''s':*)"
    assert tsquery_text(["a\\b"]) == "('a\\\\b':*)"


def test_snippet_centres_on_the_first_match() -> None:
    body = "Setup notes. " * 10 + "Worked AO-91 at dusk with the handheld Yagi. " + "x " * 100
    s = snippet(body, ["ao-91"])
    assert s is not None
    assert s.startswith("…") and s.endswith("…")
    assert "AO-91" in s and len(s) <= 170
    assert snippet("Short body", ["nomatch"]) == "Short body"
    assert snippet("", ["x"]) is None
    assert snippet("line one\nline two", ["two"]) == "line one line two"


# --- matching -------------------------------------------------------------------------------


def test_matches_title_and_body_case_insensitively(client: TestClient, alice: Headers) -> None:
    _doc(client, alice, "Satellite pass log", "Heard the beacon clearly.")
    _doc(client, alice, "Antenna experiment", "Inverted-V dipole for 40m, fed with LADDER line")
    _doc(client, alice, "Shopping", "coax, connectors")

    assert _titles(client, alice, "satellite") == ["Satellite pass log"]
    assert _titles(client, alice, "SATELLITE") == ["Satellite pass log"]
    assert _titles(client, alice, "ladder") == ["Antenna experiment"]
    assert _titles(client, alice, "Ladder LINE") == ["Antenna experiment"]
    # Every word must match somewhere (title or body), not necessarily together.
    assert _titles(client, alice, "antenna dipole") == ["Antenna experiment"]
    assert _titles(client, alice, "antenna beacon") == []
    assert _titles(client, alice, "nothing-like-this") == []


def test_prefix_and_callsign_fragments(client: TestClient, alice: Headers) -> None:
    _doc(client, alice, "Park K-4392 activation", "Worked AO-91 and KD0ABC on 14.074 MHz")
    for q in ("park", "K-43", "k-4392", "4392", "AO-9", "ao", "91", "kd0", "14.07", "074", "MHz"):
        assert _titles(client, alice, q) == ["Park K-4392 activation"], q
    for q in ("K-5", "AO-7", "0abc"):  # word-prefix search, not arbitrary substrings
        assert _titles(client, alice, q) == [], q


def test_title_matches_rank_first_and_snippet_comes_from_body(
    client: TestClient, alice: Headers
) -> None:
    _doc(client, alice, "Notes", "We tried the yagi again today.")
    _doc(client, alice, "Yagi build", "Elements cut to length.")
    results = _search(client, alice, "yagi")
    assert [r["title"] for r in results] == ["Yagi build", "Notes"]
    assert results[1]["snippet"] == "We tried the yagi again today."
    assert results[0]["snippet"] == "Elements cut to length."
    assert results[0]["permission"] == "owner"


@pytest.mark.parametrize(
    "q", ["'", "\\", "%", "_", "&", "|", "!", "()", ":*", "<->", "a'b", "x:*|y", "'; drop"]
)
def test_hostile_queries_are_literal_text(client: TestClient, alice: Headers, q: str) -> None:
    _doc(client, alice, "Plain", "nothing special here")
    assert _search(client, alice, q) == []


def test_empty_and_overlong_queries(client: TestClient, alice: Headers) -> None:
    _doc(client, alice, "Anything", "text")
    assert _search(client, alice, "") == []
    assert _search(client, alice, "   ") == []
    assert client.get("/api/documents/search", headers=alice).json() == []
    r = client.get("/api/documents/search", params={"q": "x" * 201}, headers=alice)
    assert r.status_code == 422
    client.cookies.clear()
    assert client.get("/api/documents/search", params={"q": "x"}).status_code == 401


def test_results_are_capped(client: TestClient, alice: Headers) -> None:
    for i in range(52):
        _doc(client, alice, f"Log {i}", "beacon")
    assert len(_search(client, alice, "beacon")) == 50


# --- permissions ------------------------------------------------------------------------------


def test_owned_and_shared_results_never_strangers(
    client: TestClient, alice: Headers, bob: Headers, charlie: Headers
) -> None:
    shared = _doc(client, alice, "Shared repeater notes", "secret tone 141.3")
    _doc(client, alice, "Private repeater notes", "secret tone 100.0")
    _share(client, shared["id"], alice)
    _doc(client, bob, "Bob repeater list", "his own")

    assert sorted(_titles(client, alice, "repeater")) == [
        "Private repeater notes",
        "Shared repeater notes",
    ]
    bob_results = {r["title"]: r for r in _search(client, bob, "repeater")}
    assert sorted(bob_results) == ["Bob repeater list", "Shared repeater notes"]
    assert bob_results["Shared repeater notes"]["permission"] == "viewer"
    assert bob_results["Shared repeater notes"]["owner"]["display_name"].startswith("Alice")
    # Body-only words of the private document don't surface it (or a snippet of it) for Bob.
    assert _search(client, bob, "100.0") == []
    assert _titles(client, bob, "secret") == ["Shared repeater notes"]

    for q in ("repeater", "secret", "notes", "tone", "141", "Private", "Bob"):
        assert _search(client, charlie, q) == [], q


def test_revoked_share_disappears_from_results(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice, "Contest plan", "multipliers")
    _share(client, doc["id"], alice)
    assert _titles(client, bob, "multipliers") == ["Contest plan"]
    bob_id = client.get("/api/me", headers=bob).json()["id"]
    r = client.delete(f"/api/documents/{doc['id']}/grants/{bob_id}", headers=alice)
    assert r.status_code == 204
    assert _search(client, bob, "multipliers") == []


def test_archived_documents_are_excluded(client: TestClient, alice: Headers, bob: Headers) -> None:
    doc = _doc(client, alice, "Old field day", "generator")
    _share(client, doc["id"], alice)
    assert client.post(f"/api/documents/{doc['id']}/archive", headers=alice).is_success
    assert _search(client, alice, "generator") == []
    assert _search(client, bob, "field") == []
    assert client.post(f"/api/documents/{doc['id']}/restore", headers=alice).is_success
    assert _titles(client, alice, "generator") == ["Old field day"]


# --- search text stays in sync ------------------------------------------------------------------


def test_patch_updates_search(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice, "Draft", "first words")
    r = client.patch(
        f"/api/documents/{doc['id']}",
        json={"expected_revision": 1, "content_json": _content("replacement text")},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    assert _search(client, alice, "first") == []
    assert _titles(client, alice, "replacement") == ["Draft"]
    # A title-only edit renames without losing the body.
    r = client.patch(
        f"/api/documents/{doc['id']}",
        json={"expected_revision": 2, "title": "Final"},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    assert _titles(client, alice, "replacement") == ["Final"]
    assert _titles(client, alice, "final") == ["Final"]
    assert _search(client, alice, "draft") == []


def test_stale_patch_leaves_search_unchanged(client: TestClient, alice: Headers) -> None:
    doc = _doc(client, alice, "Draft", "kept")
    r = client.patch(
        f"/api/documents/{doc['id']}",
        json={"expected_revision": 9, "content_json": _content("lost")},
        headers=alice,
    )
    assert r.status_code == 409
    assert _titles(client, alice, "kept") == ["Draft"]
    assert _search(client, alice, "lost") == []


@pytest.mark.parametrize("mode", ["append", "replace"])
def test_import_updates_search(client: TestClient, alice: Headers, mode: str) -> None:
    doc = _doc(client, alice, "Imported", "original paragraph")
    r = client.post(
        f"/api/documents/{doc['id']}/imports",
        files={"file": ("log.md", b"# Contacts\n\nWorked VK2ABC", "text/markdown")},
        data={"mode": mode, "expected_revision": "1"},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    assert _titles(client, alice, "vk2abc") == ["Imported"]
    assert _titles(client, alice, "original") == (["Imported"] if mode == "append" else [])


def test_duplicate_is_searchable_by_its_owner(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    doc = _doc(client, alice, "Source", "unique-marker body")
    _share(client, doc["id"], alice)
    r = client.post(f"/api/documents/{doc['id']}/duplicate", headers=bob)
    assert r.status_code == 201, r.text
    bob_hits = {(d["title"], d["permission"]) for d in _search(client, bob, "unique-marker")}
    assert bob_hits == {("Source", "viewer"), ("Copy of Source", "owner")}
    assert _titles(client, alice, "unique-marker") == ["Source"]


# --- migration ------------------------------------------------------------------------------


def test_migration_backfills_existing_documents(engine: Engine, database_url: str) -> None:
    """Rows written before 0004 are searchable afterwards, with revision/updated_at untouched."""
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    engine.dispose()
    command.downgrade(cfg, "0003")
    doc_id = "22222222-2222-2222-2222-222222222222"
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (display_name, email) VALUES ('Pre', 'pre@x.io')"))
            uid = conn.execute(text("SELECT id FROM users WHERE email = 'pre@x.io'")).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO documents (id, owner_id, title, content_json, revision, "
                    "created_at, updated_at) VALUES (:id, :uid, 'Old log', :c, 4, "
                    "'2026-01-02T03:04:05Z', '2026-01-02T03:04:05Z')"
                ),
                {
                    "id": doc_id,
                    "uid": uid,
                    "c": '{"type": "doc", "content": [{"type": "paragraph", "content": '
                    '[{"type": "text", "text": "Heard ISS on 145.800"}]}]}',
                },
            )
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT title, revision, updated_at, search_text FROM documents WHERE id = :i"
                ),
                {"i": doc_id},
            ).one()
            assert (row.title, row.revision, row.search_text) == (
                "Old log",
                4,
                "Heard ISS on 145.800",
            )
            assert row.updated_at.isoformat().startswith("2026-01-02T03:04:05")
            if engine.dialect.name == "postgresql":
                hit = conn.execute(
                    text(
                        "SELECT count(*) FROM documents WHERE id = :i AND search_vector @@ "
                        "to_tsquery('simple', '''iss'':* & ''145'' <-> ''800'':*')"
                    ),
                    {"i": doc_id},
                ).scalar_one()
                assert hit == 1
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc_id})
            conn.execute(text("DELETE FROM users WHERE email = 'pre@x.io'"))
