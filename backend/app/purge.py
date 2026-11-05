"""Remove the seeded demo identities and everything they own (production cut-over, ADR-009).

Demo users are the rows with a `login_key`. OAuth users never have one. Removed:
the demo users and their sessions, documents they own (with those documents' grants and
attachments), grants they gave or received, and attachments they uploaded anywhere. The
database cascade cannot reach object storage, so attachment objects are deleted explicitly.
"""

from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import Attachment, Document, DocumentGrant, User, UserIdentity
from app.storage import Storage, StorageError


@dataclass
class PurgePlan:
    users: list[tuple[int, str]]  # (id, login_key)
    document_ids: list[str]
    grant_ids: list[int]
    attachment_keys: list[str]

    @property
    def empty(self) -> bool:
        return not self.users

    def summary(self) -> str:
        names = ", ".join(f"{key}#{uid}" for uid, key in self.users) or "none"
        return (
            f"demo users: {names}\n"
            f"documents owned by them: {len(self.document_ids)}\n"
            f"grants given/received/on those documents: {len(self.grant_ids)}\n"
            f"attachment objects: {len(self.attachment_keys)}"
        )


@dataclass
class PurgeResult:
    plan: PurgePlan
    orphaned_keys: list[str] = field(default_factory=list)


class PurgeRefused(RuntimeError):
    pass


def plan_purge(db: Session) -> PurgePlan:
    users = db.execute(
        select(User.id, User.login_key).where(User.login_key.is_not(None)).order_by(User.id)
    ).all()
    user_ids = [uid for uid, _ in users]
    if user_ids and db.scalar(
        select(UserIdentity.id).where(UserIdentity.user_id.in_(user_ids)).limit(1)
    ):
        # Should be impossible (OAuth never sets login_key); refuse rather than delete a person.
        raise PurgeRefused("a demo user has an OAuth identity; inspect before purging")
    doc_ids = list(db.scalars(select(Document.id).where(Document.owner_id.in_(user_ids))))
    grant_ids = list(
        db.scalars(
            select(DocumentGrant.id).where(
                or_(
                    DocumentGrant.document_id.in_(doc_ids),
                    DocumentGrant.grantee_id.in_(user_ids),
                    DocumentGrant.granted_by.in_(user_ids),
                )
            )
        )
    )
    keys = list(
        db.scalars(
            select(Attachment.object_key).where(
                or_(Attachment.document_id.in_(doc_ids), Attachment.uploaded_by.in_(user_ids))
            )
        )
    )
    return PurgePlan(
        users=[(uid, str(key)) for uid, key in users],
        document_ids=[str(d) for d in doc_ids],
        grant_ids=grant_ids,
        attachment_keys=keys,
    )


def purge_demo_data(db: Session, storage: Storage | None) -> PurgeResult:
    """Delete everything in `plan_purge` in one transaction, then the storage objects."""
    plan = plan_purge(db)
    if plan.empty:
        return PurgeResult(plan)
    if plan.attachment_keys and storage is None:
        raise PurgeRefused("attachment objects exist but storage is not configured")
    user_ids = [uid for uid, _ in plan.users]
    db.execute(delete(Attachment).where(Attachment.object_key.in_(plan.attachment_keys)))
    db.execute(delete(DocumentGrant).where(DocumentGrant.id.in_(plan.grant_ids)))
    db.execute(delete(Document).where(Document.owner_id.in_(user_ids)))
    db.execute(delete(User).where(User.id.in_(user_ids)))  # sessions cascade
    db.commit()
    result = PurgeResult(plan)
    for key in plan.attachment_keys:
        assert storage is not None
        try:
            storage.delete(key)
        except StorageError:
            result.orphaned_keys.append(key)
    return result
