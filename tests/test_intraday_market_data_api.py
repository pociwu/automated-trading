from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.core.database import get_db
from app.schemas.trading import IntradayQuoteRead


class FakeIntradayProvider:
    def get_quote(self, symbol: str) -> IntradayQuoteRead:
        return IntradayQuoteRead(
            symbol=symbol,
            name="台積電",
            price=Decimal("1025"),
            bid=Decimal("1020"),
            ask=Decimal("1025"),
            quoted_at=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
            source="Fugle MarketData",
        )


def test_intraday_quote_endpoint_returns_latest_trade():
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[routes.get_intraday_market_data_provider] = FakeIntradayProvider

    response = TestClient(api).get("/api/v1/market-data/intraday/2330")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "2330",
        "name": "台積電",
        "price": "1025",
        "bid": "1020",
        "ask": "1025",
        "quoted_at": "2026-08-02T01:00:00Z",
        "source": "Fugle MarketData",
    }


def test_market_buy_endpoint_uses_provider_price(db):
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[routes.get_intraday_market_data_provider] = FakeIntradayProvider

    response = TestClient(api).post(
        "/api/v1/trades/buy-market",
        json={"symbol": "2330", "quantity": 2, "stop_price": 900},
    )

    assert response.status_code == 201
    assert response.json()["price"] == "1025.0000"
    assert response.json()["quantity"] == 2
