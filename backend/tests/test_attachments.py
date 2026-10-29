from typing import Any

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws

from app.storage import MemoryStorage, S3Storage
from tests.conftest import FIXTURES


def _doc(client: TestClient, headers: dict[str, str]) -> str:
    return str(client.post("/api/documents", json={}, headers=headers).json()["id"])


def _attach(
    client: TestClient, headers: dict[str, str], doc_id: str, name: str, data: bytes
) -> Any:
    return client.post(
        f"/api/documents/{doc_id}/attachments",
        files={"file": (name, data, "text/plain")},
        headers=headers,
    )


def test_upload_list_download_delete(client: TestClient, login, storage: MemoryStorage) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc_id = _doc(client, alice)
    data = (FIXTURES / "sample.txt").read_bytes()
    r = _attach(client, alice, doc_id, "notes ünïcode.txt", data)
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["size_bytes"] == len(data)
    assert att["mime_type"] == "text/plain"

    listed = client.get(f"/api/documents/{doc_id}/attachments", headers=alice).json()
    assert [a["id"] for a in listed] == [att["id"]]

    dl = client.get(f"/api/documents/{doc_id}/attachments/{att['id']}", headers=alice)
    assert dl.status_code == 200
    assert dl.content == data
    assert dl.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''notes%20%C3%BCn%C3%AFcode.txt" in dl.headers["content-disposition"]
    assert dl.headers["x-content-type-options"] == "nosniff"

    (key,) = storage.objects
    assert key.startswith(f"documents/{doc_id}/attachments/")
    assert "notes" not in key  # user filename never reaches the object key

    assert (
        client.delete(f"/api/documents/{doc_id}/attachments/{att['id']}", headers=alice).status_code
        == 204
    )
    assert storage.objects == {}


def test_attachment_limits_and_types(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc_id = _doc(client, alice)
    assert _attach(client, alice, doc_id, "x.exe", b"MZ").status_code == 415
    assert _attach(client, alice, doc_id, "x.txt", b"a" * (10 * 1024 * 1024 + 1)).status_code == 413
    for i in range(10):
        assert _attach(client, alice, doc_id, f"{i}.txt", b"x").status_code == 201
    assert _attach(client, alice, doc_id, "11.txt", b"x").status_code == 409


def test_attachment_authorization(client: TestClient, login) -> None:  # type: ignore[no-untyped-def]
    alice, bob, charlie = login("alice"), login("bob"), login("charlie")
    doc_id = _doc(client, alice)
    att = _attach(client, alice, doc_id, "a.txt", b"secret").json()
    url = f"/api/documents/{doc_id}/attachments/{att['id']}"

    # Charlie: no access at all → indistinguishable from missing.
    assert client.get(url, headers=charlie).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/attachments", headers=charlie).status_code == 404
    assert _attach(client, charlie, doc_id, "b.txt", b"x").status_code == 404

    # Bob as viewer: can list and download, cannot add or remove.
    bob_id = client.get("/api/me", headers=bob).json()["id"]
    client.post(f"/api/documents/{doc_id}/grants", json={"user_id": bob_id}, headers=alice)
    assert client.get(url, headers=bob).content == b"secret"
    assert _attach(client, bob, doc_id, "b.txt", b"x").status_code == 403
    assert client.delete(url, headers=bob).status_code == 403

    # Attachment id under a different document is not reachable.
    other = _doc(client, alice)
    assert (
        client.get(f"/api/documents/{other}/attachments/{att['id']}", headers=alice).status_code
        == 404
    )


def test_deleting_document_removes_objects(
    client: TestClient, login, storage: MemoryStorage
) -> None:  # type: ignore[no-untyped-def]
    alice = login("alice")
    doc_id = _doc(client, alice)
    _attach(client, alice, doc_id, "a.txt", b"1")
    _attach(client, alice, doc_id, "b.txt", b"2")
    assert len(storage.objects) == 2
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 204
    assert storage.objects == {}


def test_ready_reports_storage(client: TestClient) -> None:
    assert client.get("/health/ready").json()["storage"] == "ok"


@mock_aws
def test_s3_storage_roundtrip_against_s3_api() -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="bucket")
    s3 = S3Storage("bucket", None, "k", "s", "us-east-1", auto_create=False)
    s3.check()
    s3.put("documents/x/attachments/y", b"bytes", "text/plain")
    assert s3.get("documents/x/attachments/y") == b"bytes"
    s3.delete("documents/x/attachments/y")


@mock_aws
def test_s3_storage_auto_creates_bucket_for_local_dev() -> None:
    s3 = S3Storage("fresh", None, "k", "s", "us-east-1", auto_create=True)
    s3.put("k", b"v", "text/plain")
    assert s3.get("k") == b"v"
