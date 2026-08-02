from datetime import UTC, datetime
from decimal import Decimal

from app.schemas.trading import (
    BuyRequest,
    IntradayQuoteRead,
    MarketBuyRequest,
    MarketSellRequest,
    MarketStrategySellRequest,
)
from app.services.market_orders import MarketOrderService
from app.services.trading import TradingService


class FakeIntradayProvider:
    def __init__(self, price: str) -> None:
        self.price = Decimal(price)

    def get_quote(self, symbol: str) -> IntradayQuoteRead:
        return IntradayQuoteRead(
            symbol=symbol,
            name="台積電",
            price=self.price,
            bid=self.price - 1,
            ask=self.price + 1,
            quoted_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
            source="test",
        )


def test_market_buy_uses_server_side_latest_price(db):
    trade = MarketOrderService(db, FakeIntradayProvider("1025")).buy(
        MarketBuyRequest(symbol="2330", quantity=10, stop_price=900)
    )

    assert trade.price == Decimal("1025.0000")
    assert trade.name == "台積電"
    assert TradingService(db).dashboard().cash == Decimal("1989750.00")


def test_market_sell_uses_server_side_latest_price(db):
    TradingService(db).buy(BuyRequest(symbol="2330", quantity=10, price=1000))

    trade = MarketOrderService(db, FakeIntradayProvider("1030")).sell(
        MarketSellRequest(symbol="2330", quantity=4)
    )

    assert trade.price == Decimal("1030.0000")
    assert trade.realized_pnl == Decimal("120.00")


def test_market_424_sell_uses_server_side_latest_price(db):
    TradingService(db).buy(BuyRequest(symbol="2330", quantity=10, price=1000))

    trade = MarketOrderService(db, FakeIntradayProvider("1040")).sell_next_424_stage(
        MarketStrategySellRequest(symbol="2330")
    )

    assert trade.price == Decimal("1040.0000")
    assert trade.quantity == 4
    assert trade.stage == 1
