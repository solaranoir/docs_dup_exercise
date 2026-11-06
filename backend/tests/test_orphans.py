"""Orphaned attachment objects (audit A12): app/orphans.py and scripts/sweep_orphans.py."""

from datetime import UTC, datetime, timedelta

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import Session

from app.orphans import find_orphans, sweep
from app.storage import MemoryStorage, S3Storage

LATER = datetime.now(UTC) + timedelta(hours=2)


def _attach(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    doc = client.post("/api/documents", json={"title": "Log"}, headers=headers).json()
    att = client.post(
        f"/api/documents/{doc['id']}/attachments",
        files={"file": ("log.txt", b"73", "text/plain")},
        headers=headers,
    ).json()
    return doc["id"], att["id"]


def test_finds_only_objects_without_an_attachment(
    client: TestClient,
    db: Session,
    storage: MemoryStorage,
    login,  # type: ignore[no-untyped-def]
) -> None:
    alice = login("alice")
    doc_id, att_id = _attach(client, alice)
    kept = f"documents/{doc_id}/attachments/{att_id}"
    lost = "documents/00000000-0000-0000-0000-000000000000/attachments/lost"
    storage.put(lost, b"deleted bytes", "text/plain")
    storage.put("not-ours/elsewhere", b"x", "text/plain")  # outside documents/: ignored

    result = find_orphans(db, storage, now=LATER)
    assert result.orphans == [lost]
    assert result.scanned == 2

    sweep(storage, result)
    assert result.deleted == 1
    assert lost not in storage.objects and kept in storage.objects
    assert (
        client.get(f"/api/documents/{doc_id}/attachments/{att_id}", headers=alice).content == b"73"
    )


def test_recent_objects_are_never_orphans(db: Session, storage: MemoryStorage) -> None:
    """An upload stores its bytes before committing its row."""
    storage.put("documents/x/attachments/in-flight", b"x", "text/plain")
    assert find_orphans(db, storage).orphans == []
    assert find_orphans(db, storage, now=LATER).orphans == ["documents/x/attachments/in-flight"]


def test_permanently_deleted_document_leaves_no_orphans(
    client: TestClient,
    db: Session,
    storage: MemoryStorage,
    login,  # type: ignore[no-untyped-def]
) -> None:
    alice = login("alice")
    doc_id, _ = _attach(client, alice)
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 204
    assert client.delete(f"/api/trash/{doc_id}", headers=alice).status_code == 204
    assert find_orphans(db, storage, now=LATER).orphans == []


@mock_aws
def test_s3_list_pages_through_the_bucket() -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="bucket")
    s3 = S3Storage("bucket", None, "k", "s", "us-east-1", auto_create=False)
    keys = [f"documents/d/attachments/{i:04}" for i in range(1005)]  # > one 1000-key page
    for key in keys:
        s3.put(key, b"", "text/plain")
    s3.put("other/x", b"", "text/plain")
    listed = list(s3.list("documents/"))
    assert [k for k, _ in listed] == keys
    assert all(m.tzinfo is not None for _, m in listed)
