from pathlib import Path

import pandas as pd
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


def run_app_on_tab(app_path: Path, tab_label: str) -> AppTest:
    app = AppTest.from_file(app_path, default_timeout=20)
    app.session_state["main_tabs_0"] = tab_label
    return app.run()


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
    app = run_app_on_tab(app_path, "盤中限價單")

    app.text_input(key="limit_order_buy_symbol").set_value("2330").run()

    assert not app.exception
    assert app.number_input(key="limit_order_price").value == 1025.0


def test_watchlist_renders_taiwan_red_up_market_board(monkeypatch):
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
        if url.endswith("/watchlist"):
            return FakeResponse(
                [{"id": 1, "symbol": "2330", "name": "台積電", "created_at": "2026-08-10T01:00:00"}]
            )
        if url.endswith("/market-data/intraday/2330"):
            return FakeResponse(
                {
                    "symbol": "2330",
                    "name": "台積電",
                    "price": "1025",
                    "bid": "1020",
                    "ask": "1025",
                    "quoted_at": "2026-08-10T01:00:00Z",
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
    app = run_app_on_tab(app_path, "觀察清單")

    board = next(markdown.value for markdown in app.markdown if "watchlist-board" in markdown.value)
    assert not app.exception
    assert "台積電" in board
    assert "1,025.00" in board
    assert "+25.00" in board
    assert "+2.50%" in board
    assert "watch-row up" in board
    assert '?order_symbol=2330' in board


def test_watchlist_selection_prefills_limit_order_and_opens_order_tab(monkeypatch):
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
                    "quoted_at": "2026-08-10T01:00:00Z",
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
    app = AppTest.from_file(app_path, default_timeout=20)
    app.query_params["order_symbol"] = "2330"

    app.run()

    assert not app.exception
    assert app.text_input(key="limit_order_buy_symbol").value == "2330"
    assert app.number_input(key="limit_order_price").value == 1025.0
    assert app.tabs[2].label == "盤中限價單"


def test_personal_assets_show_category_summary_below_total(monkeypatch):
    positions = [
        {"asset_type": "TWD", "current_value": "100000", "total_cost": "100000", "symbol": "TWD", "name": "活存"},
        {"asset_type": "FX", "current_value": "20000", "total_cost": "18000", "symbol": "USD", "name": "美元"},
        {"asset_type": "GOLD", "current_value": "55000", "total_cost": "50000", "symbol": "BOT_GOLD_TWD", "name": "黃金存摺"},
        {"asset_type": "STOCK", "current_value": "120000", "total_cost": "100000", "symbol": "2330", "name": "台積電"},
        {"asset_type": "CRYPTO", "current_value": "8000", "total_cost": "10000", "symbol": "LINK", "name": "Chainlink"},
        {"asset_type": "INSURANCE", "current_value": "90000", "total_cost": "100000", "symbol": "POLICY", "name": "保單"},
    ]
    for index, position in enumerate(positions, start=1):
        position.update({"id": index, "account_name": "測試帳戶"})

    def fake_request(method: str, url: str, **kwargs):
        if "personal-assets/dashboard" in url:
            return FakeResponse(
                {
                    "total_value": "393000.00",
                    "total_basis": "378000.00",
                    "estimated_difference": "15000.00",
                    "stale_count": 0,
                    "positions": positions,
                    "snapshots": [],
                    "has_backdated_changes": False,
                }
            )
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
        return FakeResponse([])

    monkeypatch.setenv("MARKET_QUOTE_REFRESH_INTERVAL", "off")
    monkeypatch.setattr("requests.request", fake_request)
    app_path = Path(__file__).parents[1] / "streamlit_app.py"
    app = run_app_on_tab(app_path, "個人資產")

    summary = next(
        dataframe.value
        for dataframe in app.dataframe
        if "資產類別" in dataframe.value.columns
    )
    cash = summary.loc[summary["資產類別"] == "現金"].iloc[0]
    stock = summary.loc[summary["資產類別"] == "股票"].iloc[0]

    assert not app.exception
    assert cash["現值"] == 120000.0
    assert pd.isna(cash["投入成本"])
    assert pd.isna(cash["投報率"])
    assert stock["投入成本"] == 100000.0
    assert stock["現值"] == 120000.0
    assert stock["投報率"] == 20.0


def test_personal_asset_tab_does_not_render_hidden_market_refresh_fragments(monkeypatch):
    requested_urls = []

    def fake_request(method: str, url: str, **kwargs):
        requested_urls.append(url)
        if "personal-assets/dashboard" in url:
            return FakeResponse(
                {
                    "total_value": "0.00",
                    "total_basis": "0.00",
                    "estimated_difference": "0.00",
                    "stale_count": 0,
                    "positions": [],
                    "snapshots": [],
                    "has_backdated_changes": False,
                }
            )
        if url.endswith("/personal-assets/accounts"):
            return FakeResponse(
                [
                    {
                        "id": 1,
                        "name": "個人台股",
                        "institution": "富邦證券",
                        "asset_type": "STOCK",
                        "currency": "TWD",
                    }
                ]
            )
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
                    "holdings": [
                        {
                            "symbol": "2330",
                            "name": "台積電",
                            "quantity": 1000,
                            "average_cost": "900.00",
                            "last_price": "950.00",
                            "stop_price": None,
                            "sell_stage": 0,
                            "reserved_quantity": 0,
                            "available_quantity": 1000,
                            "market_value": "950000.00",
                            "unrealized_pnl": "50000.00",
                            "return_rate": "5.56",
                        }
                    ],
                }
            )
        return FakeResponse([])

    monkeypatch.setenv("MARKET_QUOTE_REFRESH_INTERVAL", "off")
    monkeypatch.setattr("requests.request", fake_request)
    app_path = Path(__file__).parents[1] / "streamlit_app.py"
    app = AppTest.from_file(app_path, default_timeout=20)
    app.session_state["main_tabs_0"] = "個人資產"

    app.run()

    assert not app.exception
    assert any("personal-assets/dashboard" in url for url in requested_urls)
    assert not any(url.endswith("/watchlist") for url in requested_urls)
    assert not any(widget.key == "limit_order_side" for widget in app.radio)
    assert not any(widget.key == "limit_order_buy_symbol" for widget in app.text_input)
    assert not any(widget.key == "market_buy_symbol" for widget in app.text_input)
    assert not any(widget.key == "market_sell_symbol" for widget in app.selectbox)


def test_stock_opening_symbol_prefills_name_and_uses_share_quantity(monkeypatch):
    submitted = []

    def fake_request(method: str, url: str, **kwargs):
        if "personal-assets/dashboard" in url:
            return FakeResponse(
                {
                    "total_value": "0.00",
                    "total_basis": "0.00",
                    "estimated_difference": "0.00",
                    "stale_count": 0,
                    "positions": [],
                    "snapshots": [],
                    "has_backdated_changes": False,
                }
            )
        if url.endswith("/personal-assets/accounts"):
            return FakeResponse(
                [
                    {
                        "id": 1,
                        "name": "個人台股",
                        "institution": "富邦證券",
                        "asset_type": "STOCK",
                        "currency": "TWD",
                    }
                ]
            )
        if url.endswith("/market-data/4916"):
            return FakeResponse(
                {
                    "symbol": "4916",
                    "name": "事欣科",
                    "close": "45.50",
                    "price_date": "2026-08-24",
                    "source": "TWSE OpenAPI",
                }
            )
        if method == "POST" and url.endswith("/personal-assets/opening"):
            submitted.append(kwargs["json"])
            return FakeResponse({"id": 1})
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
        return FakeResponse([])

    monkeypatch.setenv("MARKET_QUOTE_REFRESH_INTERVAL", "off")
    monkeypatch.setattr("requests.request", fake_request)
    app_path = Path(__file__).parents[1] / "streamlit_app.py"
    app = run_app_on_tab(app_path, "個人資產")

    app.text_input(key="personal_opening_symbol").set_value("4916").run()

    app.number_input(key="personal_opening_quantity").set_value(100).run()
    app.number_input(key="personal_opening_cost").set_value(45.5).run()
    next(button for button in app.button if button.label == "建立期初部位").click().run()

    assert not app.exception
    assert submitted[0]["name"] == "事欣科"
    assert submitted[0]["quantity"] == 100
    assert submitted[0]["total_cost"] == 4550.0
    assert app.text_input(key="reset_opening_confirmation").label == "輸入「清空期初資產」確認"
    assert any(button.label == "清空並重置期初資產" for button in app.button)


def test_switching_opening_account_does_not_lookup_previous_account_symbol(monkeypatch):
    requested_urls = []

    def fake_request(method: str, url: str, **kwargs):
        requested_urls.append(url)
        if "personal-assets/dashboard" in url:
            return FakeResponse(
                {
                    "total_value": "0.00",
                    "total_basis": "0.00",
                    "estimated_difference": "0.00",
                    "stale_count": 0,
                    "positions": [],
                    "snapshots": [],
                    "has_backdated_changes": False,
                }
            )
        if url.endswith("/personal-assets/accounts"):
            return FakeResponse(
                [
                    {
                        "id": 1,
                        "name": "台幣帳戶",
                        "institution": "銀行",
                        "asset_type": "TWD",
                        "currency": "TWD",
                    },
                    {
                        "id": 2,
                        "name": "股票帳戶",
                        "institution": "券商",
                        "asset_type": "STOCK",
                        "currency": "TWD",
                    },
                ]
            )
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
        return FakeResponse([])

    monkeypatch.setenv("MARKET_QUOTE_REFRESH_INTERVAL", "off")
    monkeypatch.setattr("requests.request", fake_request)
    app_path = Path(__file__).parents[1] / "streamlit_app.py"
    app = run_app_on_tab(app_path, "個人資產")
    requested_urls.clear()

    app.selectbox(key="opening_account").select("股票帳戶｜個人台股｜券商").run()

    assert not app.exception
    assert app.text_input(key="personal_opening_symbol").value == ""
    assert not any(url.endswith("/market-data/TWD") for url in requested_urls)

    # 模擬瀏覽器切換帳戶後，舊股票欄位的 on_change 事件延遲送達。
    requested_urls.clear()
    app.session_state["personal_opening_context"] = "1:TWD"
    app.text_input(key="personal_opening_symbol").set_value("TWD").run()

    assert not app.exception
    assert not any(url.endswith("/market-data/TWD") for url in requested_urls)


def test_stock_opening_can_be_deleted_from_opening_tab(monkeypatch):
    reversed_urls = []
    position = {
        "id": 4,
        "account_id": 1,
        "account_name": "個人台股",
        "institution": "富邦證券",
        "asset_type": "STOCK",
        "symbol": "4916",
        "name": "事欣科",
        "quantity": "100",
        "total_cost": "4550",
        "current_value": "5000",
    }
    opening = {
        "id": 9,
        "kind": "OPENING",
        "source_position_id": None,
        "target_position_id": 4,
        "quantity": "100",
        "gross_amount": "4550",
        "fees": "0",
        "net_amount": "4550",
        "cost_basis": "4550",
        "realized_pnl": "0",
        "occurred_at": "2026-08-20T01:00:00",
        "note": "",
        "reversal_of_id": None,
        "reversed_at": None,
    }

    def fake_request(method: str, url: str, **kwargs):
        if "personal-assets/dashboard" in url:
            return FakeResponse(
                {
                    "total_value": "5000.00",
                    "total_basis": "4550.00",
                    "estimated_difference": "450.00",
                    "stale_count": 0,
                    "positions": [position],
                    "snapshots": [],
                    "has_backdated_changes": False,
                }
            )
        if url.endswith("/personal-assets/accounts"):
            return FakeResponse(
                [{"id": 1, "name": "個人台股", "institution": "富邦證券", "asset_type": "STOCK", "currency": "TWD"}]
            )
        if "/personal-assets/transactions" in url and method == "GET":
            return FakeResponse([opening])
        if method == "POST" and url.endswith("/personal-assets/transactions/9/reverse"):
            reversed_urls.append(url)
            return FakeResponse({"id": 10, "kind": "REVERSAL"}, status_code=201)
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
        return FakeResponse([])

    monkeypatch.setenv("MARKET_QUOTE_REFRESH_INTERVAL", "off")
    monkeypatch.setattr("requests.request", fake_request)
    app_path = Path(__file__).parents[1] / "streamlit_app.py"
    app = run_app_on_tab(app_path, "個人資產")

    app.checkbox(key="confirm_delete_stock_opening").check().run()
    next(button for button in app.button if button.label == "刪除期初資料").click().run()

    assert not app.exception
    assert reversed_urls and reversed_urls[0].endswith("/personal-assets/transactions/9/reverse")
