"""Built-in templates for the "New document" picker (DOC-023..026, ADR-011)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth import CurrentUser
from app.templates import TEMPLATES

router = APIRouter(prefix="/api/templates", tags=["templates"])


class SectionOut(BaseModel):
    heading: str
    fields: list[str]


class TemplateOut(BaseModel):
    id: str
    version: int
    name: str
    description: str
    sections: list[SectionOut]


@router.get("")
def list_templates(_user: CurrentUser) -> list[TemplateOut]:
    """Names, descriptions and an outline for previews; the content itself stays server-side."""
    return [
        TemplateOut(
            id=t.id,
            version=t.version,
            name=t.name,
            description=t.description,
            sections=[SectionOut(heading=s.heading, fields=list(s.fields)) for s in t.sections],
        )
        for t in TEMPLATES
    ]
