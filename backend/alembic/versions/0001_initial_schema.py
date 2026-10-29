"""initial schema: users, documents, document_grants, attachments

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

json_content = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
tstz = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("login_key", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content_json", json_content, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(title) BETWEEN 1 AND 160", name="ck_documents_title_len"),
        sa.CheckConstraint("revision >= 1", name="ck_documents_revision_positive"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_table(
        "document_grants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grantee_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column("granted_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "grantee_id", name="uq_document_grants_doc_grantee"),
        sa.CheckConstraint("role IN ('viewer', 'editor')", name="ck_document_grants_role"),
    )
    op.create_index("ix_document_grants_document_id", "document_grants", ["document_id"])
    op.create_index("ix_document_grants_grantee_id", "document_grants", ["grantee_id"])
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("size_bytes >= 0", name="ck_attachments_size"),
    )
    op.create_index("ix_attachments_document_id", "attachments", ["document_id"])


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_table("document_grants")
    op.drop_table("documents")
    op.drop_table("users")
