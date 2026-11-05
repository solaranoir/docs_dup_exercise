"""Personal folders and tags (ADR-010): normalisation and per-user lookups."""

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DocumentFolder, DocumentTag, User

TAG_MAX = 32
TAGS_PER_DOCUMENT = 20
FOLDER_NAME_MAX = 60
FOLDERS_PER_USER = 100
# Suggested in the UI; Phase 4 templates may apply them (ADR-010).
STARTER_TAGS = ("pota", "sota", "satellite", "antenna", "contest", "research")

_SPACES = re.compile(r"\s+")


def normalize_tag(raw: str) -> str:
    """Trim, lowercase, spaces → '-'. Raises ValueError for empty or overlong tags."""
    tag = _SPACES.sub("-", raw.strip().lower())
    if not 1 <= len(tag) <= TAG_MAX:
        raise ValueError(f"Tags must be 1–{TAG_MAX} characters")
    if any(not (ch.isalnum() or ch in "-_./+#") for ch in tag):
        raise ValueError("Tags may use letters, numbers and - _ . / + #")
    return tag


def normalize_tags(raw: Iterable[str]) -> list[str]:
    tags = sorted({normalize_tag(t) for t in raw})
    if len(tags) > TAGS_PER_DOCUMENT:
        raise ValueError(f"At most {TAGS_PER_DOCUMENT} tags per document")
    return tags


def normalize_folder_name(raw: str) -> str:
    name = _SPACES.sub(" ", raw.strip())
    if not 1 <= len(name) <= FOLDER_NAME_MAX:
        raise ValueError(f"Folder names must be 1–{FOLDER_NAME_MAX} characters")
    return name


def organization_for(
    db: Session, user: User, document_ids: Iterable[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, list[str]]]:
    """The caller's folder id and tags for each document (only their own rows, ever)."""
    ids = list(document_ids)
    if not ids:
        return {}, {}
    folders: dict[uuid.UUID, int] = {
        doc_id: folder_id
        for doc_id, folder_id in db.execute(
            select(DocumentFolder.document_id, DocumentFolder.folder_id).where(
                DocumentFolder.user_id == user.id, DocumentFolder.document_id.in_(ids)
            )
        )
    }
    tags: dict[uuid.UUID, list[str]] = defaultdict(list)
    for doc_id, tag in db.execute(
        select(DocumentTag.document_id, DocumentTag.tag)
        .where(DocumentTag.user_id == user.id, DocumentTag.document_id.in_(ids))
        .order_by(DocumentTag.tag)
    ):
        tags[doc_id].append(tag)
    return folders, dict(tags)


def set_folder(db: Session, user: User, document_id: uuid.UUID, folder_id: int | None) -> None:
    """File (or unfile, with None) a document in one of the caller's folders. Caller commits."""
    db.execute(
        delete(DocumentFolder).where(
            DocumentFolder.user_id == user.id, DocumentFolder.document_id == document_id
        )
    )
    if folder_id is not None:
        db.add(DocumentFolder(user_id=user.id, document_id=document_id, folder_id=folder_id))


def set_tags(db: Session, user: User, document_id: uuid.UUID, tags: list[str]) -> None:
    """Replace the caller's tags on a document. Caller commits."""
    db.execute(
        delete(DocumentTag).where(
            DocumentTag.user_id == user.id, DocumentTag.document_id == document_id
        )
    )
    db.add_all(DocumentTag(user_id=user.id, document_id=document_id, tag=t) for t in tags)
