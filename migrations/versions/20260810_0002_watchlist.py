"""Add persistent watchlist items."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_0002"
down_revision: str | None = "20260802_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "symbol"),
    )
    op.create_index(op.f("ix_watchlist_items_account_id"), "watchlist_items", ["account_id"])
    op.create_index(op.f("ix_watchlist_items_symbol"), "watchlist_items", ["symbol"])


def downgrade() -> None:
    op.drop_table("watchlist_items")
