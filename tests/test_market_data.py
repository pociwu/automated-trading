from decimal import Decimal

import httpx
import pytest

from app.services.market_data import (
    FallbackIntradayMarketDataProvider,
    FugleIntradayMarketDataProvider,
    MarketDataError,
    TwseMarketDataProvider,
    TwseMisMarketDataProvider,
)


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


def test_twse_mis_provider_parses_keyless_quote_and_limits():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["ex_ch"] == "tse_2330.tw|otc_2330.tw"
        assert request.headers["Referer"].endswith("stock/fibest.jsp?stock=2330")
        return httpx.Response(
            200,
            json={
                "msgArray": [
                    {
                        "c": "2330",
                        "n": "台積電",
                        "z": "2420.0000",
                        "y": "2410.0000",
                        "u": "2650.0000",
                        "w": "2170.0000",
                        "b": "2415.0000_2410.0000_",
                        "a": "2420.0000_2425.0000_",
                        "tlong": "1787898600000",
                        "ex": "tse",
                    },
                    {"c": "", "z": "-"},
                ]
            },
        )

    provider = TwseMisMarketDataProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    quote = provider.get_quote("2330")
    limits = provider.get_price_limits("2330")

    assert calls == 1
    assert quote.symbol == "2330"
    assert quote.name == "台積電"
    assert quote.price == Decimal("2420.0000")
    assert quote.bid == Decimal("2415.0000")
    assert quote.ask == Decimal("2420.0000")
    assert quote.source == "TWSE MIS 基本市況報導（免 Key 備援）"
    assert limits.reference_price == Decimal("2410.0000")
    assert limits.limit_down_price == Decimal("2170.0000")
    assert limits.limit_up_price == Decimal("2650.0000")


def test_intraday_provider_falls_back_to_twse_mis_when_fugle_fails():
    class BrokenFugle:
        def get_quote(self, symbol: str):
            raise MarketDataError(f"Fugle {symbol} unavailable")

        def get_price_limits(self, symbol: str):
            raise MarketDataError(f"Fugle {symbol} unavailable")

    class WorkingMis:
        def get_quote(self, symbol: str):
            return type("Quote", (), {"symbol": symbol, "source": "TWSE MIS"})()

        def get_price_limits(self, symbol: str):
            return type("Limits", (), {"symbol": symbol, "reference_price": Decimal("100")})()

    provider = FallbackIntradayMarketDataProvider(primary=BrokenFugle(), fallback=WorkingMis())

    assert provider.get_quote("2330").source == "TWSE MIS"
    assert provider.get_price_limits("2330").reference_price == Decimal("100")


def test_twse_mis_provider_does_not_treat_reference_price_as_latest_trade():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "msgArray": [
                    {
                        "c": "2330",
                        "n": "台積電",
                        "z": "-",
                        "y": "2410.0000",
                        "u": "2650.0000",
                        "w": "2170.0000",
                        "tlong": "1787898600000",
                        "ex": "tse",
                    }
                ]
            },
        )

    provider = TwseMisMarketDataProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MarketDataError, match="尚無 2330 有效成交價"):
        provider.get_quote("2330")

    assert provider.get_price_limits("2330").reference_price == Decimal("2410.0000")


def test_intraday_provider_does_not_call_fallback_when_fugle_succeeds():
    class WorkingFugle:
        def get_quote(self, symbol: str):
            return type("Quote", (), {"symbol": symbol, "source": "Fugle"})()

    class ForbiddenMis:
        def get_quote(self, symbol: str):
            raise AssertionError(f"不應呼叫備援來源：{symbol}")

    provider = FallbackIntradayMarketDataProvider(primary=WorkingFugle(), fallback=ForbiddenMis())

    assert provider.get_quote("2330").source == "Fugle"


def test_intraday_provider_reports_both_source_failures():
    class BrokenProvider:
        def __init__(self, message: str) -> None:
            self.message = message

        def get_quote(self, symbol: str):
            raise MarketDataError(f"{self.message} {symbol}")

    provider = FallbackIntradayMarketDataProvider(
        primary=BrokenProvider("primary"),
        fallback=BrokenProvider("fallback"),
    )

    with pytest.raises(MarketDataError) as error:
        provider.get_quote("2330")

    assert str(error.value) == (
        "行情來源皆無法使用；Fugle：primary 2330；TWSE MIS：fallback 2330"
    )
