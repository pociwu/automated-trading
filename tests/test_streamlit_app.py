from pathlib import Path

from streamlit.testing.v1 import AppTest


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_limit_order_symbol_prefills_latest_price(monkeypatch):
    def fake_request(method: str, url: str, **kwargs):
        if url.endswith("/dashboard"):
            return FakeResponse(
                {
                    "initial_capital": "2000000.00",
                    "cash": "2000000.00",
                    "reserved_cash": "0.00",
                    "available_cash": "2000000.00",
                    "holdings_cost": "0.00",
                    "market_value": "0.00",
                    "total_assets": "2000000.00",
                    "total_pnl": "0.00",
                    "return_rate": "0.00",
                    "holdings": [],
                }
            )
        if url.endswith("/market-data/intraday/2330"):
            return FakeResponse(
                {
                    "symbol": "2330",
                    "name": "台積電",
                    "price": "1025",
                    "bid": "1020",
                    "ask": "1025",
                    "quoted_at": "2026-08-03T01:00:00Z",
                    "source": "Fugle MarketData",
                }
            )
        if url.endswith("/market-data/intraday/2330/limits"):
            return FakeResponse(
                {
                    "symbol": "2330",
                    "reference_price": "1000",
                    "limit_down_price": "900",
                    "limit_up_price": "1100",
                }
            )
        return FakeResponse([])

    monkeypatch.setenv("MARKET_QUOTE_REFRESH_INTERVAL", "off")
    monkeypatch.setattr("requests.request", fake_request)
    app_path = Path(__file__).parents[1] / "streamlit_app.py"
    app = AppTest.from_file(app_path, default_timeout=20).run()

    app.text_input(key="limit_order_buy_symbol").set_value("2330").run()

    assert not app.exception
    assert app.number_input(key="limit_order_price").value == 1025.0
