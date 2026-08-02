from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.entities import LimitOrder, OrderStatus, TradeReason
from app.schemas.trading import BuyRequest, LimitOrderCreate, SellRequest
from app.services.orders import OrderService
from app.services.trading import TradingService


def test_buy_limit_order_reserves_cash_and_fills_at_limit(db):
    orders = OrderService(db)
    order = orders.place(
        LimitOrderCreate(symbol="2330", name="台積電", side="BUY", quantity=10, limit_price=100)
    )

    assert TradingService(db).dashboard().reserved_cash == Decimal("1000.00")
    assert orders.process_tick("2330", Decimal("101")) == []

    trades = orders.process_tick("2330", Decimal("99"))
    db.refresh(order)
    assert order.status == OrderStatus.FILLED
    assert trades[0].price == Decimal("100.0000")
    assert trades[0].reason == TradeReason.LIMIT_ORDER
    assert TradingService(db).dashboard().available_cash == Decimal("1999000.00")


def test_sell_limit_order_reserves_stock_and_can_be_cancelled(db):
    trading = TradingService(db)
    trading.buy(BuyRequest(symbol="2330", quantity=10, price=100))
    orders = OrderService(db)
    order = orders.place(LimitOrderCreate(symbol="2330", side="SELL", quantity=4, limit_price=110))

    holding = trading.dashboard().holdings[0]
    assert holding.reserved_quantity == 4
    assert holding.available_quantity == 6
    with pytest.raises(HTTPException, match="可用持股"):
        trading.sell(SellRequest(symbol="2330", quantity=7, price=105))

    orders.cancel(order.id)
    assert trading.dashboard().holdings[0].available_quantity == 10
    assert db.scalar(select(LimitOrder).where(LimitOrder.id == order.id)).status == OrderStatus.CANCELLED

