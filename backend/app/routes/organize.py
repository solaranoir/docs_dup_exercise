"""Personal folders and tags (DOC-016, DOC-018; ADR-010).

Everything here is the caller's own data. Another user's folder id is answered exactly like a
missing one (404), and filing/tagging needs only read access to the document.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.models import Document, DocumentFolder, DocumentGrant, DocumentTag, Folder, User
from app.organization import (
    FOLDERS_PER_USER,
    STARTER_TAGS,
    normalize_folder_name,
    normalize_tags,
    set_folder,
    set_tags,
)
from app.routes.documents import DB, load_document

router = APIRouter(tags=["organize"])

FolderName = Annotated[str, Field(max_length=200)]


class FolderIn(BaseModel):
    name: FolderName

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return normalize_folder_name(value)


class FolderOut(BaseModel):
    id: int
    name: str
    document_count: int


class FolderAssignment(BaseModel):
    folder_id: int | None


class TagsIn(BaseModel):
    tags: list[Annotated[str, Field(max_length=100)]] = Field(max_length=100)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)


class TagsOut(BaseModel):
    tags: list[str]


class TagCount(BaseModel):
    tag: str
    count: int


class TagSummary(BaseModel):
    tags: list[TagCount]
    suggestions: list[str]


def _readable(user: User):  # type: ignore[no-untyped-def]
    """SQL condition: the caller can still read the document (owner or grantee)."""
    granted = exists().where(
        DocumentGrant.document_id == Document.id, DocumentGrant.grantee_id == user.id
    )
    return or_(Document.owner_id == user.id, granted)


def _own_folder(db: Session, user: User, folder_id: int) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None or folder.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")
    return folder


def _folder_out(db: Session, user: User, folder: Folder) -> FolderOut:
    count = db.scalar(
        select(func.count())
        .select_from(DocumentFolder)
        .join(Document, Document.id == DocumentFolder.document_id)
        .where(
            DocumentFolder.folder_id == folder.id,
            Document.archived_at.is_(None),
            _readable(user),
        )
    )
    return FolderOut(id=folder.id, name=folder.name, document_count=count or 0)


def _commit_name(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already have a folder with that name"
        ) from None


@router.get("/api/folders")
def list_folders(user: CurrentUser, db: DB) -> list[FolderOut]:
    folders = db.scalars(
        select(Folder).where(Folder.user_id == user.id).order_by(func.lower(Folder.name))
    )
    return [_folder_out(db, user, f) for f in folders]


@router.post("/api/folders", status_code=status.HTTP_201_CREATED)
def create_folder(body: FolderIn, user: CurrentUser, db: DB) -> FolderOut:
    count = db.scalar(select(func.count()).select_from(Folder).where(Folder.user_id == user.id))
    if (count or 0) >= FOLDERS_PER_USER:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"At most {FOLDERS_PER_USER} folders"
        )
    folder = Folder(user_id=user.id, name=body.name)
    db.add(folder)
    _commit_name(db)
    return _folder_out(db, user, folder)


@router.patch("/api/folders/{folder_id}")
def rename_folder(folder_id: int, body: FolderIn, user: CurrentUser, db: DB) -> FolderOut:
    folder = _own_folder(db, user, folder_id)
    folder.name = body.name
    _commit_name(db)
    return _folder_out(db, user, folder)


@router.delete("/api/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: int, user: CurrentUser, db: DB) -> None:
    """Ungroups its documents (their document_folders rows cascade); never deletes documents."""
    db.delete(_own_folder(db, user, folder_id))
    db.commit()


@router.get("/api/tags")
def list_tags(user: CurrentUser, db: DB) -> TagSummary:
    """The caller's tags with how many readable, unarchived documents carry each."""
    rows = db.execute(
        select(DocumentTag.tag, func.count())
        .join(Document, Document.id == DocumentTag.document_id)
        .where(DocumentTag.user_id == user.id, Document.archived_at.is_(None), _readable(user))
        .group_by(DocumentTag.tag)
        .order_by(DocumentTag.tag)
    ).all()
    return TagSummary(
        tags=[TagCount(tag=t, count=c) for t, c in rows], suggestions=list(STARTER_TAGS)
    )


@router.put("/api/documents/{doc_id}/folder")
def file_document(
    doc_id: uuid.UUID, body: FolderAssignment, user: CurrentUser, db: DB
) -> FolderAssignment:
    """File a readable document in one of the caller's folders (null unfiles). Not an edit."""
    doc, _ = load_document(db, user, doc_id)
    if body.folder_id is not None:
        _own_folder(db, user, body.folder_id)
    set_folder(db, user, doc.id, body.folder_id)
    db.commit()
    return body


@router.put("/api/documents/{doc_id}/tags")
def tag_document(doc_id: uuid.UUID, body: TagsIn, user: CurrentUser, db: DB) -> TagsOut:
    """Replace the caller's tags on a readable document. Not an edit."""
    doc, _ = load_document(db, user, doc_id)
    set_tags(db, user, doc.id, body.tags)
    db.commit()
    return TagsOut(tags=body.tags)
