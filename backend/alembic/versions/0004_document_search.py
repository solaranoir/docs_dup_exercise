"""document search: plain-text column, PostgreSQL full-text vector and GIN index (DOC-017)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04

Additive only. ``search_text`` is backfilled from each row's content_json in Python, with the
same extraction the application runs on every write; ``updated_at`` and ``revision`` are left
alone. On PostgreSQL ``search_vector`` is a generated column, so it cannot drift from
title/search_text.
"""

import sqlalchemy as sa
from alembic import op

from app.content import plain_text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# 'simple': no stemming or stop words. Notes are full of callsigns, grid squares, park
# references and frequencies that English stemming would mangle; prefix queries cover plurals.
# Hyphens, dots and slashes split words ("K-43" -> "k 43"); app/search.py does the same to
# queries. Title words weigh more than body words in ranking.
SEARCH_VECTOR = (
    "setweight(to_tsvector('simple'::regconfig, translate(title, '-./', '   ')), 'A') || "
    "setweight(to_tsvector('simple'::regconfig, translate(search_text, '-./', '   ')), 'B')"
)
BATCH = 200


def upgrade() -> None:
    op.add_column("documents", sa.Column("search_text", sa.Text, nullable=False, server_default=""))
    _backfill()
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE documents ADD COLUMN search_vector tsvector "
            f"GENERATED ALWAYS AS ({SEARCH_VECTOR}) STORED"
        )
        op.create_index(
            "ix_documents_search_vector", "documents", ["search_vector"], postgresql_using="gin"
        )


def _backfill() -> None:
    conn = op.get_bind()
    docs = sa.table(
        "documents",
        sa.column("id", sa.Uuid),
        sa.column("content_json", sa.JSON),
        sa.column("search_text", sa.Text),
    )
    last = None
    while True:
        query = sa.select(docs.c.id, docs.c.content_json).order_by(docs.c.id).limit(BATCH)
        if last is not None:
            query = query.where(docs.c.id > last)
        rows = conn.execute(query).all()
        if not rows:
            return
        for doc_id, content in rows:
            conn.execute(
                docs.update().where(docs.c.id == doc_id).values(search_text=plain_text(content))
            )
        last = rows[-1][0]


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_documents_search_vector", table_name="documents")
        op.drop_column("documents", "search_vector")
    op.drop_column("documents", "search_text")
