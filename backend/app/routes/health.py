import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.storage import Storage, StorageError, optional_storage

router = APIRouter(prefix="/health", tags=["health"])
log = logging.getLogger(__name__)


@router.get("/live")
def live(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str | None]:
    return {"status": "ok", "commit": settings.git_commit}


@router.get("/ready")
def ready(
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[Storage | None, Depends(optional_storage)],
) -> JSONResponse:
    # Storage problems are reported but don't fail readiness: documents still work without
    # attachments, and a failing health check would make Render restart a healthy API.
    storage_status = "unconfigured"
    if storage is not None:
        try:
            storage.check()
            storage_status = "ok"
        except StorageError:
            log.exception("readiness: storage check failed")
            storage_status = "error"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("readiness: database check failed")
        return JSONResponse(
            {"status": "unavailable", "database": "error", "storage": storage_status},
            status_code=503,
        )
    return JSONResponse({"status": "ok", "database": "ok", "storage": storage_status})
