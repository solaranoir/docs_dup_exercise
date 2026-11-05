import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.allowlist import normalize_email
from app.auth import CurrentUser
from app.models import Document, DocumentGrant, User
from app.routes.documents import DB, load_document

router = APIRouter(prefix="/api/documents/{doc_id}/grants", tags=["sharing"])


class GrantIn(BaseModel):
    # Share with an existing account by email (ADR-009). There is deliberately no user
    # directory endpoint, so nobody can list who has an account.
    email: str
    # MVP decision (#7): view-only sharing. The column already allows "editor" for later.
    role: Literal["viewer"] = "viewer"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class GrantOut(BaseModel):
    user_id: int
    display_name: str
    email: str | None
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
    return [_out(g, u) for g, u in rows]


def _out(grant: DocumentGrant, user: User) -> GrantOut:
    return GrantOut(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        role=grant.role,
        created_at=grant.created_at,
    )


@router.get("")
def list_grants(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> list[GrantOut]:
    _owned(db, user, doc_id)
    return _grants(db, doc_id)


@router.post("")
def grant_access(
    doc_id: uuid.UUID, body: GrantIn, user: CurrentUser, db: DB, response: Response
) -> GrantOut:
    doc = _owned(db, user, doc_id)
    grantee = db.scalar(select(User).where(User.email == body.email))
    if grantee is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No Solara Docs account uses that email. They need to sign in once before you "
            "can share with them.",
        )
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
    return _out(grant, grantee)


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
