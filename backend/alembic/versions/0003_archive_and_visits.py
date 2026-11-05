"""archive/restore and per-user recently opened documents (DOC-021, DOC-022)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04

Additive only: existing documents start unarchived with no visit history.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

tstz = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("documents", sa.Column("archived_at", tstz, nullable=True))
    op.create_table(
        "document_visits",
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("last_opened_at", tstz, nullable=False),
    )
    op.create_index("ix_document_visits_document_id", "document_visits", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_visits_document_id", table_name="document_visits")
    op.drop_table("document_visits")
    op.drop_column("documents", "archived_at")
