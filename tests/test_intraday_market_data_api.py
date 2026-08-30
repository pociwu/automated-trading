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

    def get_price_limits(self, symbol: str):
        return type(
            "PriceLimits",
            (),
            {
                "symbol": symbol,
                "reference_price": Decimal("1000"),
                "limit_down_price": Decimal("900"),
                "limit_up_price": Decimal("1100"),
            },
        )()


class ForbiddenFallbackProvider:
    def get_quote(self, symbol: str):
        raise AssertionError(f"市價成交不可使用備援行情：{symbol}")


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
    api.dependency_overrides[routes.get_fugle_market_data_provider] = FakeIntradayProvider
    api.dependency_overrides[routes.get_intraday_market_data_provider] = ForbiddenFallbackProvider

    response = TestClient(api).post(
        "/api/v1/trades/buy-market",
        json={"symbol": "2330", "quantity": 2, "stop_price": 900},
    )

    assert response.status_code == 201
    assert response.json()["price"] == "1025.0000"
    assert response.json()["quantity"] == 2


def test_intraday_price_limits_endpoint_returns_official_range():
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[routes.get_intraday_market_data_provider] = FakeIntradayProvider

    response = TestClient(api).get("/api/v1/market-data/intraday/2330/limits")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "2330",
        "reference_price": "1000",
        "limit_down_price": "900",
        "limit_up_price": "1100",
    }


def test_limit_order_endpoint_rejects_price_outside_daily_limits(db):
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[routes.get_intraday_market_data_provider] = FakeIntradayProvider

    response = TestClient(api).post(
        "/api/v1/orders",
        json={"symbol": "2330", "side": "BUY", "quantity": 1, "limit_price": "0.01"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "限價必須介於跌停價 900 與漲停價 1100 之間"


def test_limit_order_endpoint_accepts_price_inside_daily_limits(db):
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[routes.get_intraday_market_data_provider] = FakeIntradayProvider

    response = TestClient(api).post(
        "/api/v1/orders",
        json={"symbol": "2330", "side": "BUY", "quantity": 1, "limit_price": "1025"},
    )

    assert response.status_code == 201
    assert response.json()["limit_price"] == "1025.0000"
    assert response.json()["name"] == "台積電"
