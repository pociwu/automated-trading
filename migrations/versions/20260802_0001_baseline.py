"""Create the paper-trading baseline schema."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260802_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

trade_side = postgresql.ENUM("BUY", "SELL", name="tradeside", create_type=False)
trade_reason = postgresql.ENUM(
    "MANUAL_BUY",
    "MANUAL_SELL",
    "STRATEGY_424",
    "S_POINT_STOP",
    "LIMIT_ORDER",
    name="tradereason",
    create_type=False,
)
order_status = postgresql.ENUM(
    "PENDING", "FILLED", "CANCELLED", name="orderstatus", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    trade_side.create(bind, checkfirst=True)
    trade_reason.create(bind, checkfirst=True)
    order_status.create(bind, checkfirst=True)
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("initial_capital", sa.Numeric(16, 2), nullable=False),
        sa.Column("cash", sa.Numeric(16, 2), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(16, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_cost", sa.Numeric(14, 4), nullable=False),
        sa.Column("last_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("stop_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("sell_stage", sa.Integer(), nullable=False),
        sa.Column("strategy_base_quantity", sa.Integer(), nullable=True),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "symbol"),
    )
    op.create_index(op.f("ix_holdings_symbol"), "holdings", ["symbol"])
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("close", sa.Numeric(14, 4), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("symbol", "price_date"),
    )
    op.create_index(op.f("ix_price_history_price_date"), "price_history", ["price_date"])
    op.create_index(op.f("ix_price_history_symbol"), "price_history", ["symbol"])
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("side", trade_side, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(16, 2), nullable=True),
        sa.Column("reason", trade_reason, nullable=False),
        sa.Column("stage", sa.Integer(), nullable=True),
        sa.Column("traded_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_trades_account_id"), "trades", ["account_id"])
    op.create_index(op.f("ix_trades_symbol"), "trades", ["symbol"])
    op.create_index(op.f("ix_trades_traded_at"), "trades", ["traded_at"])
    op.create_table(
        "limit_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("side", trade_side, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("filled_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("placed_at", sa.DateTime(), nullable=False),
        sa.Column("filled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_limit_orders_account_id"), "limit_orders", ["account_id"])
    op.create_index(op.f("ix_limit_orders_placed_at"), "limit_orders", ["placed_at"])
    op.create_index(op.f("ix_limit_orders_status"), "limit_orders", ["status"])
    op.create_index(op.f("ix_limit_orders_symbol"), "limit_orders", ["symbol"])
    op.create_table(
        "market_data_status",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("subscribed_symbols", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("last_tick_at", sa.DateTime(), nullable=True),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_data_status")
    op.drop_table("limit_orders")
    op.drop_table("trades")
    op.drop_table("price_history")
    op.drop_table("holdings")
    op.drop_table("accounts")
    bind = op.get_bind()
    order_status.drop(bind, checkfirst=True)
    trade_reason.drop(bind, checkfirst=True)
    trade_side.drop(bind, checkfirst=True)
