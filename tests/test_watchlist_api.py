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
            quoted_at=datetime(2026, 8, 10, 1, 0, tzinfo=UTC),
            source="Fugle MarketData",
        )


def client(db) -> TestClient:
    api = FastAPI()
    api.include_router(routes.router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[routes.get_intraday_market_data_provider] = FakeIntradayProvider
    return TestClient(api)


def test_watchlist_can_add_list_and_remove_symbol(db):
    api = client(db)

    created = api.post("/api/v1/watchlist", json={"symbol": " 2330 "})
    listed = api.get("/api/v1/watchlist")
    removed = api.delete("/api/v1/watchlist/2330")

    assert created.status_code == 201
    assert created.json()["symbol"] == "2330"
    assert created.json()["name"] == "台積電"
    assert [(item["symbol"], item["name"]) for item in listed.json()] == [("2330", "台積電")]
    assert removed.status_code == 204
    assert api.get("/api/v1/watchlist").json() == []


def test_watchlist_rejects_duplicate_symbol(db):
    api = client(db)

    assert api.post("/api/v1/watchlist", json={"symbol": "2330"}).status_code == 201
    duplicate = api.post("/api/v1/watchlist", json={"symbol": "2330"})

    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "此股票已在觀察清單"
