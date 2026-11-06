"""Persistence model. Mirrors the proposal's data model; Alembic owns the actual DDL."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.content import plain_text

# JSONB on PostgreSQL (ADR-002); plain JSON elsewhere so unit tests can run without a server.
JsonContent = JSON().with_variant(JSONB(), "postgresql")

EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": [{"type": "paragraph"}]}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_users_email_lower"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Demo identities only (ADR-004); OAuth users have none.
    login_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserIdentity(Base):
    """A sign-in method for a user, keyed by the provider's stable account id (ADR-009)."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_user_identities_provider_subject"
        ),
        CheckConstraint("provider IN ('github', 'google')", name="ck_user_identities_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    provider_subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AllowedEmail(Base):
    """Invite allowlist: only these verified emails may sign in (ADR-009)."""

    __tablename__ = "allowed_emails"
    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_allowed_emails_lower"),)

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    """Server-side session. Only the SHA-256 of the cookie token is stored (ADR-009)."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("length(title) BETWEEN 1 AND 160", name="ck_documents_title_len"),
        CheckConstraint("revision >= 1", name="ck_documents_revision_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    content_json: Mapped[dict[str, Any]] = mapped_column(JsonContent, default=lambda: EMPTY_DOC)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    # Set by the owner to retire a document (DOC-021): hidden from lists, read-only until restored.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when the owner deletes it (DOC-031, ADR-012): in the Trash, invisible to everyone except
    # the owner's Trash view, and permanently removed TRASH_DAYS later.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Plain text of content_json for search (DOC-017). Derived, never set directly: the listeners
    # below cover ORM writes and apply_update() covers its bulk UPDATE. On PostgreSQL the
    # migration also adds a generated ``search_vector`` tsvector (title + this) with a GIN index;
    # it is not mapped here because it only exists on PostgreSQL.
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")


@event.listens_for(Document, "before_insert")
@event.listens_for(Document, "before_update")
def _sync_search_text(_mapper: Any, _conn: Any, doc: Document) -> None:
    doc.search_text = plain_text(doc.content_json if doc.content_json is not None else EMPTY_DOC)


class DocumentVisit(Base):
    """When a user last opened a document, for their "Recently opened" list (DOC-022)."""

    __tablename__ = "document_visits"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    last_opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Folder(Base):
    """A user's private, one-level folder (ADR-010). Names are unique per user, ignoring case."""

    __tablename__ = "folders"
    __table_args__ = (CheckConstraint("length(name) BETWEEN 1 AND 60", name="ck_folders_name_len"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentFolder(Base):
    """Where a user filed a document: at most one folder per (user, document)."""

    __tablename__ = "document_folders"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), index=True)


class DocumentTag(Base):
    """One of a user's private tags on a document (normalised lowercase, ADR-010)."""

    __tablename__ = "document_tags"
    __table_args__ = (
        CheckConstraint(
            "tag = lower(tag) AND length(tag) BETWEEN 1 AND 32", name="ck_document_tags_tag"
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    tag: Mapped[str] = mapped_column(String(32), primary_key=True)


class DocumentGrant(Base):
    __tablename__ = "document_grants"
    __table_args__ = (
        UniqueConstraint("document_id", "grantee_id", name="uq_document_grants_doc_grantee"),
        CheckConstraint("role IN ('viewer', 'editor')", name="ck_document_grants_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    grantee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (CheckConstraint("size_bytes >= 0", name="ck_attachments_size"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
