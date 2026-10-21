"""Create the initial guest, check-in and point transaction tables."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("token_nonce", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("token_nonce"),
    )
    op.create_index("ix_guests_telegram_id", "guests", ["telegram_id"], unique=False)
    op.create_table(
        "check_ins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_id", sa.String(length=36), nullable=False),
        sa.Column("organizer_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_id"),
    )
    op.create_table(
        "point_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_id", sa.String(length=36), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("checkin_key", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_id", "kind", "checkin_key", name="uq_checkin_transaction"),
    )
    op.create_index("ix_point_transactions_guest_id", "point_transactions", ["guest_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_point_transactions_guest_id", table_name="point_transactions")
    op.drop_table("point_transactions")
    op.drop_table("check_ins")
    op.drop_index("ix_guests_telegram_id", table_name="guests")
    op.drop_table("guests")
