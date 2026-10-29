import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.content import ContentError, validate_content
from app.db import get_db
from app.models import EMPTY_DOC, Document, DocumentGrant, User, utcnow
from app.policy import Permission, can_delete, can_edit, can_read, permission_for

router = APIRouter(prefix="/api/documents", tags=["documents"])
DB = Annotated[Session, Depends(get_db)]

TITLE_MAX = 160


def _clean_title(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= TITLE_MAX:
        raise ValueError(f"Title must be 1–{TITLE_MAX} characters")
    return value


def _clean_content(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        return validate_content(value)
    except ContentError as exc:
        raise ValueError(f"Invalid document content: {exc}") from None


class DocumentCreate(BaseModel):
    title: str = "Untitled document"
    content_json: dict[str, Any] | None = None

    _title = field_validator("title")(_clean_title)
    _content = field_validator("content_json")(_clean_content)


class DocumentPatch(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = None
    content_json: dict[str, Any] | None = None

    _content = field_validator("content_json")(_clean_content)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _clean_title(value)


class OwnerOut(BaseModel):
    id: int
    display_name: str


class DocumentSummary(BaseModel):
    id: uuid.UUID
    title: str
    revision: int
    owner: OwnerOut
    permission: Permission
    updated_at: datetime


class DocumentOut(DocumentSummary):
    content_json: dict[str, Any]
    created_at: datetime


def _summary(doc: Document, owner: User, permission: Permission) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        title=doc.title,
        revision=doc.revision,
        owner=OwnerOut(id=owner.id, display_name=owner.display_name),
        permission=permission,
        updated_at=doc.updated_at,
    )


def _out(db: Session, doc: Document, permission: Permission) -> DocumentOut:
    owner = db.get(User, doc.owner_id)
    assert owner is not None
    return DocumentOut(
        **_summary(doc, owner, permission).model_dump(),
        content_json=doc.content_json,
        created_at=doc.created_at,
    )


def _load(db: Session, user: User, doc_id: uuid.UUID) -> tuple[Document, Permission]:
    doc = db.get(Document, doc_id)
    permission = permission_for(db, user, doc) if doc else None
    # Privacy-preserving: documents the caller cannot read look exactly like missing ones.
    if doc is None or not can_read(permission):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    assert permission is not None
    return doc, permission


@router.get("")
def list_documents(user: CurrentUser, db: DB) -> list[DocumentSummary]:
    owned = db.execute(
        select(Document, User)
        .join(User, User.id == Document.owner_id)
        .where(Document.owner_id == user.id)
    ).all()
    shared = db.execute(
        select(Document, User, DocumentGrant.role)
        .join(DocumentGrant, DocumentGrant.document_id == Document.id)
        .join(User, User.id == Document.owner_id)
        .where(DocumentGrant.grantee_id == user.id)
    ).all()
    items = [_summary(d, o, "owner") for d, o in owned]
    items += [_summary(d, o, "editor" if r == "editor" else "viewer") for d, o, r in shared]
    return sorted(items, key=lambda s: s.updated_at, reverse=True)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(body: DocumentCreate, user: CurrentUser, db: DB) -> DocumentOut:
    doc = Document(owner_id=user.id, title=body.title, content_json=body.content_json or EMPTY_DOC)
    db.add(doc)
    db.commit()
    return _out(db, doc, "owner")


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> DocumentOut:
    doc, permission = _load(db, user, doc_id)
    return _out(db, doc, permission)


@router.patch("/{doc_id}")
def update_document(
    doc_id: uuid.UUID, body: DocumentPatch, user: CurrentUser, db: DB
) -> DocumentOut:
    doc, permission = _load(db, user, doc_id)
    if not can_edit(permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You have view-only access")
    values: dict[str, Any] = {"revision": Document.revision + 1, "updated_at": utcnow()}
    if body.title is not None:
        values["title"] = body.title
    if body.content_json is not None:
        values["content_json"] = body.content_json
    # Compare-and-swap on revision (ADR-003): a stale writer never overwrites newer content.
    result = db.execute(
        update(Document)
        .where(Document.id == doc_id, Document.revision == body.expected_revision)
        .values(**values)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        db.rollback()
        db.refresh(doc)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "This document was changed since you opened it. Copy your edits, "
                "reload to get the latest version, then reapply them.",
                "current_revision": doc.revision,
            },
        )
    db.commit()
    db.refresh(doc)
    return _out(db, doc, permission)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    doc, permission = _load(db, user, doc_id)
    if not can_delete(permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete a document")
    db.delete(doc)
    db.commit()
