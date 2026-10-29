import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.observability import configure_logging, request_id_var
from app.routes import attachments, demo, documents, grants, health, imports

access_log = logging.getLogger("app.access")
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Document Workspace API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "If-Match", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        # Accept a caller's id only if it is short and safe to echo into logs and headers.
        rid = incoming if _SAFE_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        access_log.log(
            level,
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(documents.router)
    app.include_router(imports.router)
    app.include_router(attachments.router)
    app.include_router(grants.router)
    return app


app = create_app()
