"""Trash with 30-day recovery (DOC-031, ADR-012).

Deleting a document only sets ``deleted_at``: it disappears from every list, search and
document route (including for people it was shared with) but keeps its grants, attachments,
folders and tags, so a restore brings everything back. After ``TRASH_DAYS`` it is removed for
good, together with its attachment objects (the database cascade cannot reach object storage).

The free Render plan has no cron, so expired documents are purged opportunistically: at most
once per ``PURGE_INTERVAL`` the API runs a purge after responding to a list request. The
runbook's ``scripts/purge_trash.py`` does the same on demand.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models import Attachment, Document, utcnow
from app.storage import Storage, StorageError, optional_storage

log = logging.getLogger(__name__)

TRASH_DAYS = 30
PURGE_INTERVAL_SECONDS = 3600
PURGE_BATCH = 200

LIVE = Document.deleted_at.is_(None)
"""Documents outside the Trash: add to every query that lists or counts documents."""


def purge_after(deleted_at: datetime) -> datetime:
    return deleted_at + timedelta(days=TRASH_DAYS)


@dataclass
class PurgeResult:
    documents: int = 0
    orphaned_keys: list[str] = field(default_factory=list)


def delete_permanently(
    db: Session, storage: Storage | None, documents: Iterable[Document]
) -> PurgeResult:
    """Remove documents and their attachment objects. Rows first, then objects: a failed
    object delete leaves an orphan (logged) rather than a row pointing at nothing."""
    docs = list(documents)
    result = PurgeResult()
    if not docs:
        return result
    ids = [d.id for d in docs]
    keys = list(db.scalars(select(Attachment.object_key).where(Attachment.document_id.in_(ids))))
    for doc in docs:
        db.delete(doc)
    db.commit()
    result.documents = len(docs)
    for key in keys:
        try:
            if storage is None:
                raise StorageError("storage is not configured")
            storage.delete(key)
        except StorageError:
            log.warning("orphaned attachment object after permanent delete: %s", key)
            result.orphaned_keys.append(key)
    return result


def purge_expired(db: Session, storage: Storage | None, now: datetime | None = None) -> PurgeResult:
    """Permanently delete every document that has been in the Trash for ``TRASH_DAYS``."""
    cutoff = (now or utcnow()) - timedelta(days=TRASH_DAYS)
    total = PurgeResult()
    while True:
        batch = list(
            db.scalars(
                select(Document)
                .where(Document.deleted_at.is_not(None), Document.deleted_at <= cutoff)
                .limit(PURGE_BATCH)
            )
        )
        if not batch:
            break
        result = delete_permanently(db, storage, batch)
        total.documents += result.documents
        total.orphaned_keys += result.orphaned_keys
    if total.documents:
        log.info("trash purge removed %d documents", total.documents)
    return total


Purger = Callable[[], None]


def trash_purger(storage: Annotated[Storage | None, Depends(optional_storage)]) -> Purger:
    """The background purge, as a dependency so tests can point it at their own database."""

    def run() -> None:
        try:
            with get_sessionmaker()() as db:
                purge_expired(db, storage)
        except Exception:  # never let housekeeping break a request
            log.exception("trash purge failed")

    return run


TrashPurger = Annotated[Purger, Depends(trash_purger)]

_lock = threading.Lock()
_last_run = 0.0


def schedule_purge(background: BackgroundTasks, purger: Purger) -> None:
    """Queue a purge after the response, at most once per interval per process."""
    global _last_run
    with _lock:
        now = time.monotonic()
        if _last_run and now - _last_run < PURGE_INTERVAL_SECONDS:
            return
        _last_run = now
    background.add_task(purger)


def reset_schedule() -> None:
    global _last_run
    with _lock:
        _last_run = 0.0
