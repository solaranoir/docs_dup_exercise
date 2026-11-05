"""Demo-data purge for the production cut-over."""

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Attachment, Document, DocumentGrant, User, UserIdentity, UserSession
from app.purge import PurgeRefused, plan_purge, purge_demo_data
from app.sessions import create_session
from app.storage import MemoryStorage, StorageError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import purge_demo_data as cli  # noqa: E402


@pytest.fixture
def scene(client: TestClient, db: Session, login, storage: MemoryStorage) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Demo users with shared, attached data, next to a real account that must survive."""
    alice = login("alice")
    demo_doc = client.post("/api/documents", json={"title": "Demo"}, headers=alice).json()
    client.post(
        f"/api/documents/{demo_doc['id']}/grants", json={"email": "bob@demo.test"}, headers=alice
    )
    client.post(
        f"/api/documents/{demo_doc['id']}/attachments",
        files={"file": ("demo.txt", b"demo", "text/plain")},
        headers=alice,
    )

    real = User(email="op@example.com", display_name="Real Operator")
    db.add(real)
    db.commit()
    db.add(UserIdentity(user_id=real.id, provider="github", provider_subject="9", email=real.email))
    real_token = create_session(db, real, get_settings())
    real_doc = Document(owner_id=real.id, title="POTA plan")
    db.add(real_doc)
    db.commit()
    real_key = f"documents/{real_doc.id}/attachments/{uuid.uuid4()}"
    storage.put(real_key, b"real", "text/plain")
    alice_id = db.scalar(select(User.id).where(User.login_key == "alice"))
    bob_id = db.scalar(select(User.id).where(User.login_key == "bob"))
    assert alice_id is not None and bob_id is not None
    stray_key = f"documents/{real_doc.id}/attachments/{uuid.uuid4()}"
    storage.put(stray_key, b"stray", "text/plain")
    db.add_all(
        [
            Attachment(
                document_id=real_doc.id,
                original_name="real.txt",
                mime_type="text/plain",
                size_bytes=4,
                object_key=real_key,
                uploaded_by=real.id,
            ),
            # Edge cases the FK constraints would otherwise trip on: a demo user's upload
            # inside a real document, and a grant from a real owner to a demo user.
            Attachment(
                document_id=real_doc.id,
                original_name="stray.txt",
                mime_type="text/plain",
                size_bytes=5,
                object_key=stray_key,
                uploaded_by=alice_id,
            ),
            DocumentGrant(document_id=real_doc.id, grantee_id=bob_id, granted_by=real.id),
        ]
    )
    db.commit()
    return {
        "real_id": real.id,
        "real_doc": real_doc.id,
        "real_key": real_key,
        "real_token": real_token,
        "stray_key": stray_key,
    }


def _count(db: Session, model: type) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_plan_lists_only_demo_data(db: Session, scene: dict[str, object]) -> None:
    plan = plan_purge(db)
    assert [key for _, key in plan.users] == ["alice", "bob", "charlie"]
    assert len(plan.document_ids) == 1
    assert len(plan.grant_ids) == 2  # alice→bob on demo doc, real owner→bob
    assert scene["real_key"] not in plan.attachment_keys
    assert scene["stray_key"] in plan.attachment_keys
    assert len(plan.attachment_keys) == 2


def test_purge_removes_demo_data_and_keeps_real_accounts(
    client: TestClient, db: Session, storage: MemoryStorage, scene: dict[str, object]
) -> None:
    result = purge_demo_data(db, storage)
    assert result.orphaned_keys == []

    assert db.scalars(select(User.email)).all() == ["op@example.com"]
    assert db.scalars(select(Document.title)).all() == ["POTA plan"]
    assert db.scalars(select(Attachment.object_key)).all() == [scene["real_key"]]
    assert _count(db, DocumentGrant) == 0
    assert db.scalars(select(UserSession.user_id)).all() == [scene["real_id"]]
    assert list(storage.objects) == [scene["real_key"]]  # demo + stray objects deleted

    # The real user is still signed in and their document still works end to end.
    headers = {"Cookie": f"sd_session={scene['real_token']}"}
    client.cookies.clear()
    assert client.get("/api/me", headers=headers).json()["email"] == "op@example.com"
    doc_url = f"/api/documents/{scene['real_doc']}"
    assert client.get(doc_url, headers=headers).status_code == 200
    attachments = client.get(f"{doc_url}/attachments", headers=headers).json()
    assert [a["original_name"] for a in attachments] == ["real.txt"]

    assert plan_purge(db).empty  # idempotent


def test_purge_reports_objects_it_could_not_delete(
    db: Session, storage: MemoryStorage, scene: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(key: str) -> None:
        raise StorageError("r2 down")

    monkeypatch.setattr(storage, "delete", broken)
    result = purge_demo_data(db, storage)
    assert sorted(result.orphaned_keys) == sorted(result.plan.attachment_keys)
    assert _count(db, User) == 1  # database cleanup still committed


def test_purge_refuses_without_storage_when_objects_exist(
    db: Session, scene: dict[str, object]
) -> None:
    with pytest.raises(PurgeRefused, match="storage"):
        purge_demo_data(db, None)
    assert _count(db, User) == 4  # nothing deleted


def test_purge_refuses_if_a_demo_user_has_an_oauth_identity(db: Session) -> None:
    alice = db.scalar(select(User).where(User.login_key == "alice"))
    assert alice is not None
    db.add(UserIdentity(user_id=alice.id, provider="google", provider_subject="x", email="a@b.co"))
    db.commit()
    with pytest.raises(PurgeRefused, match="OAuth identity"):
        plan_purge(db)


def test_cli_dry_run_then_delete(
    db: Session,
    storage: MemoryStorage,
    scene: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: db)
    monkeypatch.setattr(cli, "optional_storage", lambda: storage)
    monkeypatch.setattr(db, "close", lambda: None)

    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "demo users: alice#" in out and "Dry run: nothing deleted" in out
    assert _count(db, User) == 4

    assert cli.main(["--yes"]) == 0
    assert "Deleted." in capsys.readouterr().out
    assert _count(db, User) == 1

    assert cli.main(["--yes"]) == 0
    assert "Nothing to purge." in capsys.readouterr().out
