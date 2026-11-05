"""identity schema: user email, OAuth identities, email allowlist, server-side sessions (ADR-009)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

tstz = sa.DateTime(timezone=True)


def upgrade() -> None:
    # OAuth users have no demo login key; existing demo rows keep theirs.
    op.alter_column("users", "login_key", existing_type=sa.String(64), nullable=True)
    op.add_column("users", sa.Column("email", sa.String(320), nullable=True))
    op.add_column("users", sa.Column("last_login_at", tstz, nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_check_constraint("ck_users_email_lower", "users", "email = lower(email)")

    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        # Stable provider account id (GitHub numeric id, Google `sub`) — never the email.
        sa.Column("provider_subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "provider", "provider_subject", name="uq_user_identities_provider_subject"
        ),
        sa.CheckConstraint("provider IN ('github', 'google')", name="ck_user_identities_provider"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    op.create_table(
        "allowed_emails",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("email = lower(email)", name="ck_allowed_emails_lower"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        # SHA-256 hex of the cookie token; the token itself is never stored.
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", tstz, nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", tstz, nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("allowed_emails")
    op.drop_table("user_identities")
    op.drop_constraint("ck_users_email_lower", "users", type_="check")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email")
    # Fails if OAuth-only users exist; delete or give them a login_key before downgrading.
    op.alter_column("users", "login_key", existing_type=sa.String(64), nullable=False)
