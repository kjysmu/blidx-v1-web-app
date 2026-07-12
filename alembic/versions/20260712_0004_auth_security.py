"""Add account security and session revocation fields.

Revision ID: 20260712_0004
Revises: 20260711_0003
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260712_0004"
down_revision: Union[str, None] = "20260711_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("users")}


def upgrade() -> None:
    existing = _column_names()
    columns = (
        sa.Column(
            "session_version", sa.Integer(), server_default="1", nullable=False
        ),
        sa.Column(
            "failed_login_attempts", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("users", column)


def downgrade() -> None:
    existing = _column_names()
    for name in (
        "last_login_at",
        "password_changed_at",
        "locked_until",
        "failed_login_attempts",
        "session_version",
    ):
        if name in existing:
            op.drop_column("users", name)
