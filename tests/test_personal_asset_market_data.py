from decimal import Decimal

import httpx

from app.core.config import get_settings
from app.services.personal_asset_market_data import PersonalAssetMarketDataProvider


def test_bot_gold_fx_and_coingecko_prices_are_parsed(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/gold":
            return httpx.Response(
                200,
                text="<html>掛牌時間：2026/08/24 13:30 黃金存摺 本行賣出 4,771 本行買進 4,720</html>",
            )
        if request.url.path == "/xrt":
            return httpx.Response(
                200,
                text='''<table><tr><td>美金 (USD)</td><td data-table="本行即期買入"><input value="30.50000"></td></tr>
                <tr><td>日圓 (JPY)</td><td data-table="本行即期買入">0.20500</td></tr></table>''',
            )
        assert request.url.path == "/api/v3/simple/price"
        assert request.headers["x-cg-demo-api-key"] == "demo-key"
        return httpx.Response(
            200,
            json={
                "bitcoin": {"twd": 3000000, "last_updated_at": 1787530200},
                "chainlink": {"twd": 700, "last_updated_at": 1787530200},
            },
        )

    settings = get_settings()
    monkeypatch.setattr(settings, "bot_gold_url", "https://example.test/gold")
    monkeypatch.setattr(settings, "bot_fx_url", "https://example.test/xrt")
    monkeypatch.setattr(settings, "coingecko_api_url", "https://example.test/api/v3")
    monkeypatch.setattr(settings, "coingecko_demo_api_key", "demo-key")
    provider = PersonalAssetMarketDataProvider(httpx.Client(transport=httpx.MockTransport(handler)))

    gold, _, _ = provider.gold_buy_price()
    fx, _, _ = provider.fx_spot_buy_rates()
    crypto, _, _ = provider.crypto_twd_prices()

    assert gold == Decimal("4720")
    assert fx == {"USD": Decimal("30.50000"), "JPY": Decimal("0.20500")}
    assert crypto["BTC"] == Decimal("3000000")
    assert crypto["LINK"] == Decimal("700")


def test_gold_falls_back_to_esun_when_bot_requires_browser_challenge(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rate.example.test":
            return httpx.Response(
                200,
                text='''<html><title>Challenge Validation</title>
                <iframe challenge="token" data-duration=30></iframe>
                <input type="hidden" name="verify-url" value="challenge"></html>''',
            )
        return httpx.Response(
            200,
            text='''<div class="goldCard">
            <span class="goldCard-name">新臺幣計價</span><span class="goldCard-unit">1 公克</span>
            <span class="goldCard-label">銀行買進</span>
            <span class="goldCard-value js-twd-buy">4,739</span>
            <span class="goldCard-timeValue js-twd-time">2026-08-24 15:25:00</span></div>''',
        )

    settings = get_settings()
    monkeypatch.setattr(settings, "bot_gold_url", "https://rate.example.test/gold")
    monkeypatch.setattr(settings, "esun_gold_url", "https://esun.example.test/gold")
    provider = PersonalAssetMarketDataProvider(httpx.Client(transport=httpx.MockTransport(handler)))

    price, quoted_at, source = provider.gold_buy_price()

    assert price == Decimal("4739")
    assert quoted_at.isoformat() == "2026-08-24T07:25:00+00:00"
    assert source == "玉山銀行黃金存摺銀行買進價"
