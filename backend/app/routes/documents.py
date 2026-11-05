import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, false, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.content import ContentError, plain_text, validate_content
from app.db import get_db
from app.models import (
    EMPTY_DOC,
    Attachment,
    Document,
    DocumentFolder,
    DocumentGrant,
    DocumentTag,
    DocumentVisit,
    User,
    utcnow,
)
from app.organization import normalize_tag, organization_for, set_folder, set_tags
from app.policy import Permission, can_delete, can_edit, can_read, permission_for
from app.search import MAX_QUERY_LENGTH, match_and_rank, query_terms, snippet
from app.storage import Storage, StorageError, optional_storage

router = APIRouter(prefix="/api/documents", tags=["documents"])
log = logging.getLogger(__name__)
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
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    # When the *caller* last opened it; drives "Recently opened" (DOC-022).
    last_opened_at: datetime | None = None
    # The caller's own folder and tags (ADR-010); never anyone else's.
    folder_id: int | None = None
    tags: list[str] = []


class DocumentOut(DocumentSummary):
    content_json: dict[str, Any]


class SearchResult(DocumentSummary):
    # Plain text around the first body match (or the opening lines); None for an empty body.
    snippet: str | None


def _summary(
    doc: Document, owner: User, permission: Permission, last_opened_at: datetime | None = None
) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        title=doc.title,
        revision=doc.revision,
        owner=OwnerOut(id=owner.id, display_name=owner.display_name),
        permission=permission,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        archived_at=doc.archived_at,
        last_opened_at=last_opened_at,
    )


def document_out(
    db: Session,
    doc: Document,
    permission: Permission,
    last_opened_at: datetime | None = None,
    *,
    viewer: User | None = None,
) -> DocumentOut:
    """With ``viewer``, includes that user's own folder and tags for the document."""
    owner = db.get(User, doc.owner_id)
    assert owner is not None
    out = DocumentOut(
        **_summary(doc, owner, permission, last_opened_at).model_dump(),
        content_json=doc.content_json,
    )
    if viewer is not None:
        folders, tags = organization_for(db, viewer, [doc.id])
        out.folder_id, out.tags = folders.get(doc.id), tags.get(doc.id, [])
    return out


def load_document(db: Session, user: User, doc_id: uuid.UUID) -> tuple[Document, Permission]:
    doc = db.get(Document, doc_id)
    permission = permission_for(db, user, doc) if doc else None
    # Privacy-preserving: documents the caller cannot read look exactly like missing ones.
    if doc is None or not can_read(permission):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    assert permission is not None
    return doc, permission


def _record_visit(db: Session, user: User, doc: Document) -> datetime:
    """Upsert the caller's last-opened time (idempotent under concurrent opens)."""
    now = utcnow()
    values = {"user_id": user.id, "document_id": doc.id, "last_opened_at": now}
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(DocumentVisit).values(**values)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id", "document_id"], set_={"last_opened_at": now}
        )
    )
    db.commit()
    return now


@router.get("")
def list_documents(user: CurrentUser, db: DB, archived: bool = False) -> list[DocumentSummary]:
    """The caller's own and shared documents; archived ones only with ``?archived=true``."""
    visit = DocumentVisit.last_opened_at
    visit_join = (DocumentVisit.document_id == Document.id) & (DocumentVisit.user_id == user.id)
    state = Document.archived_at.is_not(None) if archived else Document.archived_at.is_(None)
    owned = db.execute(
        select(Document, User, visit)
        .join(User, User.id == Document.owner_id)
        .outerjoin(DocumentVisit, visit_join)
        .where(Document.owner_id == user.id, state)
    ).all()
    shared = db.execute(
        select(Document, User, DocumentGrant.role, visit)
        .join(DocumentGrant, DocumentGrant.document_id == Document.id)
        .join(User, User.id == Document.owner_id)
        .outerjoin(DocumentVisit, visit_join)
        .where(DocumentGrant.grantee_id == user.id, state)
    ).all()
    items = [_summary(d, o, "owner", v) for d, o, v in owned]
    items += [_summary(d, o, "editor" if r == "editor" else "viewer", v) for d, o, r, v in shared]
    folders, tags = organization_for(db, user, [i.id for i in items])
    for item in items:
        item.folder_id, item.tags = folders.get(item.id), tags.get(item.id, [])
    return sorted(items, key=lambda s: s.updated_at, reverse=True)


SEARCH_LIMIT = 50


def _organisation_filters(user: User, folder: str | None, tag: str | None) -> list[Any]:
    """SQL conditions for the caller's own folder/tag (ADR-010). Unknown tags match nothing."""
    conditions: list[Any] = []
    if folder is not None:
        filed = exists().where(
            DocumentFolder.user_id == user.id, DocumentFolder.document_id == Document.id
        )
        if folder == "unfiled":
            conditions.append(~filed)
        else:
            conditions.append(filed.where(DocumentFolder.folder_id == int(folder)))
    if tag:
        try:
            normalized = normalize_tag(tag)
        except ValueError:
            return [false()]
        conditions.append(
            exists().where(
                DocumentTag.user_id == user.id,
                DocumentTag.document_id == Document.id,
                DocumentTag.tag == normalized,
            )
        )
    return conditions


@router.get("/search")
def search_documents(
    user: CurrentUser,
    db: DB,
    q: Annotated[str, Query(max_length=MAX_QUERY_LENGTH)] = "",
    folder: Annotated[str | None, Query(pattern=r"^(\d{1,9}|unfiled)$")] = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
) -> list[SearchResult]:
    """Title and body search over the caller's own and shared, unarchived documents (DOC-017).

    The permission filter is part of the SQL, before the LIMIT, so other users' documents can
    never appear, be counted or contribute snippets. Best matches first, at most SEARCH_LIMIT.
    ``folder`` (an id or ``unfiled``) and ``tag`` narrow to the caller's *own* organisation
    (ADR-010), also in SQL before the LIMIT.
    """
    terms = query_terms(q)
    if not terms:
        return []
    filters = _organisation_filters(user, folder, tag)
    match, order = match_and_rank(db.get_bind().dialect.name, terms)
    shared_with_me = (DocumentGrant.document_id == Document.id) & (
        DocumentGrant.grantee_id == user.id
    )
    visit_join = (DocumentVisit.document_id == Document.id) & (DocumentVisit.user_id == user.id)
    rows = db.execute(
        select(Document, User, DocumentGrant.role, DocumentVisit.last_opened_at)
        .join(User, User.id == Document.owner_id)
        # (document_id, grantee_id) is unique, so this join never duplicates a document.
        .outerjoin(DocumentGrant, shared_with_me)
        .outerjoin(DocumentVisit, visit_join)
        .where(
            or_(Document.owner_id == user.id, DocumentGrant.id.is_not(None)),
            Document.archived_at.is_(None),
            match,
            *filters,
        )
        .order_by(*order, Document.id)
        .limit(SEARCH_LIMIT)
    ).all()
    folders, tags = organization_for(db, user, [doc.id for doc, *_ in rows])
    results = []
    for doc, owner, role, opened in rows:
        permission: Permission = (
            "owner" if doc.owner_id == user.id else "editor" if role == "editor" else "viewer"
        )
        summary = _summary(doc, owner, permission, opened)
        summary.folder_id, summary.tags = folders.get(doc.id), tags.get(doc.id, [])
        results.append(
            SearchResult(**summary.model_dump(), snippet=snippet(doc.search_text, terms))
        )
    return results


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(body: DocumentCreate, user: CurrentUser, db: DB) -> DocumentOut:
    doc = Document(owner_id=user.id, title=body.title, content_json=body.content_json or EMPTY_DOC)
    db.add(doc)
    db.commit()
    return document_out(db, doc, "owner")


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> DocumentOut:
    doc, permission = load_document(db, user, doc_id)
    return document_out(db, doc, permission, _record_visit(db, user, doc), viewer=user)


@router.patch("/{doc_id}")
def update_document(
    doc_id: uuid.UUID, body: DocumentPatch, user: CurrentUser, db: DB
) -> DocumentOut:
    doc, permission = load_editable(db, user, doc_id)
    values: dict[str, Any] = {}
    if body.title is not None:
        values["title"] = body.title
    if body.content_json is not None:
        values["content_json"] = body.content_json
    apply_update(db, doc, body.expected_revision, values)
    return document_out(db, doc, permission, viewer=user)


def load_editable(db: Session, user: User, doc_id: uuid.UUID) -> tuple[Document, Permission]:
    doc, permission = load_document(db, user, doc_id)
    if not can_edit(permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You have view-only access")
    if doc.archived_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This document is archived. Restore it to make changes."
        )
    return doc, permission


def _load_owned(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    doc, permission = load_document(db, user, doc_id)
    if not can_delete(permission):  # owner-only, like delete
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can archive or restore")
    return doc


@router.post("/{doc_id}/archive")
def archive_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> DocumentOut:
    """Hide from everyone's lists and make read-only (DOC-021). Idempotent; revision unchanged."""
    doc = _load_owned(db, user, doc_id)
    if doc.archived_at is None:
        _set_archived(db, doc, utcnow())
    return document_out(db, doc, "owner", viewer=user)


@router.post("/{doc_id}/restore")
def restore_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> DocumentOut:
    doc = _load_owned(db, user, doc_id)
    if doc.archived_at is not None:
        _set_archived(db, doc, None)
    return document_out(db, doc, "owner", viewer=user)


def _set_archived(db: Session, doc: Document, when: datetime | None) -> None:
    # Explicit UPDATE so the ORM's onupdate doesn't treat archiving as an edit (updated_at).
    db.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(archived_at=when, updated_at=Document.updated_at)
    )
    db.commit()
    db.refresh(doc)


def copy_title(title: str) -> str:
    return f"Copy of {title}"[:TITLE_MAX].rstrip()


@router.post("/{doc_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> DocumentOut:
    """Anyone who can read a document can copy it into a new document they own (DOC-020).

    Title and content are copied, and the caller's own folder and tags (ADR-010); attachments,
    sharing and archive state are not.
    """
    source, _ = load_document(db, user, doc_id)
    copy = Document(
        owner_id=user.id, title=copy_title(source.title), content_json=source.content_json
    )
    db.add(copy)
    db.flush()
    # The copy is filed and tagged like the source *in the duplicating user's own view*.
    folders, tags = organization_for(db, user, [source.id])
    set_folder(db, user, copy.id, folders.get(source.id))
    set_tags(db, user, copy.id, tags.get(source.id, []))
    db.commit()
    return document_out(db, copy, "owner", viewer=user)


def apply_update(
    db: Session, doc: Document, expected_revision: int, values: dict[str, Any]
) -> None:
    """Compare-and-swap on revision (ADR-003): a stale writer never overwrites newer content."""
    if "content_json" in values:  # keep search in step with content (DOC-017)
        values = {**values, "search_text": plain_text(values["content_json"])}
    result = db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.revision == expected_revision)
        .values(**values, revision=Document.revision + 1, updated_at=utcnow())
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


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    storage: Annotated[Storage | None, Depends(optional_storage)],
) -> None:
    doc, permission = load_document(db, user, doc_id)
    if not can_delete(permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete a document")
    keys = list(db.scalars(select(Attachment.object_key).where(Attachment.document_id == doc.id)))
    db.delete(doc)
    db.commit()
    for key in keys:
        if storage is None:
            break
        try:
            storage.delete(key)
        except StorageError:
            log.warning("orphaned attachment object after document delete: %s", key)
