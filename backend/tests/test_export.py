"""Markdown export and export packages (DOC-028, DOC-030, DOC-033; ADR-012)."""

import io
import zipfile
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.content import validate_content
from app.export import safe_file_name, slug, to_markdown, unique
from app.imports import convert_md
from app.storage import MemoryStorage, optional_storage
from app.templates import TEMPLATES, Template

Headers = dict[str, str]
Node = dict[str, Any]


def text(value: str, *marks: str) -> Node:
    node: Node = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": m} for m in marks]
    return node


def para(*inline: Node) -> Node:
    return {"type": "paragraph", "content": list(inline)}


def doc(*blocks: Node) -> Node:
    return {"type": "doc", "content": list(blocks)}


def normalize(node: Any) -> Any:
    """Structure that survives Markdown: merged texts, trimmed paragraph edges, no underline,
    no alignment or font size, no empty paragraphs outside list items."""
    if isinstance(node, list):
        return [n for n in (normalize(x) for x in node) if n is not None]
    kind = node["type"]
    if kind == "text":
        marks = sorted(m["type"] for m in node.get("marks", []) if m["type"] in ("bold", "italic"))
        return {"text": node["text"], "marks": marks}
    out: dict[str, Any] = {"type": kind}
    if kind == "heading":
        out["level"] = node["attrs"]["level"]
    if kind == "orderedList":
        out["start"] = (node.get("attrs") or {}).get("start", 1)
    children = normalize(node.get("content", []))
    if kind in ("paragraph", "heading"):
        # Whitespace at the edge of a marked run looks the same unmarked; Markdown moves it out.
        split: list[dict[str, Any]] = []
        for child in children:
            raw = child.get("text")
            if raw is None or not child["marks"] or not raw.strip():
                split.append(
                    {**child, "marks": []} if raw is not None and not raw.strip() else child
                )
                continue
            lead, trail = raw[: len(raw) - len(raw.lstrip())], raw[len(raw.rstrip()) :]
            if lead:
                split.append({"text": lead, "marks": []})
            split.append({"text": raw.strip(), "marks": child["marks"]})
            if trail:
                split.append({"text": trail, "marks": []})
        merged: list[dict[str, Any]] = []
        for child in split:
            if (
                "text" in child
                and merged
                and "text" in merged[-1]
                and merged[-1]["marks"] == child["marks"]
            ):
                merged[-1] = {**merged[-1], "text": merged[-1]["text"] + child["text"]}
            else:
                merged.append(child)
        while merged and "text" in merged[-1] and not merged[-1]["text"].rstrip():
            merged.pop()
        if merged and "text" in merged[-1]:
            merged[-1] = {**merged[-1], "text": merged[-1]["text"].rstrip()}
        children = merged
    out["content"] = children
    return out


def round_trip(title: str, content: Node) -> Node:
    converted = convert_md(to_markdown(title, content).encode()).content
    validate_content(converted)
    blocks = converted["content"]
    assert blocks[0] == {"type": "heading", "attrs": {"level": 1}, "content": [text(title)]}
    return {"type": "doc", "content": blocks[1:]}


def assert_round_trips(content: Node, title: str = "Field notes") -> None:
    expected = [
        b for b in normalize(content["content"]) if b.get("content") or b["type"] != "paragraph"
    ]
    assert normalize(round_trip(title, content)["content"]) == expected


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.id)
def test_every_template_round_trips_through_the_importer(template: Template) -> None:
    assert_round_trips(template.content(), title=f"{template.name}, 2026-11-05")


@pytest.mark.parametrize(
    "literal",
    [
        "# not a heading",
        "1. not a list",
        "2) nor this",
        "- or this",
        "+ or this",
        "> not a quote",
        "*not italic* and **not bold**",
        "a_b_c and __init__",
        "<script>alert(1)</script> &copy; & [link](http://x) `code` ~~x~~ | pipe",
        "back\\slash",
        "=",
    ],
)
def test_markdown_syntax_in_text_stays_literal(literal: str) -> None:
    assert_round_trips(doc(para(text(literal))))
    assert_round_trips(doc({"type": "heading", "attrs": {"level": 2}, "content": [text(literal)]}))


def test_marks_nest_and_whitespace_moves_outside_delimiters() -> None:
    content = doc(
        para(text("Park reference:", "bold"), text(" "), text("K-4389")),
        para(text("plain "), text("bold ", "bold"), text("both", "bold", "italic"), text(" end")),
        para(text("x "), text("ital", "italic"), text(", "), text("strong", "bold"), text(".")),
    )
    md = to_markdown("T", content)
    assert "**Park reference:** K-4389" in md
    assert "plain **bold** ***both*** end" in md  # a run never ends in a space
    assert_round_trips(content)


def test_underline_is_html_and_reimports_as_text() -> None:
    content = doc(para(text("under", "underline"), text(" line")))
    assert "<u>under</u> line" in to_markdown("T", content)
    converted = convert_md(to_markdown("T", content).encode())
    assert normalize(converted.content["content"][1]) == normalize(para(text("under line")))
    assert converted.warnings == ["Embedded HTML was removed."]


def test_lists_nest_keep_start_and_hard_breaks() -> None:
    content = doc(
        {
            "type": "orderedList",
            "attrs": {"start": 3, "type": None},
            "content": [
                {"type": "listItem", "content": [para(text("three"))]},
                {
                    "type": "listItem",
                    "content": [
                        para(text("four")),
                        {
                            "type": "bulletList",
                            "content": [
                                {"type": "listItem", "content": [para(text("nested", "bold"))]},
                                {"type": "listItem", "content": [{"type": "paragraph"}]},
                            ],
                        },
                    ],
                },
            ],
        },
        para(text("line one"), {"type": "hardBreak"}, text("line two")),
        {"type": "paragraph"},
        {
            "type": "heading",
            "attrs": {"level": 3, "textAlign": "center"},
            "content": [text("Centred")],
        },
    )
    md = to_markdown("T", content)
    assert "3. three\n4. four\n   - **nested**\n   -" in md
    assert "line one\\\nline two" in md
    converted = round_trip("T", content)
    assert converted["content"][1]["content"][1] == {"type": "hardBreak"}
    assert normalize(converted["content"][0]) == normalize(content["content"][0])


def test_file_names() -> None:
    assert slug("POTA K-4389: Activation, 2026-11-05") == "pota-k-4389-activation-2026-11-05"
    assert slug("Écoute du satellite") == "ecoute-du-satellite"
    assert slug("???") == "document"
    assert len(slug("x" * 200)) == 60
    assert safe_file_name("../../etc/passwd") == "etcpasswd"
    assert safe_file_name("..hidden") == "hidden"
    assert safe_file_name("a/b\\c:d.txt") == "abcd.txt"
    assert safe_file_name("\x00") == "attachment"
    taken: set[str] = set()
    assert [unique(n, taken) for n in ["log.txt", "LOG.txt", "log.txt", "notes"]] == [
        "log.txt",
        "LOG (2).txt",
        "log (3).txt",
        "notes",
    ]


# --- API -----------------------------------------------------------------------------------


@pytest.fixture
def alice(login: Callable[[str], Headers]) -> Headers:
    return login("alice")


@pytest.fixture
def bob(login: Callable[[str], Headers]) -> Headers:
    return login("bob")


def _create(client: TestClient, headers: Headers, title: str, **body: Any) -> dict[str, Any]:
    r = client.post("/api/documents", json={"title": title, **body}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _attach(client: TestClient, headers: Headers, doc_id: str, name: str, data: bytes) -> None:
    r = client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": (name, data, "text/plain")},
        headers=headers,
    )
    assert r.status_code == 201, r.text


def _share(client: TestClient, doc_id: str, owner: Headers) -> None:
    r = client.post(
        f"/api/documents/{doc_id}/grants", json={"email": "bob@demo.test"}, headers=owner
    )
    assert r.is_success, r.text


def test_export_without_attachments_is_markdown(client: TestClient, alice: Headers) -> None:
    d = _create(client, alice, "POTA plan, 2026-11-05", template="pota-activation-plan")
    r = client.get(f"/api/documents/{d['id']}/export", headers=alice)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/markdown; charset=utf-8"
    assert 'filename="pota-plan-2026-11-05.md"' in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "private, no-store"
    assert r.text.startswith("# POTA plan, 2026-11-05\n\n## Park\n\n**Park reference:**")


def test_export_with_attachments_is_a_zip(client: TestClient, alice: Headers) -> None:
    d = _create(client, alice, "Antenna test")
    _attach(client, alice, d["id"], "swr.txt", b"1.2:1")
    _attach(client, alice, d["id"], "swr.txt", b"1.5:1")
    _attach(client, alice, d["id"], "../evil.txt", b"x")
    r = client.get(f"/api/documents/{d['id']}/export", headers=alice)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="antenna-test.zip"' in r.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(archive.namelist()) == [
        "antenna-test.md",
        "attachments/evil.txt",
        "attachments/swr (2).txt",
        "attachments/swr.txt",
    ]
    assert archive.read("attachments/swr.txt") == b"1.2:1"
    assert archive.read("attachments/swr (2).txt") == b"1.5:1"
    md = archive.read("antenna-test.md").decode()
    assert "## Attachments\n\n- [swr.txt](<attachments/swr.txt>)" in md


def test_export_permissions(client: TestClient, alice: Headers, bob: Headers) -> None:
    d = _create(client, alice, "Shared plan")
    url = f"/api/documents/{d['id']}/export"
    assert client.get(url, headers=bob).status_code == 404  # not shared: looks missing
    _share(client, d["id"], alice)
    assert client.get(url, headers=bob).status_code == 200  # viewers can export what they read
    assert client.post(f"/api/documents/{d['id']}/archive", headers=alice).status_code == 200
    assert client.get(url, headers=alice).status_code == 200  # archived documents export too
    client.cookies.clear()
    assert client.get(url).status_code == 401


def test_export_needs_storage_only_for_attachments(client: TestClient, alice: Headers) -> None:
    plain = _create(client, alice, "Plain")
    attached = _create(client, alice, "Attached")
    _attach(client, alice, attached["id"], "log.txt", b"x")
    client.app.dependency_overrides[optional_storage] = lambda: None  # type: ignore[attr-defined]
    assert client.get(f"/api/documents/{plain['id']}/export", headers=alice).status_code == 200
    r = client.get(f"/api/documents/{attached['id']}/export", headers=alice)
    assert r.status_code == 503 and "try again" in r.json()["detail"]
    # Export all still delivers everything else and says what is missing.
    r = client.get("/api/export", headers=alice)
    assert r.status_code == 200 and r.headers["x-export-missing-attachments"] == "1"
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    index = next(archive.read(n).decode() for n in archive.namelist() if n.endswith("index.md"))
    assert "## Attachments that could not be included\n" in index
    assert "- Attached: log.txt" in index
    md = next(archive.read(n).decode() for n in archive.namelist() if n.endswith("attached.md"))
    assert "## Attachments" not in md


def test_export_all_skips_a_lost_attachment(
    client: TestClient, alice: Headers, storage: MemoryStorage
) -> None:
    d = _create(client, alice, "Pass log")
    _attach(client, alice, d["id"], "kept.txt", b"ok")
    _attach(client, alice, d["id"], "lost.txt", b"gone")
    lost_key = next(k for k, v in storage.objects.items() if v[0] == b"gone")
    storage.delete(lost_key)
    assert client.get(f"/api/documents/{d['id']}/export", headers=alice).status_code == 503
    r = client.get("/api/export", headers=alice)
    assert r.headers["x-export-missing-attachments"] == "1"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert any(n.endswith("pass-log/attachments/kept.txt") for n in names)
    assert not any(n.endswith("lost.txt") for n in names)


def test_export_all_has_owned_documents_only(
    client: TestClient, alice: Headers, bob: Headers
) -> None:
    first = _create(client, alice, "Field notes")
    _create(client, alice, "Field notes")  # same title: separate folders
    archived = _create(client, alice, "Old | plan")
    _attach(client, alice, first["id"], "photo.txt", b"img")
    client.post(f"/api/documents/{archived['id']}/archive", headers=alice)
    folder = client.post("/api/folders", json={"name": "2026 POTA"}, headers=alice).json()
    client.put(
        f"/api/documents/{first['id']}/folder", json={"folder_id": folder["id"]}, headers=alice
    )
    client.put(f"/api/documents/{first['id']}/tags", json={"tags": ["pota", "cw"]}, headers=alice)
    bobs = _create(client, bob, "Bob's secret")
    client.post(
        f"/api/documents/{bobs['id']}/grants", json={"email": "alice@demo.test"}, headers=bob
    )

    r = client.get("/api/export", headers=alice)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    names = archive.namelist()
    root = names[0].split("/")[0]
    assert root.startswith("solara-docs-export-")
    assert sorted(n.removeprefix(root + "/") for n in names) == [
        "field-notes (2)/field-notes (2).md",
        "field-notes/attachments/photo.txt",
        "field-notes/field-notes.md",
        "index.md",
        "old-plan/old-plan.md",
    ]
    index = archive.read(f"{root}/index.md").decode()
    assert "3 documents" in index
    assert "| [Field notes](<field-notes/field-notes.md>) | 2026 POTA | cw, pota |" in index
    assert "[Old \\| plan](<old-plan/old-plan.md>)" in index
    assert "secret" not in index and not any("secret" in n for n in names)

    # Someone with nothing still gets a valid archive.
    empty = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=bob).content))
    assert any(n.endswith("index.md") for n in empty.namelist())
    client.cookies.clear()
    assert client.get("/api/export").status_code == 401


def test_exports_are_rate_limited(client: TestClient, alice: Headers) -> None:
    d = _create(client, alice, "Plan")
    codes = [
        client.get(f"/api/documents/{d['id']}/export", headers=alice).status_code for _ in range(11)
    ]
    assert codes[:10] == [200] * 10 and codes[10] == 429
