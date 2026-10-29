import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Document, DocumentGrant, User


def _users(db: Session) -> dict[str, User]:
    return {u.login_key: u for u in db.query(User)}


def test_document_content_roundtrip(db: Session) -> None:
    alice = _users(db)["alice"]
    content = {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Hi"}]}
        ],
    }
    doc = Document(owner_id=alice.id, title="Quarterly Notes", content_json=content)
    db.add(doc)
    db.commit()
    db.expire_all()
    loaded = db.get(Document, doc.id)
    assert loaded is not None
    assert loaded.content_json == content
    assert loaded.revision == 1


def test_grant_is_unique_per_document_and_grantee(db: Session) -> None:
    u = _users(db)
    doc = Document(owner_id=u["alice"].id, title="Shared")
    db.add(doc)
    db.commit()
    db.add(DocumentGrant(document_id=doc.id, grantee_id=u["bob"].id, granted_by=u["alice"].id))
    db.commit()
    db.add(DocumentGrant(document_id=doc.id, grantee_id=u["bob"].id, granted_by=u["alice"].id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_grant_role_is_constrained(db: Session) -> None:
    u = _users(db)
    doc = Document(owner_id=u["alice"].id, title="Roles")
    db.add(doc)
    db.commit()
    db.add(
        DocumentGrant(
            document_id=doc.id, grantee_id=u["bob"].id, granted_by=u["alice"].id, role="admin"
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_empty_title_rejected_by_database(db: Session) -> None:
    db.add(Document(owner_id=_users(db)["alice"].id, title=""))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
