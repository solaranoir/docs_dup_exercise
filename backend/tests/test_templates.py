"""Built-in templates (DOC-023..027; ADR-011)."""

import hashlib
import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.content import plain_text, validate_content
from app.templates import BY_ID, TEMPLATES, Template

Headers = dict[str, str]

# Bump a template's ``version`` whenever its content changes, then update its fingerprint here.
# A content change without a version bump fails this test.
FINGERPRINTS: dict[str, tuple[int, str]] = {
    "pota-activation-plan": (1, "2fed5999667fddfc"),
    "satellite-observation-log": (1, "006d68acfa3ede3a"),
    "antenna-experiment": (1, "5a08fa6a3d923e84"),
    "research-notes": (1, "55980ba0100dc029"),
}


def fingerprint(template: Template) -> str:
    raw = json.dumps(template.content(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@pytest.fixture
def alice(login: Callable[[str], Headers]) -> Headers:
    return login("alice")


def test_the_four_roadmap_templates_ship() -> None:
    assert [t.name for t in TEMPLATES] == [
        "POTA Activation Plan",
        "Satellite Observation Log",
        "Antenna Experiment",
        "Research / Engineering Notes",
    ]
    assert len(BY_ID) == len(TEMPLATES), "template ids must be unique"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.id)
def test_template_is_valid_editor_content(template: Template) -> None:
    content = template.content()
    assert validate_content(content) == content
    assert template.version >= 1 and template.description and template.sections
    headings = [s.heading for s in template.sections]
    assert len(set(headings)) == len(headings)
    # Searchable: every heading and field label is in the document's plain text.
    text = plain_text(content)
    for section in template.sections:
        assert section.heading in text
        for label in section.fields:
            assert f"{label}:" in text


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.id)
def test_template_content_changes_bump_the_version(template: Template) -> None:
    expected = FINGERPRINTS.get(template.id)
    actual = (template.version, fingerprint(template))
    assert expected == actual, (
        f"{template.id} changed: bump its version and set FINGERPRINTS[{template.id!r}] = {actual}"
    )


def test_roadmap_fields_are_present() -> None:
    """The fields each template promises in the roadmap (section 5)."""
    expected = {
        "pota-activation-plan": [
            "Park reference",
            "Equipment",
            "Antenna",
            "Bands",
            "Schedule",
            "Weather",
            "Operating notes",
        ],
        "satellite-observation-log": [
            "Satellite",
            "AOS (UTC)",
            "Downlink",
            "Maximum elevation",
            "Equipment",
            "Signal quality",
        ],
        "antenna-experiment": [
            "Hypothesis",
            "Setup",
            "Measurements",
            "Conditions",
            "Results",
            "Next steps",
        ],
        "research-notes": [
            "Problem",
            "Assumptions",
            "Method",
            "Evidence",
            "Findings",
            "Follow-ups",
        ],
    }
    for template_id, words in expected.items():
        text = plain_text(BY_ID[template_id].content())
        for word in words:
            assert word in text, f"{template_id} lacks {word!r}"


def test_list_templates_requires_sign_in(client: TestClient, alice: Headers) -> None:
    r = client.get("/api/templates", headers=alice)
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body] == [t.id for t in TEMPLATES]
    first = body[0]
    assert set(first) == {"id", "version", "name", "description", "sections"}
    assert first["sections"][0] == {
        "heading": "Park",
        "fields": ["Park reference", "Park name", "Access and parking"],
    }
    client.cookies.clear()
    assert client.get("/api/templates").status_code == 401


def test_create_from_template_makes_an_ordinary_editable_document(
    client: TestClient, alice: Headers
) -> None:
    template = BY_ID["pota-activation-plan"]
    r = client.post(
        "/api/documents",
        json={"template": template.id, "title": "POTA Activation Plan, 2026-11-05"},
        headers=alice,
    )
    assert r.status_code == 201, r.text
    doc: dict[str, Any] = r.json()
    assert doc["title"] == "POTA Activation Plan, 2026-11-05"
    assert doc["content_json"] == template.content()
    assert doc["revision"] == 1 and doc["permission"] == "owner"
    assert "template" not in doc  # no special data model: nothing links back to the template

    # Fully editable like any other document.
    edited = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "K-4389"}]}],
    }
    r = client.patch(
        f"/api/documents/{doc['id']}",
        json={"expected_revision": 1, "content_json": edited},
        headers=alice,
    )
    assert r.status_code == 200 and r.json()["content_json"] == edited

    # Search finds template text in a fresh document.
    r = client.post("/api/documents", json={"template": "antenna-experiment"}, headers=alice)
    assert r.json()["title"] == "Antenna Experiment"  # defaults to the template name
    hits = client.get("/api/documents/search", params={"q": "hypothesis"}, headers=alice).json()
    assert [h["id"] for h in hits] == [r.json()["id"]]


@pytest.mark.parametrize(
    "body",
    [
        {"template": "nope"},
        {"template": "research-notes", "content_json": {"type": "doc", "content": []}},
        {"template": "research-notes", "title": "   "},
    ],
)
def test_create_rejects_bad_template_requests(
    client: TestClient, alice: Headers, body: dict[str, Any]
) -> None:
    assert client.post("/api/documents", json=body, headers=alice).status_code == 422


def test_blank_create_is_unchanged(client: TestClient, alice: Headers) -> None:
    r = client.post("/api/documents", json={}, headers=alice)
    assert r.status_code == 201
    assert r.json()["title"] == "Untitled document"
    assert r.json()["content_json"] == {"type": "doc", "content": [{"type": "paragraph"}]}
