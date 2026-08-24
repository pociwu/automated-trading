from decimal import Decimal

import httpx
import pytest

from app.services.market_data import FugleIntradayMarketDataProvider, MarketDataError, TwseMarketDataProvider


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


def test_fugle_provider_caches_repeated_watchlist_requests():
    calls = {"quote": 0, "limits": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/intraday/quote/" in request.url.path:
            calls["quote"] += 1
            return httpx.Response(
                200,
                json={
                    "symbol": "2330",
                    "name": "台積電",
                    "lastTrade": {"price": 1025, "time": 1785632400000000},
                },
            )
        calls["limits"] += 1
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

    provider.get_quote("2330")
    provider.get_price_limits("2330")
    provider.get_quote("2330")
    provider.get_price_limits("2330")

    assert calls == {"quote": 1, "limits": 1}


def test_fugle_provider_reports_rate_limit_status():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Rate limit exceeded"})

    provider = FugleIntradayMarketDataProvider(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MarketDataError) as error:
        provider.get_quote("2330")

    assert str(error.value) == "無法取得 2330 即時行情：Fugle HTTP 429（呼叫次數已達方案上限，請稍後再試）"
