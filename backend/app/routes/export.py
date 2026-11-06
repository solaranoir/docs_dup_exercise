"""Markdown export of one document or everything a user owns (DOC-028, DOC-030, DOC-033).

Archives are written to a spooled temporary file (in memory up to a few MB, then on disk) and
streamed, so exporting many attachments never holds them all in memory at once.
"""

import logging
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import IO, Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.auth import CurrentUser
from app.export import safe_file_name, slug, to_markdown, unique
from app.models import Attachment, Document, Folder
from app.organization import organization_for
from app.ratelimit import limit_exports
from app.routes.documents import DB, load_document
from app.storage import Storage, StorageError, optional_storage

router = APIRouter(tags=["export"], dependencies=[Depends(limit_exports)])
log = logging.getLogger(__name__)
OptionalStorage = Annotated[Storage | None, Depends(optional_storage)]

SPOOL_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 256 * 1024


def _disposition(filename: str) -> dict[str, str]:
    ascii_name = filename.encode("ascii", "replace").decode().replace('"', "_")
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Attachments are temporarily unavailable, so the export could not be made. "
        "Please try again shortly.",
    )


def _attachments(db: DB, doc_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Attachment]]:
    by_doc: dict[uuid.UUID, list[Attachment]] = {d: [] for d in doc_ids}
    if doc_ids:
        rows = db.scalars(
            select(Attachment)
            .where(Attachment.document_id.in_(doc_ids))
            .order_by(Attachment.created_at, Attachment.id)
        )
        for a in rows:
            by_doc[a.document_id].append(a)
    return by_doc


def _write_document(
    archive: zipfile.ZipFile,
    prefix: str,
    stem: str,
    doc: Document,
    attachments: list[Attachment],
    storage: Storage | None,
    *,
    strict: bool,
) -> list[str]:
    """``<prefix><stem>.md`` plus ``<prefix>attachments/<name>`` for each attachment.

    ``strict`` (one document): any unreadable attachment fails the export with 503, so the user
    retries. Otherwise (export all) it is skipped and its name returned, so one lost or
    unreachable file never blocks someone from taking the rest of their work.
    """
    if attachments and storage is None and strict:
        raise _storage_unavailable()
    taken: set[str] = set()
    paths: list[str] = []
    missing: list[str] = []
    for a in attachments:
        name = unique(safe_file_name(a.original_name), taken)
        try:
            if storage is None:
                raise StorageError("storage is not configured")
            data = storage.get(a.object_key)
        except StorageError:
            log.exception("export: attachment fetch failed id=%s", a.id)
            if strict:
                raise _storage_unavailable() from None
            missing.append(a.original_name)
            continue
        archive.writestr(f"{prefix}attachments/{name}", data)
        paths.append(f"attachments/{name}")
    archive.writestr(f"{prefix}{stem}.md", to_markdown(doc.title, doc.content_json, paths))
    return missing


def _stream(spool: IO[bytes]) -> Iterator[bytes]:
    try:
        spool.seek(0)
        while chunk := spool.read(CHUNK_BYTES):
            yield chunk
    finally:
        spool.close()


def _zip_response(spool: IO[bytes], filename: str) -> StreamingResponse:
    size = spool.tell()
    headers = {**_disposition(filename), "Content-Length": str(size)}
    return StreamingResponse(_stream(spool), media_type="application/zip", headers=headers)


@router.get("/api/documents/{doc_id}/export")
def export_document(
    doc_id: uuid.UUID, user: CurrentUser, db: DB, storage: OptionalStorage
) -> Response:
    """Markdown for anyone who can read the document: ``.md``, or ``.zip`` with attachments."""
    doc, _permission = load_document(db, user, doc_id)
    stem = slug(doc.title)
    attachments = _attachments(db, [doc.id])[doc.id]
    if not attachments:
        return Response(
            content=to_markdown(doc.title, doc.content_json),
            media_type="text/markdown; charset=utf-8",
            headers=_disposition(f"{stem}.md"),
        )
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    try:
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
            _write_document(archive, "", stem, doc, attachments, storage, strict=True)
    except BaseException:
        spool.close()
        raise
    return _zip_response(spool, f"{stem}.zip")


def _index(
    rows: list[tuple[Document, str]],
    folders: dict[uuid.UUID, str],
    tags: dict[uuid.UUID, list[str]],
    exported_at: datetime,
    missing: list[tuple[Document, str]],
) -> str:
    lines = [
        "# Solara Docs export",
        "",
        f"Exported {exported_at:%Y-%m-%d %H:%M} UTC. {len(rows)} documents. Folders and tags are "
        "your own (only you saw them).",
        "",
        "| Document | Folder | Tags | Created | Last edited | Archived |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    for doc, stem in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"[{cell(doc.title)}](<{stem}/{stem}.md>)",
                    cell(folders.get(doc.id, "")),
                    cell(", ".join(tags.get(doc.id, []))),
                    f"{doc.created_at:%Y-%m-%d}",
                    f"{doc.updated_at:%Y-%m-%d}",
                    f"{doc.archived_at:%Y-%m-%d}" if doc.archived_at else "",
                ]
            )
            + " |"
        )
    if missing:
        lines += [
            "",
            "## Attachments that could not be included",
            "",
            "Storage could not provide these files when the export was made. Export again later,"
            " or download them from the document's attachments panel.",
            "",
        ]
        lines += [f"- {cell(doc.title)}: {cell(name)}" for doc, name in missing]
    return "\n".join(lines) + "\n"


@router.get("/api/export")
def export_all(user: CurrentUser, db: DB, storage: OptionalStorage) -> StreamingResponse:
    """Every document the caller owns, archived included, as one ``.zip`` (DOC-033).

    Each document gets a folder with its Markdown and attachments; ``index.md`` lists them with
    the caller's own folder, tags and dates. Documents shared *with* the caller are not
    included: they belong to someone else.
    """
    docs = list(
        db.scalars(
            select(Document)
            .where(Document.owner_id == user.id)
            .order_by(Document.created_at, Document.id)
        )
    )
    ids = [d.id for d in docs]
    attachments = _attachments(db, ids)
    folder_ids, tags = organization_for(db, user, ids)
    folder_rows = db.execute(select(Folder.id, Folder.name).where(Folder.user_id == user.id))
    names: dict[int, str] = {row[0]: row[1] for row in folder_rows.all()}
    folders = {doc_id: names[f] for doc_id, f in folder_ids.items() if f in names}
    now = datetime.now(UTC)
    root = f"solara-docs-export-{now:%Y-%m-%d}"
    taken: set[str] = set()
    rows: list[tuple[Document, str]] = []
    missing: list[tuple[Document, str]] = []
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    try:
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
            for doc in docs:
                stem = unique(slug(doc.title), taken)
                rows.append((doc, stem))
                lost = _write_document(
                    archive,
                    f"{root}/{stem}/",
                    stem,
                    doc,
                    attachments[doc.id],
                    storage,
                    strict=False,
                )
                missing += [(doc, name) for name in lost]
            archive.writestr(f"{root}/index.md", _index(rows, folders, tags, now, missing))
    except BaseException:
        spool.close()
        raise
    response = _zip_response(spool, f"{root}.zip")
    # Lets the page warn that the archive is incomplete (the details are in index.md).
    response.headers["X-Export-Missing-Attachments"] = str(len(missing))
    return response
