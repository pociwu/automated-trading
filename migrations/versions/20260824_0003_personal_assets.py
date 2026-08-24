"""Add personal asset ledger and valuation snapshots."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0003"
down_revision: str | None = "20260810_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_asset_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("institution", sa.String(80), nullable=False),
        sa.Column("asset_type", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_personal_asset_accounts_asset_type"), "personal_asset_accounts", ["asset_type"])
    op.create_table(
        "personal_asset_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("personal_asset_accounts.id"), nullable=False),
        sa.Column("asset_type", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("current_price_twd", sa.Numeric(18, 8), nullable=True),
        sa.Column("price_source", sa.String(80), nullable=True),
        sa.Column("price_at", sa.DateTime(), nullable=True),
        sa.Column("manual_price", sa.Boolean(), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=True),
        sa.Column("policy_last4", sa.String(4), nullable=True),
        sa.Column("policy_status", sa.String(20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "asset_type", "symbol"),
    )
    op.create_index(op.f("ix_personal_asset_positions_account_id"), "personal_asset_positions", ["account_id"])
    op.create_index(op.f("ix_personal_asset_positions_asset_type"), "personal_asset_positions", ["asset_type"])
    op.create_index(op.f("ix_personal_asset_positions_symbol"), "personal_asset_positions", ["symbol"])
    op.create_table(
        "personal_asset_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source_position_id", sa.Integer(), sa.ForeignKey("personal_asset_positions.id"), nullable=True),
        sa.Column("target_position_id", sa.Integer(), sa.ForeignKey("personal_asset_positions.id"), nullable=True),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fees", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 2), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("reversal_of_id", sa.Integer(), sa.ForeignKey("personal_asset_transactions.id"), nullable=True, unique=True),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_personal_asset_transactions_kind"), "personal_asset_transactions", ["kind"])
    op.create_index(op.f("ix_personal_asset_transactions_occurred_at"), "personal_asset_transactions", ["occurred_at"])
    op.create_table(
        "personal_asset_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False, unique=True),
        sa.Column("total_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_basis", sa.Numeric(18, 2), nullable=False),
        sa.Column("stock_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("gold_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("insurance_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("twd_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("fx_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("crypto_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("stale_detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        op.f("ix_personal_asset_snapshots_scheduled_at"),
        "personal_asset_snapshots",
        ["scheduled_at"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("personal_asset_snapshots")
    op.drop_table("personal_asset_transactions")
    op.drop_table("personal_asset_positions")
    op.drop_table("personal_asset_accounts")
