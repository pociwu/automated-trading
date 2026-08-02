from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.entities import Holding, TradeReason
from app.schemas.trading import BuyRequest, PriceUpdateRequest, SellRequest, StrategySellRequest
from app.services.trading import TradingService


def test_buy_updates_cash_and_holding(db):
    service = TradingService(db)
    trade = service.buy(BuyRequest(symbol="2330", name="台積電", quantity=1000, price=100, stop_price=90))

    dashboard = service.dashboard()
    assert trade.amount == Decimal("100000.00")
    assert dashboard.cash == Decimal("1900000.00")
    assert dashboard.market_value == Decimal("100000.00")
    assert dashboard.holdings[0].stop_price == Decimal("90.0000")


def test_buy_is_not_limited_by_424(db):
    service = TradingService(db)
    trade = service.buy(BuyRequest(symbol="2330", quantity=10_000, price=100))
    assert trade.amount == Decimal("1000000.00")


def test_424_sells_40_20_then_remaining_40_percent(db):
    service = TradingService(db)
    service.buy(BuyRequest(symbol="2330", quantity=10, price=100))

    first = service.sell_next_424_stage(StrategySellRequest(symbol="2330", price=110))
    second = service.sell_next_424_stage(StrategySellRequest(symbol="2330", price=120))
    third = service.sell_next_424_stage(StrategySellRequest(symbol="2330", price=130))

    assert [first.quantity, second.quantity, third.quantity] == [4, 2, 4]
    assert [first.stage, second.stage, third.stage] == [1, 2, 3]
    assert all(trade.reason == TradeReason.STRATEGY_424 for trade in (first, second, third))
    assert db.scalar(select(Holding).where(Holding.symbol == "2330")) is None


def test_close_at_s_point_sells_entire_position(db):
    service = TradingService(db)
    service.buy(BuyRequest(symbol="2330", name="台積電", quantity=1000, price=100, stop_price=90))

    result = service.update_price(PriceUpdateRequest(symbol="2330", close=89, price_date=date(2026, 8, 1)))

    assert result.stopped_out is True
    assert result.stop_trade is not None
    assert result.stop_trade.reason == TradeReason.S_POINT_STOP
    assert db.scalar(select(Holding).where(Holding.symbol == "2330")) is None
    assert service.dashboard().cash == Decimal("1989000.00")


def test_manual_partial_sell_keeps_remaining_position(db):
    service = TradingService(db)
    service.buy(BuyRequest(symbol="AAPL", quantity=10, price=100))
    trade = service.sell(SellRequest(symbol="AAPL", quantity=4, price=110))

    assert trade.realized_pnl == Decimal("40.00")
    assert service.dashboard().holdings[0].quantity == 6

