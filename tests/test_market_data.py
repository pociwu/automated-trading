from decimal import Decimal

import httpx

from app.services.market_data import TwseMarketDataProvider


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

