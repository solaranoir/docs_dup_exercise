import io
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.imports import convert_docx, convert_md, convert_txt
from tests.conftest import FIXTURES


def _types(content: dict[str, Any]) -> list[str]:
    return [n["type"] for n in content["content"]]


def _upload(name: str, data: bytes | None = None) -> dict[str, Any]:
    payload = data if data is not None else (FIXTURES / name).read_bytes()
    return {"file": (name, payload, "application/octet-stream")}


# --- converters ---------------------------------------------------------------------


def test_txt_paragraphs_and_line_breaks() -> None:
    result = convert_txt((FIXTURES / "sample.txt").read_bytes())
    assert _types(result.content) == ["paragraph", "paragraph"]
    assert result.content["content"][0]["content"][1] == {"type": "hardBreak"}
    assert result.warnings == []


def test_txt_handles_crlf_and_bom() -> None:
    result = convert_txt("﻿a\r\nb\r\n\r\nc".encode())
    assert _types(result.content) == ["paragraph", "paragraph"]
    assert result.content["content"][0]["content"][0]["text"] == "a"


def test_md_supported_subset_and_warnings() -> None:
    result = convert_md((FIXTURES / "sample.md").read_bytes())
    types = _types(result.content)
    assert types[:4] == ["heading", "paragraph", "heading", "bulletList"]
    assert "orderedList" in types
    para = result.content["content"][1]["content"]
    assert {"type": "text", "text": "bold", "marks": [{"type": "bold"}]} in para
    assert {"type": "text", "text": "italic", "marks": [{"type": "italic"}]} in para
    nested = result.content["content"][3]["content"][1]["content"]
    assert [n["type"] for n in nested] == ["paragraph", "bulletList"]
    deep = [n for n in result.content["content"] if n.get("attrs", {}).get("level") == 3]
    assert deep, "h4 should clamp to h3"
    assert "Embedded HTML was removed." in result.warnings
    assert "Links were converted to plain text." in result.warnings
    assert "script" not in str(result.content)


def test_docx_headings_marks_lists_and_warnings() -> None:
    result = convert_docx((FIXTURES / "sample.docx").read_bytes())
    types = _types(result.content)
    assert types == [
        "heading",
        "paragraph",
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "heading",
    ]
    marks = {
        n["text"]: [m["type"] for m in n.get("marks", [])]
        for block in result.content["content"][1:3]
        for n in block["content"]
    }
    assert marks["strongly"] == ["bold"]
    assert marks["quarter"] == ["italic"]
    assert marks["Underlined note"] == ["underline"]
    assert len(result.content["content"][4]["content"]) == 2
    assert "Tables are not supported and were removed." in result.warnings


# --- API ----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sample.txt", "sample.md", "sample.docx"])
def test_preview_then_create(client: TestClient, login, name: str) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    r = client.post("/api/imports", files=_upload(name), headers=alice)
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["title"] == "sample"
    assert preview["source_type"] == name.split(".")[1]
    created = client.post(
        "/api/documents",
        json={"title": preview["title"], "content_json": preview["content_json"]},
        headers=alice,
    )
    assert created.status_code == 201
    # Preview alone must not create anything.
    assert len(client.get("/api/documents", headers=alice).json()) == 1


@pytest.mark.parametrize(
    ("name", "data", "status"),
    [
        ("evil.exe", b"MZ", 415),
        ("notes.pdf", b"%PDF-1.7", 415),
        ("fake.docx", b"plain text pretending", 415),
        ("binary.txt", b"\x00\x01\x02", 415),
        ("latin1.txt", "caf\xe9".encode("latin-1"), 415),
        ("empty.md", b"", 422),
    ],
)
def test_rejected_uploads(client: TestClient, login, name: str, data: bytes, status: int) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/imports", files=_upload(name, data), headers=login("alice"))
    assert r.status_code == status, r.text
    assert r.json()["detail"]


def test_zip_without_word_document_rejected(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    r = client.post("/api/imports", files=_upload("x.docx", buf.getvalue()), headers=login("alice"))
    assert r.status_code == 415


def test_oversize_upload_rejected(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    big = b"a" * (10 * 1024 * 1024 + 1)
    r = client.post("/api/imports", files=_upload("big.txt", big), headers=login("alice"))
    assert r.status_code == 413


def test_path_traversal_filename_is_neutralised(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/imports", files=_upload("../../etc/passwd.txt", b"hello"), headers=login("alice")
    )
    assert r.status_code == 200
    assert r.json()["source_name"] == "passwd.txt"


def test_append_and_replace_into_existing(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc = client.post(
        "/api/documents",
        json={
            "title": "Draft",
            "content_json": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "keep"}]}],
            },
        },
        headers=alice,
    ).json()
    url = f"/api/documents/{doc['id']}/imports"

    r = client.post(
        url,
        files=_upload("sample.txt"),
        data={"mode": "append", "expected_revision": "1"},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    appended = r.json()["document"]
    assert appended["revision"] == 2
    assert appended["content_json"]["content"][0]["content"][0]["text"] == "keep"
    assert len(appended["content_json"]["content"]) == 3

    stale = client.post(
        url,
        files=_upload("sample.md"),
        data={"mode": "replace", "expected_revision": "1"},
        headers=alice,
    )
    assert stale.status_code == 409

    r = client.post(
        url,
        files=_upload("sample.md"),
        data={"mode": "replace", "expected_revision": "2"},
        headers=alice,
    )
    replaced = r.json()["document"]
    assert replaced["revision"] == 3
    assert replaced["content_json"]["content"][0]["type"] == "heading"
    assert r.json()["warnings"]


def test_import_into_document_requires_edit_access(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    doc = client.post("/api/documents", json={}, headers=login("alice")).json()
    r = client.post(
        f"/api/documents/{doc['id']}/imports",
        files=_upload("sample.txt"),
        data={"mode": "replace", "expected_revision": "1"},
        headers=login("charlie"),
    )
    assert r.status_code == 404


def test_imports_require_session(client: TestClient) -> None:
    assert client.post("/api/imports", files=_upload("sample.txt")).status_code == 401
