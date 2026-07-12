"""Add email verification and account recovery tokens.

Revision ID: 20260712_0005
Revises: 20260712_0004
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260712_0005"
down_revision: Union[str, None] = "20260712_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "email_verified_at" not in _column_names("users"):
        op.add_column(
            "users",
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.execute(
            "UPDATE users SET email_verified_at = COALESCE(created_at, CURRENT_TIMESTAMP)"
        )

    if not inspector.has_table("account_tokens"):
        op.create_table(
            "account_tokens",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("purpose", sa.String(length=40), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_account_tokens_user_id"),
            "account_tokens",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_account_tokens_purpose"),
            "account_tokens",
            ["purpose"],
            unique=False,
        )
        op.create_index(
            op.f("ix_account_tokens_token_hash"),
            "account_tokens",
            ["token_hash"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("account_tokens"):
        op.drop_index(
            op.f("ix_account_tokens_token_hash"), table_name="account_tokens"
        )
        op.drop_index(op.f("ix_account_tokens_purpose"), table_name="account_tokens")
        op.drop_index(op.f("ix_account_tokens_user_id"), table_name="account_tokens")
        op.drop_table("account_tokens")
    if "email_verified_at" in _column_names("users"):
        op.drop_column("users", "email_verified_at")
