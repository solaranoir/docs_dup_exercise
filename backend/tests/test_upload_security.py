"""Upload security for attachments (Phase 6: upload security and sanitisation).

Attachments are stored privately and only ever served as downloads. These tests try what an
attacker would: disguised files, lying content types, hostile file names, malformed or
expanding .docx files, and binary or non-UTF-8 "text".
"""

import io
import zipfile
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

Headers = dict[str, str]


@pytest.fixture
def alice(login: Callable[[str], Headers]) -> Headers:
    return login("alice")


@pytest.fixture
def doc_id(client: TestClient, alice: Headers) -> str:
    r = client.post("/api/documents", json={"title": "Uploads"}, headers=alice)
    return r.json()["id"]  # type: ignore[no-any-return]


def _attach(
    client: TestClient, headers: Headers, doc_id: str, name: str, data: bytes, ctype: str
) -> Any:
    return client.post(
        f"/api/documents/{doc_id}/attachments", files={"file": (name, data, ctype)}, headers=headers
    )


def _docx(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_html_disguised_as_text_is_only_ever_a_plain_text_download(
    client: TestClient, alice: Headers, doc_id: str
) -> None:
    payload = b"<html><script>alert(document.cookie)</script></html>"
    r = _attach(client, alice, doc_id, "notes.txt", payload, "text/html")  # lying content type
    assert r.status_code == 201, r.text
    assert r.json()["mime_type"] == "text/plain"  # decided by the server, not the client
    dl = client.get(f"/api/documents/{doc_id}/attachments/{r.json()['id']}", headers=alice)
    assert dl.content == payload  # stored unchanged, never rendered
    assert dl.headers["content-type"].startswith("text/plain")
    assert dl.headers["content-disposition"].startswith("attachment;")
    assert dl.headers["x-content-type-options"] == "nosniff"
    assert dl.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "name",
    ["page.html", "image.svg", "photo.png", "run.exe", "notes.txt.html", "macro.docm", "noext"],
)
def test_types_outside_the_allowlist_are_refused(
    client: TestClient, alice: Headers, doc_id: str, name: str
) -> None:
    r = _attach(client, alice, doc_id, name, b"hello", "text/plain")
    assert r.status_code == 415
    assert client.get(f"/api/documents/{doc_id}/attachments", headers=alice).json() == []


def test_allowlisted_extensions_are_case_insensitive(
    client: TestClient, alice: Headers, doc_id: str
) -> None:
    assert _attach(client, alice, doc_id, "LOG.TXT", b"73", "text/plain").status_code == 201
    assert _attach(client, alice, doc_id, "a.html.md", b"# hi", "text/html").status_code == 201


@pytest.mark.parametrize(
    ("data", "status"),
    [
        (b"", 422),  # empty
        (b"abc\x00def", 415),  # binary
        (b"\xff\xfe\xfa invalid utf-8", 415),
    ],
)
def test_text_must_be_real_utf8_text(
    client: TestClient, alice: Headers, doc_id: str, data: bytes, status: int
) -> None:
    assert _attach(client, alice, doc_id, "log.txt", data, "text/plain").status_code == status


@pytest.mark.parametrize(
    "data",
    [
        b"<html>not a zip</html>",
        _docx({"hello.txt": b"zip, but not Word"}),
        b"PK\x03\x04 truncated",
    ],
    ids=["html", "other-zip", "corrupt"],
)
def test_fake_docx_is_refused(client: TestClient, alice: Headers, doc_id: str, data: bytes) -> None:
    ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert _attach(client, alice, doc_id, "report.docx", data, ctype).status_code == 415


def test_docx_that_expands_far_beyond_the_limit_is_refused(
    client: TestClient, alice: Headers, doc_id: str
) -> None:
    bomb = _docx(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document/>",
            "word/media/padding.bin": b"\x00" * (210 * 1024 * 1024),
        }
    )
    assert len(bomb) < 1024 * 1024  # small on the wire
    ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert _attach(client, alice, doc_id, "bomb.docx", bomb, ctype).status_code == 415


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\x\\secret.txt", "secret.txt"),
        # Clients percent-encode quotes and line breaks in multipart names (as browsers do), so
        # these arrive encoded; the stored name must still contain neither.
        ('evil"; filename="x.exe.txt', None),
        ("line\r\nX-Injected: 1.txt", None),
        ("<img src=x onerror=alert(1)>.txt", "_img src=x onerror=alert(1)_.txt"),
    ],
)
def test_hostile_file_names_are_neutralised(
    client: TestClient, alice: Headers, doc_id: str, raw: str, stored: str | None
) -> None:
    r = _attach(client, alice, doc_id, raw, b"x", "text/plain")
    assert r.status_code == 201, r.text
    name = r.json()["original_name"]
    if stored is not None:
        assert name == stored
    assert not set(name) & set('"\r\n/\\<>')
    dl = client.get(f"/api/documents/{doc_id}/attachments/{r.json()['id']}", headers=alice)
    disposition = dl.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert "x-injected" not in {k.lower() for k in dl.headers}
    assert disposition.count('filename="') == 1
