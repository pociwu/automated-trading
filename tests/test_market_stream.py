from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.entities import LimitOrder, OrderStatus, Trade
from app.schemas.trading import LimitOrderCreate
from app.services.orders import OrderService
from app.workers import market_stream


def test_stale_fugle_tick_does_not_fill_pending_order(db, monkeypatch):
    order = OrderService(db).place(
        LimitOrderCreate(symbol="2330", side="BUY", quantity=10, limit_price=100)
    )
    monkeypatch.setattr(
        market_stream,
        "SessionLocal",
        sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False),
    )
    stale_at = datetime.now(UTC) - timedelta(seconds=11)
    source_time = int(stale_at.timestamp() * 1_000_000)

    accepted = market_stream.process_trade_tick("2330", "99", source_time)

    db.expire_all()
    assert accepted is False
    assert db.scalar(select(LimitOrder).where(LimitOrder.id == order.id)).status == OrderStatus.PENDING
    assert list(db.scalars(select(Trade)).all()) == []
