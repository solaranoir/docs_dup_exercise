import uuid
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import CurrentUser
from app.config import Settings, get_settings
from app.imports import ConversionError, convert
from app.ratelimit import limit_uploads
from app.routes.documents import DB, DocumentOut, apply_update, document_out, load_editable
from app.uploads import read_upload

router = APIRouter(prefix="/api", tags=["imports"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


class ImportPreview(BaseModel):
    title: str
    content_json: dict[str, Any]
    warnings: list[str]
    source_name: str
    source_type: str


class ImportApplied(BaseModel):
    document: DocumentOut
    warnings: list[str]


async def _convert(file: UploadFile, settings: Settings) -> tuple[str, dict[str, Any], list[str]]:
    upload = await read_upload(file, settings.max_upload_bytes)
    try:
        result = convert(upload)
    except ConversionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    return upload.name, result.content, result.warnings


@router.post("/imports", dependencies=[Depends(limit_uploads)])
async def preview_import(
    _user: CurrentUser, settings: SettingsDep, file: Annotated[UploadFile, File()]
) -> ImportPreview:
    """Convert an upload into an editable draft. Nothing is stored until the user creates it."""
    name, content, warnings = await _convert(file, settings)
    title = PurePosixPath(name).stem.strip()[:160] or "Imported document"
    return ImportPreview(
        title=title,
        content_json=content,
        warnings=warnings,
        source_name=name,
        source_type=PurePosixPath(name).suffix.lstrip(".").lower(),
    )


@router.post("/documents/{doc_id}/imports", dependencies=[Depends(limit_uploads)])
async def import_into_document(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    mode: Annotated[Literal["append", "replace"], Form()],
    expected_revision: Annotated[int, Form(ge=1)],
) -> ImportApplied:
    doc, permission = load_editable(db, user, doc_id)
    _name, content, warnings = await _convert(file, settings)
    if mode == "append":
        existing = [n for n in doc.content_json.get("content", []) if n != {"type": "paragraph"}]
        content = {"type": "doc", "content": existing + content["content"]}
    apply_update(db, doc, expected_revision, {"content_json": content})
    return ImportApplied(document=document_out(db, doc, permission), warnings=warnings)
