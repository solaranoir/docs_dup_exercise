"""personal folders and tags (DOC-016, DOC-018; ADR-010)

Revision ID: 0005
Revises: 0003
Create Date: 2026-11-04

Additive only: existing documents start unfiled and untagged. Numbered 0005 so the search
migration (0004, DOC-017) can land first or second; whichever merges second points its
down_revision at the other.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0003"
branch_labels = None
depends_on = None

tstz = sa.DateTime(timezone=True)


def _user_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


def _document_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "document_id",
        sa.Uuid,
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 60", name="ck_folders_name_len"),
    )
    op.create_index(
        "uq_folders_user_name", "folders", ["user_id", sa.text("lower(name)")], unique=True
    )
    op.create_table(
        "document_folders",
        _user_fk(),
        _document_fk(),
        sa.Column(
            "folder_id",
            sa.Integer,
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    op.create_table(
        "document_tags",
        _user_fk(),
        _document_fk(),
        sa.Column("tag", sa.String(32), primary_key=True),
        sa.CheckConstraint(
            "tag = lower(tag) AND length(tag) BETWEEN 1 AND 32", name="ck_document_tags_tag"
        ),
    )
    op.create_index("ix_document_tags_document_id", "document_tags", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_tags_document_id", table_name="document_tags")
    op.drop_table("document_tags")
    op.drop_table("document_folders")
    op.drop_index("uq_folders_user_name", table_name="folders")
    op.drop_table("folders")
