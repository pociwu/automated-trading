from decimal import Decimal

import httpx

from app.services.market_data import FugleIntradayMarketDataProvider, TwseMarketDataProvider


def test_twse_provider_parses_close_price():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"Date": "1150801", "Code": "2330", "Name": "台積電", "ClosingPrice": "1,025.00"}],
        )

    TwseMarketDataProvider._cache = None
    provider = TwseMarketDataProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    quote = provider.get_close("2330")

    assert quote.symbol == "2330"
    assert quote.name == "台積電"
    assert quote.close == Decimal("1025.00")
    assert quote.price_date.isoformat() == "2026-08-01"


def test_fugle_provider_parses_intraday_quote():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/intraday/quote/2330")
        assert request.headers["X-API-KEY"] == "test-key"
        return httpx.Response(
            200,
            json={
                "symbol": "2330",
                "name": "台積電",
                "lastTrade": {
                    "price": 1025,
                    "bid": 1020,
                    "ask": 1025,
                    "time": 1785632400000000,
                },
            },
        )

    provider = FugleIntradayMarketDataProvider(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    quote = provider.get_quote("2330")

    assert quote.symbol == "2330"
    assert quote.name == "台積電"
    assert quote.price == Decimal("1025")
    assert quote.bid == Decimal("1020")
    assert quote.ask == Decimal("1025")
    assert quote.quoted_at.isoformat() == "2026-08-02T01:00:00+00:00"


def test_fugle_provider_parses_official_daily_price_limits():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/intraday/ticker/2330")
        assert request.headers["X-API-KEY"] == "test-key"
        return httpx.Response(
            200,
            json={
                "symbol": "2330",
                "referencePrice": 1000,
                "limitDownPrice": 900,
                "limitUpPrice": 1100,
            },
        )

    provider = FugleIntradayMarketDataProvider(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    limits = provider.get_price_limits("2330")

    assert limits.symbol == "2330"
    assert limits.reference_price == Decimal("1000")
    assert limits.limit_down_price == Decimal("900")
    assert limits.limit_up_price == Decimal("1100")
