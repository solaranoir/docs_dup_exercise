"""The owner's Trash: list, restore, delete forever (DOC-031, ADR-012)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update

from app.auth import CurrentUser
from app.models import Document, User
from app.routes.documents import DB
from app.storage import Storage, optional_storage
from app.trash import TRASH_DAYS, TrashPurger, delete_permanently, purge_after, schedule_purge

router = APIRouter(prefix="/api/trash", tags=["trash"])


class TrashItem(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    deleted_at: datetime
    purge_after: datetime


class TrashList(BaseModel):
    retention_days: int
    items: list[TrashItem]


def _item(doc: Document) -> TrashItem:
    assert doc.deleted_at is not None
    return TrashItem(
        id=doc.id,
        title=doc.title,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        archived_at=doc.archived_at,
        deleted_at=doc.deleted_at,
        purge_after=purge_after(doc.deleted_at),
    )


def _load_trashed(db: DB, user: User, doc_id: uuid.UUID) -> Document:
    """Only the owner sees their Trash; anything else (including live documents) is a 404."""
    doc = db.get(Document, doc_id)
    if doc is None or doc.owner_id != user.id or doc.deleted_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in your Trash")
    return doc


@router.get("")
def list_trash(
    user: CurrentUser, db: DB, background: BackgroundTasks, purger: TrashPurger
) -> TrashList:
    """The caller's deleted documents, most recently deleted first."""
    schedule_purge(background, purger)
    docs = db.scalars(
        select(Document)
        .where(Document.owner_id == user.id, Document.deleted_at.is_not(None))
        .order_by(Document.deleted_at.desc(), Document.id)
    )
    return TrashList(retention_days=TRASH_DAYS, items=[_item(d) for d in docs])


@router.post("/{doc_id}/restore")
def restore(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> TrashItem:
    """Back where it was: same grants, attachments, folder, tags and archive state."""
    doc = _load_trashed(db, user, doc_id)
    item = _item(doc)
    db.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(deleted_at=None, updated_at=Document.updated_at)
    )
    db.commit()
    return item


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_forever(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    storage: Annotated[Storage | None, Depends(optional_storage)],
) -> None:
    """Skip the wait: remove the document and its attachments now. Cannot be undone."""
    delete_permanently(db, storage, [_load_trashed(db, user, doc_id)])
