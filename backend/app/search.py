"""Title and body search over the documents a user can read (DOC-017).

PostgreSQL matches against the generated ``documents.search_vector`` (migration 0004) with the
'simple' configuration: no stemming or stop words, so callsigns, grid squares, park references
and frequencies are indexed as written. Hyphens, dots and slashes become spaces on both sides,
so "K-43" is the words "k 43" and searching "43", "K-4" or "AO-9" finds it. Each query word is
a prefix match ("ante" finds "antenna"); all words must match, in the title or the body.
Other dialects (local experiments only) fall back to case-insensitive substring matching.
"""

import re
from typing import Any

from sqlalchemy import ColumnElement, and_, bindparam, func, literal_column, or_, true

from app.models import Document

MAX_QUERY_LENGTH = 200
MAX_TERMS = 10
SNIPPET_BEFORE = 40
SNIPPET_LENGTH = 160

# Must match the translate() in migration 0004's search_vector.
SEPARATORS = "-./"
_SPLIT = str.maketrans(SEPARATORS, " " * len(SEPARATORS))
SEARCH_VECTOR: ColumnElement[Any] = literal_column("documents.search_vector")


def query_terms(q: str) -> list[str]:
    """Whitespace-separated words that contain something searchable, at most MAX_TERMS."""
    return [t for t in q.split() if any(c.isalnum() for c in t)][:MAX_TERMS]


def _quote(lexeme: str) -> str:
    # Inside single quotes tsquery syntax characters are literal; only ' and \ need escaping.
    return "'" + lexeme.replace("\\", "\\\\").replace("'", "''") + "'"


def tsquery_text(terms: list[str]) -> str:
    """to_tsquery input: words ANDed; a hyphenated word is a phrase, its last part a prefix."""
    clauses = []
    for term in terms:
        parts = [p for p in term.translate(_SPLIT).split() if any(c.isalnum() for c in p)]
        if parts:
            quoted = [_quote(p) for p in parts]
            quoted[-1] += ":*"
            clauses.append("(" + " <-> ".join(quoted) + ")")
    return " & ".join(clauses)


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def match_and_rank(dialect: str, terms: list[str]) -> tuple[ColumnElement[bool], list[Any]]:
    """WHERE clause and ORDER BY terms (best first) for the given dialect."""
    if dialect == "postgresql":
        tsquery = func.to_tsquery(
            literal_column("'simple'::regconfig"), bindparam("tsq", tsquery_text(terms))
        )
        return SEARCH_VECTOR.op("@@")(tsquery), [
            func.ts_rank(SEARCH_VECTOR, tsquery).desc(),
            Document.updated_at.desc(),
        ]
    clauses = [
        or_(
            Document.title.ilike(_like_pattern(t), escape="\\"),
            Document.search_text.ilike(_like_pattern(t), escape="\\"),
        )
        for t in terms
    ]
    return and_(true(), *clauses), [Document.updated_at.desc()]


def snippet(text: str, terms: list[str]) -> str | None:
    """A short plain-text excerpt around the first match in the body, or its opening."""
    flat = " ".join(text.split())
    if not flat:
        return None
    needles = {p for t in terms for p in [t, *t.translate(_SPLIT).split()] if p}
    found = [m.start() for n in needles if (m := re.search(re.escape(n), flat, re.IGNORECASE))]
    start = max(0, min(found) - SNIPPET_BEFORE) if found else 0
    if start:
        space = flat.find(" ", start)
        start = space + 1 if 0 <= space < start + 15 else start
    end = min(len(flat), start + SNIPPET_LENGTH)
    if end < len(flat):
        space = flat.rfind(" ", start, end)
        end = space if space > start + SNIPPET_LENGTH // 2 else end
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")
