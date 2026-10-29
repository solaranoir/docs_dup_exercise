import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.models import Document, DocumentGrant, User
from app.routes.documents import DB, load_document

router = APIRouter(prefix="/api/documents/{doc_id}/grants", tags=["sharing"])


class GrantIn(BaseModel):
    user_id: int
    # MVP decision (#7): view-only sharing. The column already allows "editor" for later.
    role: Literal["viewer"] = "viewer"


class GrantOut(BaseModel):
    user_id: int
    display_name: str
    role: str
    created_at: datetime


def _owned(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    doc, permission = load_document(db, user, doc_id)
    if permission != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can manage sharing")
    return doc


def _grants(db: Session, doc_id: uuid.UUID) -> list[GrantOut]:
    rows = db.execute(
        select(DocumentGrant, User)
        .join(User, User.id == DocumentGrant.grantee_id)
        .where(DocumentGrant.document_id == doc_id)
        .order_by(User.display_name)
    ).all()
    return [
        GrantOut(user_id=u.id, display_name=u.display_name, role=g.role, created_at=g.created_at)
        for g, u in rows
    ]


@router.get("")
def list_grants(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> list[GrantOut]:
    _owned(db, user, doc_id)
    return _grants(db, doc_id)


@router.post("")
def grant_access(
    doc_id: uuid.UUID, body: GrantIn, user: CurrentUser, db: DB, response: Response
) -> GrantOut:
    doc = _owned(db, user, doc_id)
    grantee = db.get(User, body.user_id)
    if grantee is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown user")
    if grantee.id == doc.owner_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The owner already has access")
    grant = db.scalar(
        select(DocumentGrant).where(
            DocumentGrant.document_id == doc_id, DocumentGrant.grantee_id == grantee.id
        )
    )
    if grant is None:
        grant = DocumentGrant(
            document_id=doc_id, grantee_id=grantee.id, role=body.role, granted_by=user.id
        )
        db.add(grant)
        db.commit()
        response.status_code = status.HTTP_201_CREATED
    else:
        grant.role = body.role
        db.commit()
    return GrantOut(
        user_id=grantee.id,
        display_name=grantee.display_name,
        role=grant.role,
        created_at=grant.created_at,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_access(doc_id: uuid.UUID, user_id: int, user: CurrentUser, db: DB) -> None:
    _owned(db, user, doc_id)
    grant = db.scalar(
        select(DocumentGrant).where(
            DocumentGrant.document_id == doc_id, DocumentGrant.grantee_id == user_id
        )
    )
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No access to revoke")
    db.delete(grant)
    db.commit()
