from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeReason(str, Enum):
    MANUAL_BUY = "MANUAL_BUY"
    MANUAL_SELL = "MANUAL_SELL"
    STRATEGY_424 = "STRATEGY_424"
    S_POINT_STOP = "S_POINT_STOP"
    LIMIT_ORDER = "LIMIT_ORDER"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, default="main")
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    cash: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    holdings: Mapped[list["Holding"]] = relationship(back_populates="account")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[int] = mapped_column(Integer)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    last_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    sell_stage: Mapped[int] = mapped_column(Integer, default=0)
    strategy_base_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    account: Mapped[Account] = relationship(back_populates="holdings")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    side: Mapped[TradeSide] = mapped_column(SqlEnum(TradeSide))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    reason: Mapped[TradeReason] = mapped_column(SqlEnum(TradeReason))
    stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("symbol", "price_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    price_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LimitOrder(Base):
    __tablename__ = "limit_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    side: Mapped[TradeSide] = mapped_column(SqlEnum(TradeSide))
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    status: Mapped[OrderStatus] = mapped_column(SqlEnum(OrderStatus), default=OrderStatus.PENDING, index=True)
    filled_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MarketDataStatus(Base):
    __tablename__ = "market_data_status"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    connected: Mapped[bool]
    subscribed_symbols: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
