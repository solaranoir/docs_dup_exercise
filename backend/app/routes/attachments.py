import logging
import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth import CurrentUser
from app.config import Settings, get_settings
from app.models import Attachment
from app.routes.documents import DB, load_document, load_editable
from app.storage import Storage, StorageError, get_storage
from app.uploads import read_upload

router = APIRouter(prefix="/api/documents/{doc_id}/attachments", tags=["attachments"])
log = logging.getLogger(__name__)
StorageDep = Annotated[Storage, Depends(get_storage)]


class AttachmentOut(BaseModel):
    id: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime


def _out(a: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=a.id,
        original_name=a.original_name,
        mime_type=a.mime_type,
        size_bytes=a.size_bytes,
        created_at=a.created_at,
    )


def _storage_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Attachment storage is unavailable")


@router.get("")
def list_attachments(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> list[AttachmentOut]:
    load_document(db, user, doc_id)
    rows = db.scalars(
        select(Attachment).where(Attachment.document_id == doc_id).order_by(Attachment.created_at)
    )
    return [_out(a) for a in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    storage: StorageDep,
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
) -> AttachmentOut:
    load_editable(db, user, doc_id)
    count = db.scalar(
        select(func.count()).select_from(Attachment).where(Attachment.document_id == doc_id)
    )
    if (count or 0) >= settings.max_attachments_per_document:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A document can have at most {settings.max_attachments_per_document} attachments.",
        )
    upload = await read_upload(file, settings.max_upload_bytes)
    attachment_id = uuid.uuid4()
    # Object keys never contain user input, so names cannot traverse or collide.
    key = f"documents/{doc_id}/attachments/{attachment_id}"
    try:
        storage.put(key, upload.data, upload.mime_type)
    except StorageError:
        log.exception("attachment upload failed doc=%s", doc_id)
        raise _storage_unavailable() from None
    attachment = Attachment(
        id=attachment_id,
        document_id=doc_id,
        original_name=upload.name,
        mime_type=upload.mime_type,
        size_bytes=len(upload.data),
        object_key=key,
        uploaded_by=user.id,
    )
    db.add(attachment)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return _out(attachment)


def _get(db: DB, doc_id: uuid.UUID, attachment_id: uuid.UUID) -> Attachment:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.document_id != doc_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    return attachment


@router.get("/{attachment_id}")
def download_attachment(
    doc_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    storage: StorageDep,
) -> Response:
    load_document(db, user, doc_id)
    attachment = _get(db, doc_id, attachment_id)
    try:
        data = storage.get(attachment.object_key)
    except StorageError:
        log.exception("attachment download failed id=%s", attachment_id)
        raise _storage_unavailable() from None
    ascii_name = attachment.original_name.encode("ascii", "replace").decode().replace('"', "_")
    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(attachment.original_name)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    doc_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    storage: StorageDep,
) -> None:
    load_editable(db, user, doc_id)
    attachment = _get(db, doc_id, attachment_id)
    key = attachment.object_key
    db.delete(attachment)
    db.commit()
    try:
        storage.delete(key)
    except StorageError:
        log.warning("orphaned attachment object: %s", key)
