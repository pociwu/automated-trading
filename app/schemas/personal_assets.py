from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PersonalAssetType(StrEnum):
    STOCK = "STOCK"
    GOLD = "GOLD"
    INSURANCE = "INSURANCE"
    TWD = "TWD"
    FX = "FX"
    CRYPTO = "CRYPTO"


class PersonalTransactionKind(StrEnum):
    OPENING = "OPENING"
    BUY = "BUY"
    SELL = "SELL"
    TRANSFER = "TRANSFER"
    EXTERNAL_IN = "EXTERNAL_IN"
    EXTERNAL_OUT = "EXTERNAL_OUT"
    PREMIUM = "PREMIUM"
    SURRENDER = "SURRENDER"
    REVERSAL = "REVERSAL"


class PersonalAssetAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    institution: str = Field(default="", max_length=80)
    asset_type: PersonalAssetType
    currency: str = Field(default="TWD", min_length=3, max_length=10)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class PersonalAssetAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    institution: str
    asset_type: str
    currency: str
    active: bool
    created_at: datetime


class PersonalAssetOpeningCreate(BaseModel):
    account_id: int
    asset_type: PersonalAssetType
    symbol: str = Field(min_length=1, max_length=40)
    name: str = Field(default="", max_length=100)
    quantity: Decimal = Field(gt=0)
    total_cost: Decimal = Field(ge=0)
    current_value: Decimal | None = Field(default=None, ge=0)
    valuation_date: date | None = None
    policy_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    policy_status: str | None = Field(default=None, max_length=20)
    occurred_at: datetime
    note: str = Field(default="", max_length=500)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class PersonalAssetTransactionCreate(BaseModel):
    kind: PersonalTransactionKind
    source_position_id: int | None = None
    target_position_id: int | None = None
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    gross_amount: Decimal = Field(default=Decimal("0"), ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    occurred_at: datetime
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_positions(self):
        if self.kind in {PersonalTransactionKind.BUY, PersonalTransactionKind.TRANSFER, PersonalTransactionKind.PREMIUM}:
            if self.source_position_id is None or self.target_position_id is None:
                raise ValueError("此異動必須指定來源與目標部位")
        elif self.kind in {PersonalTransactionKind.SELL, PersonalTransactionKind.SURRENDER}:
            if self.source_position_id is None or self.target_position_id is None:
                raise ValueError("此異動必須指定來源與入帳部位")
        elif self.kind == PersonalTransactionKind.EXTERNAL_IN and self.target_position_id is None:
            raise ValueError("外部存入必須指定目標部位")
        elif self.kind == PersonalTransactionKind.EXTERNAL_OUT and self.source_position_id is None:
            raise ValueError("外部支出必須指定來源部位")
        if self.kind in {
            PersonalTransactionKind.BUY,
            PersonalTransactionKind.SELL,
            PersonalTransactionKind.TRANSFER,
            PersonalTransactionKind.SURRENDER,
        } and self.quantity <= 0:
            raise ValueError("此異動的數量必須大於 0")
        if self.kind in {
            PersonalTransactionKind.BUY,
            PersonalTransactionKind.SELL,
            PersonalTransactionKind.EXTERNAL_IN,
            PersonalTransactionKind.EXTERNAL_OUT,
            PersonalTransactionKind.PREMIUM,
        } and self.gross_amount <= 0:
            raise ValueError("此異動的金額必須大於 0")
        return self


class PersonalAssetReversalCreate(BaseModel):
    occurred_at: datetime
    reason: str = Field(min_length=1, max_length=500)


class ManualPriceUpdate(BaseModel):
    price_twd: Decimal = Field(gt=0)
    quoted_at: datetime


class PersonalAssetPositionRead(BaseModel):
    id: int
    account_id: int
    account_name: str
    institution: str
    asset_type: str
    symbol: str
    name: str
    quantity: Decimal
    total_cost: Decimal
    average_cost: Decimal
    current_price_twd: Decimal | None
    current_value: Decimal
    unrealized_pnl: Decimal
    return_rate: Decimal
    price_source: str | None
    price_at: datetime | None
    acquired_at: datetime | None
    stale: bool
    valuation_date: date | None
    policy_last4: str | None
    policy_status: str | None


class PersonalAssetTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    source_position_id: int | None
    target_position_id: int | None
    quantity: Decimal
    gross_amount: Decimal
    fees: Decimal
    net_amount: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    occurred_at: datetime
    note: str
    reversal_of_id: int | None
    reversed_at: datetime | None


class PersonalAssetSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scheduled_at: datetime
    total_value: Decimal
    total_basis: Decimal
    stock_value: Decimal
    gold_value: Decimal
    insurance_value: Decimal
    twd_value: Decimal
    fx_value: Decimal
    crypto_value: Decimal
    stale: bool
    stale_detail: str


class PersonalAssetDashboardRead(BaseModel):
    total_value: Decimal
    total_basis: Decimal
    estimated_difference: Decimal
    stale_count: int
    positions: list[PersonalAssetPositionRead]
    snapshots: list[PersonalAssetSnapshotRead]
    has_backdated_changes: bool


class QuoteRefreshRead(BaseModel):
    updated: int
    stale_symbols: list[str]


class PersonalAssetOpeningReset(BaseModel):
    confirmation: Literal["清空期初資產"]


class PersonalAssetOpeningResetRead(BaseModel):
    deleted_positions: int
    deleted_transactions: int
    deleted_snapshots: int
