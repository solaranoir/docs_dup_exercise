"""Orphaned attachment objects (audit A12).

An object is orphaned when no ``attachments`` row points at it: a storage delete failed after
its document or attachment was deleted (logged, never retried), or an upload's database commit
failed after the bytes were stored. Orphans cost a little storage and, more importantly, keep
bytes that a user deleted. ``scripts/sweep_orphans.py`` finds and removes them.

Uploads store the object *before* committing the row, so an object younger than ``MIN_AGE`` may
belong to an upload still in progress and is never treated as an orphan.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attachment
from app.storage import Storage, StorageError

PREFIX = "documents/"
MIN_AGE = timedelta(hours=1)


@dataclass
class SweepResult:
    scanned: int = 0
    orphans: list[str] = field(default_factory=list)
    deleted: int = 0
    failed: list[str] = field(default_factory=list)


def find_orphans(
    db: Session, storage: Storage, now: datetime | None = None, min_age: timedelta = MIN_AGE
) -> SweepResult:
    """Objects under ``documents/`` older than ``min_age`` with no attachment row."""
    cutoff = (now or datetime.now(UTC)) - min_age
    result = SweepResult()
    candidates: list[str] = []
    for key, modified in storage.list(PREFIX):
        result.scanned += 1
        if modified <= cutoff:
            candidates.append(key)
    if candidates:
        known = set(db.scalars(select(Attachment.object_key)))
        result.orphans = [key for key in candidates if key not in known]
    return result


def sweep(storage: Storage, result: SweepResult) -> SweepResult:
    """Delete the orphans ``find_orphans`` reported; failures are listed, not raised."""
    for key in result.orphans:
        try:
            storage.delete(key)
            result.deleted += 1
        except StorageError:
            result.failed.append(key)
    return result
