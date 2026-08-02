from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.entities import OrderStatus, TradeReason, TradeSide


class BuyRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=80)
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class SellRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class StrategySellRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    price: Decimal = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class StopPriceRequest(BaseModel):
    stop_price: Decimal | None = Field(default=None, gt=0)


class PriceUpdateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    close: Decimal = Field(gt=0)
    price_date: date = Field(default_factory=date.today)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class HoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    quantity: int
    average_cost: Decimal
    last_price: Decimal
    stop_price: Decimal | None
    sell_stage: int
    reserved_quantity: int
    available_quantity: int
    market_value: Decimal
    unrealized_pnl: Decimal
    return_rate: Decimal


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    side: TradeSide
    quantity: int
    price: Decimal
    amount: Decimal
    realized_pnl: Decimal | None
    reason: TradeReason
    stage: int | None
    traded_at: datetime


class DashboardRead(BaseModel):
    initial_capital: Decimal
    cash: Decimal
    reserved_cash: Decimal
    available_cash: Decimal
    holdings_cost: Decimal
    market_value: Decimal
    total_assets: Decimal
    total_pnl: Decimal
    return_rate: Decimal
    holdings: list[HoldingRead]


class PriceUpdateResult(BaseModel):
    symbol: str
    close: Decimal
    stopped_out: bool
    stop_trade: TradeRead | None = None


class MarketQuoteRead(BaseModel):
    symbol: str
    name: str
    close: Decimal
    price_date: date
    source: str


class LimitOrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=80)
    side: TradeSide
    quantity: int = Field(gt=0)
    limit_price: Decimal = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class LimitOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    side: TradeSide
    quantity: int
    limit_price: Decimal
    status: OrderStatus
    filled_price: Decimal | None
    trade_id: int | None
    placed_at: datetime
    filled_at: datetime | None
    cancelled_at: datetime | None


class MarketDataHealthRead(BaseModel):
    provider: str
    status: str
    connected: bool
    subscribed_symbols: int
    last_message_at: datetime | None
    last_tick_at: datetime | None
    stale: bool
    detail: str | None
