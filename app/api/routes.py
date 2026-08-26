from datetime import UTC, datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import Holding, LimitOrder, OrderStatus, Trade, WatchlistItem
from app.schemas.trading import (
    BuyRequest,
    DashboardRead,
    IntradayQuoteRead,
    LimitOrderCreate,
    LimitOrderRead,
    MarketQuoteRead,
    MarketBuyRequest,
    MarketSellRequest,
    MarketStrategySellRequest,
    MarketDataHealthRead,
    PriceLimitsRead,
    PriceUpdateRequest,
    PriceUpdateResult,
    SellRequest,
    StopPriceRequest,
    StrategySellRequest,
    TradeRead,
    WatchlistCreate,
    WatchlistItemRead,
)
from app.schemas.personal_assets import (
    ManualPriceUpdate,
    PersonalAssetAccountCreate,
    PersonalAssetAccountRead,
    PersonalAssetDashboardRead,
    PersonalAssetOpeningCreate,
    PersonalAssetOpeningReset,
    PersonalAssetOpeningResetRead,
    PersonalAssetPositionRead,
    PersonalAssetReversalCreate,
    PersonalAssetSnapshotRead,
    PersonalAssetTransactionCreate,
    PersonalAssetTransactionRead,
    QuoteRefreshRead,
)
from app.services.market_data import (
    FugleIntradayMarketDataProvider,
    MarketDataError,
    TwseMarketDataProvider,
)
from app.services.market_data_health import MarketDataHealthService
from app.services.limit_order_placement import LimitOrderPlacementService
from app.services.market_orders import MarketOrderService
from app.services.orders import OrderService
from app.services.trading import TradingService
from app.services.watchlist import WatchlistService
from app.services.personal_assets import PersonalAssetService
from app.services.personal_asset_valuation import PersonalAssetValuationService


router = APIRouter(prefix="/api/v1")


@lru_cache(maxsize=1)
def get_intraday_market_data_provider() -> FugleIntradayMarketDataProvider:
    return FugleIntradayMarketDataProvider()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/personal-assets/accounts", response_model=list[PersonalAssetAccountRead])
def personal_asset_accounts(db: Session = Depends(get_db)):
    return PersonalAssetService(db).accounts()


@router.post("/personal-assets/accounts", response_model=PersonalAssetAccountRead, status_code=201)
def create_personal_asset_account(payload: PersonalAssetAccountCreate, db: Session = Depends(get_db)):
    return PersonalAssetService(db).create_account(payload)


@router.post("/personal-assets/opening", response_model=PersonalAssetPositionRead, status_code=201)
def create_personal_asset_opening(payload: PersonalAssetOpeningCreate, db: Session = Depends(get_db)):
    position = PersonalAssetService(db).opening(payload)
    return next(row for row in PersonalAssetValuationService(db).position_reads() if row.id == position.id)


@router.post("/personal-assets/opening/reset", response_model=PersonalAssetOpeningResetRead)
def reset_personal_asset_opening(
    payload: PersonalAssetOpeningReset,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    del payload
    return PersonalAssetService(db).reset_opening_assets()


@router.get("/personal-assets/dashboard", response_model=PersonalAssetDashboardRead)
def personal_asset_dashboard(
    days: int = Query(default=30, ge=0, le=3650),
    db: Session = Depends(get_db),
):
    return PersonalAssetValuationService(db).dashboard(None if days == 0 else days)


@router.post("/personal-assets/quotes/refresh", response_model=QuoteRefreshRead)
def refresh_personal_asset_quotes(db: Session = Depends(get_db)) -> QuoteRefreshRead:
    updated, stale = PersonalAssetValuationService(db).refresh()
    return QuoteRefreshRead(updated=updated, stale_symbols=stale)


@router.patch("/personal-assets/positions/{position_id}/price", response_model=PersonalAssetPositionRead)
def update_personal_asset_manual_price(
    position_id: int,
    payload: ManualPriceUpdate,
    db: Session = Depends(get_db),
):
    service = PersonalAssetValuationService(db)
    try:
        position = service.set_manual_price(position_id, payload.price_twd, payload.quoted_at)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="找不到資產部位") from exc
    return next(row for row in service.position_reads() if row.id == position.id)


@router.get("/personal-assets/transactions", response_model=list[PersonalAssetTransactionRead])
def personal_asset_transactions(
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return PersonalAssetService(db).transactions(limit)


@router.post("/personal-assets/transactions", response_model=PersonalAssetTransactionRead, status_code=201)
def create_personal_asset_transaction(payload: PersonalAssetTransactionCreate, db: Session = Depends(get_db)):
    return PersonalAssetService(db).transact(payload)


@router.post("/personal-assets/transactions/{transaction_id}/reverse", response_model=PersonalAssetTransactionRead, status_code=201)
def reverse_personal_asset_transaction(
    transaction_id: int,
    payload: PersonalAssetReversalCreate,
    db: Session = Depends(get_db),
):
    return PersonalAssetService(db).reverse(transaction_id, payload.occurred_at, payload.reason)


@router.post("/personal-assets/snapshots", response_model=PersonalAssetSnapshotRead, status_code=201)
def create_personal_asset_snapshot(db: Session = Depends(get_db)):
    return PersonalAssetValuationService(db).create_snapshot(datetime.now(UTC).replace(second=0, microsecond=0))


@router.get("/watchlist", response_model=list[WatchlistItemRead])
def watchlist(db: Session = Depends(get_db)) -> list[WatchlistItem]:
    return WatchlistService(db).list_items()


@router.post("/watchlist", response_model=WatchlistItemRead, status_code=201)
def add_watchlist_item(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> WatchlistItem:
    try:
        quote = provider.get_quote(payload.symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if quote.symbol != payload.symbol:
        raise HTTPException(status_code=502, detail="行情股票代號不符")
    return WatchlistService(db).add(quote.symbol, quote.name)


@router.delete("/watchlist/{symbol}", status_code=204)
def remove_watchlist_item(symbol: str, db: Session = Depends(get_db)) -> None:
    WatchlistService(db).remove(symbol)


@router.get("/health/market-data", response_model=MarketDataHealthRead)
def market_data_health(db: Session = Depends(get_db)) -> MarketDataHealthRead:
    return MarketDataHealthService(db).read()


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db)) -> DashboardRead:
    return TradingService(db).dashboard()


@router.post("/trades/buy", response_model=TradeRead, status_code=201)
def buy(payload: BuyRequest, db: Session = Depends(get_db)) -> Trade:
    return TradingService(db).buy(payload)


@router.post("/trades/buy-market", response_model=TradeRead, status_code=201)
def buy_market(
    payload: MarketBuyRequest,
    db: Session = Depends(get_db),
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> Trade:
    try:
        return MarketOrderService(db, provider).buy(payload)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/trades/sell", response_model=TradeRead, status_code=201)
def sell(payload: SellRequest, db: Session = Depends(get_db)) -> Trade:
    return TradingService(db).sell(payload)


@router.post("/trades/sell-market", response_model=TradeRead, status_code=201)
def sell_market(
    payload: MarketSellRequest,
    db: Session = Depends(get_db),
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> Trade:
    try:
        return MarketOrderService(db, provider).sell(payload)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/trades/sell-424", response_model=TradeRead, status_code=201)
def sell_424(payload: StrategySellRequest, db: Session = Depends(get_db)) -> Trade:
    return TradingService(db).sell_next_424_stage(payload)


@router.post("/trades/sell-424-market", response_model=TradeRead, status_code=201)
def sell_424_market(
    payload: MarketStrategySellRequest,
    db: Session = Depends(get_db),
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> Trade:
    try:
        return MarketOrderService(db, provider).sell_next_424_stage(payload)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/orders", response_model=LimitOrderRead, status_code=201)
def place_order(
    payload: LimitOrderCreate,
    db: Session = Depends(get_db),
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> LimitOrder:
    try:
        return LimitOrderPlacementService(db, provider).place(payload)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/orders", response_model=list[LimitOrderRead])
def orders(
    status: OrderStatus | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[LimitOrder]:
    return OrderService(db).list_orders(status=status, limit=limit)


@router.delete("/orders/{order_id}", response_model=LimitOrderRead)
def cancel_order(order_id: int, db: Session = Depends(get_db)) -> LimitOrder:
    return OrderService(db).cancel(order_id)


@router.get("/trades", response_model=list[TradeRead])
def trades(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[Trade]:
    account = TradingService(db).account()
    return list(
        db.scalars(
            select(Trade)
            .where(Trade.account_id == account.id)
            .order_by(Trade.traded_at.desc(), Trade.id.desc())
            .limit(limit)
        ).all()
    )


@router.patch("/holdings/{symbol}/stop")
def set_stop(symbol: str, payload: StopPriceRequest, db: Session = Depends(get_db)) -> dict[str, str | float | None]:
    account = TradingService(db).account()
    holding = db.scalar(
        select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol.strip().upper())
    )
    if holding is None:
        raise HTTPException(status_code=404, detail="找不到持股")
    holding.stop_price = payload.stop_price
    db.commit()
    return {"symbol": holding.symbol, "stop_price": float(holding.stop_price) if holding.stop_price else None}


@router.post("/prices/close", response_model=PriceUpdateResult)
def update_close(payload: PriceUpdateRequest, db: Session = Depends(get_db)) -> PriceUpdateResult:
    return TradingService(db).update_price(payload)


@router.get("/market-data/{symbol}", response_model=MarketQuoteRead)
def market_quote(symbol: str) -> MarketQuoteRead:
    try:
        return TwseMarketDataProvider().get_close(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market-data/intraday/{symbol}", response_model=IntradayQuoteRead)
def intraday_market_quote(
    symbol: str,
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> IntradayQuoteRead:
    try:
        return provider.get_quote(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market-data/intraday/{symbol}/limits", response_model=PriceLimitsRead)
def intraday_price_limits(
    symbol: str,
    provider: FugleIntradayMarketDataProvider = Depends(get_intraday_market_data_provider),
) -> PriceLimitsRead:
    try:
        return provider.get_price_limits(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/prices/sync/{symbol}", response_model=PriceUpdateResult)
def sync_close(symbol: str, db: Session = Depends(get_db)) -> PriceUpdateResult:
    try:
        quote = TwseMarketDataProvider().get_close(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TradingService(db).update_price(
        PriceUpdateRequest(symbol=quote.symbol, close=quote.close, price_date=quote.price_date)
    )
