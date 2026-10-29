"""Central document authorization policy. Deny by default."""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentGrant, User

Permission = Literal["owner", "editor", "viewer"]


def permission_for(db: Session, user: User, doc: Document) -> Permission | None:
    if doc.owner_id == user.id:
        return "owner"
    role = db.scalar(
        select(DocumentGrant.role).where(
            DocumentGrant.document_id == doc.id, DocumentGrant.grantee_id == user.id
        )
    )
    if role == "editor":
        return "editor"
    if role == "viewer":
        return "viewer"
    return None


def can_read(permission: Permission | None) -> bool:
    return permission is not None


def can_edit(permission: Permission | None) -> bool:
    return permission in ("owner", "editor")


def can_delete(permission: Permission | None) -> bool:
    return permission == "owner"
