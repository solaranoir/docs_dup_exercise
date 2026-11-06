"""Trash with 30-day recovery (DOC-031, ADR-012)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05

Additive only: existing documents start outside the Trash. The partial index keeps the purge
query and the Trash listing cheap without touching the (much larger) set of live documents.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_documents_deleted_at",
        "documents",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_column("documents", "deleted_at")
