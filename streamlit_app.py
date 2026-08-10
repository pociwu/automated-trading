from datetime import date
from decimal import Decimal
from html import escape
import os
from urllib.parse import quote as url_quote

import pandas as pd
import requests
import streamlit as st


API_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
refresh_setting = os.getenv("MARKET_QUOTE_REFRESH_INTERVAL", "5s").strip().lower()
MARKET_QUOTE_REFRESH_INTERVAL = None if refresh_setting == "off" else refresh_setting

st.set_page_config(page_title="模擬程式交易", page_icon="📈", layout="wide")

requested_order_symbol = str(st.query_params.get("order_symbol", "")).strip().upper()
if requested_order_symbol:
    st.session_state["limit_order_buy_symbol"] = requested_order_symbol
    st.session_state["main_tab_default"] = "盤中限價單"
    st.session_state["main_tabs_version"] = st.session_state.get("main_tabs_version", 0) + 1
    st.query_params.clear()

st.title("模擬程式交易")
st.caption("手動交易 · 4:2:4 部位管理 · S 點停損")


def api(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=10, **kwargs)
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()
    except requests.RequestException as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("detail", "")
            except ValueError:
                detail = exc.response.text
        st.error(detail or f"無法連線至 API：{exc}")
        return None


def show_intraday_quote(quote: dict) -> None:
    metrics = st.columns(4)
    metrics[0].metric("最新成交價", f'NT$ {float(quote["price"]):,.2f}')
    metrics[1].metric("委買價", f'NT$ {float(quote["bid"]):,.2f}' if quote.get("bid") else "—")
    metrics[2].metric("委賣價", f'NT$ {float(quote["ask"]):,.2f}' if quote.get("ask") else "—")
    metrics[3].metric("股票名稱", quote.get("name") or "—")
    quoted_at = pd.Timestamp(quote["quoted_at"]).tz_convert("Asia/Taipei").strftime("%Y-%m-%d %H:%M:%S")
    st.caption(f'行情時間：{quoted_at}｜來源：{quote["source"]}｜每 5 秒更新')


def watchlist_board_html(rows: list[dict]) -> str:
    rendered_rows = []
    for row in rows:
        name = escape(row.get("name") or row["symbol"])
        symbol = escape(row["symbol"])
        order_url = f"?order_symbol={url_quote(row['symbol'])}"
        if row.get("price") is None or row.get("reference_price") is None:
            rendered_rows.append(
                f'<a class="watch-row unavailable" href="{order_url}" target="_self"><div><strong>{name}</strong>'
                f'<small>{symbol}・點選下單</small></div><div>—</div><div>—</div><div>—</div></a>'
            )
            continue
        price = Decimal(str(row["price"]))
        reference = Decimal(str(row["reference_price"]))
        change = price - reference
        change_rate = change / reference * Decimal("100")
        direction = "up" if change > 0 else "down" if change < 0 else "flat"
        rendered_rows.append(
            f'<a class="watch-row {direction}" href="{order_url}" target="_self"><div><strong>{name}</strong>'
            f'<small>{symbol}・點選下單</small></div><div>{price:,.2f}</div><div>{change:+,.2f}</div>'
            f'<div>{change_rate:+.2f}%</div></a>'
        )
    body = "".join(rendered_rows) or '<div class="watch-empty">尚未加入觀察股票</div>'
    return f"""
    <style>
      .watchlist-board {{background:#050505;border:1px solid #292d33;border-radius:14px;overflow:hidden;
        color:#f5f5f5;font-variant-numeric:tabular-nums;box-shadow:0 12px 30px rgba(0,0,0,.28)}}
      .watch-title {{padding:18px 20px 12px;font-size:1.35rem;font-weight:800;background:#1c1f23}}
      .watch-head,.watch-row {{display:grid;grid-template-columns:minmax(130px,1.35fr) repeat(3,minmax(92px,1fr));
        align-items:center;gap:12px;padding:12px 20px}}
      .watch-head {{background:linear-gradient(#22252a,#111);color:#d8d8d8;font-weight:700;border-bottom:1px solid #31343a}}
      .watch-row {{min-height:68px;border-bottom:1px solid #24272b;font-size:1.2rem;font-weight:750;
        text-decoration:none;color:inherit;transition:background .15s ease,transform .15s ease}}
      .watch-row:hover {{background:#15181c;transform:translateX(2px)}}
      .watch-row:last-child {{border-bottom:0}}
      .watch-row>div:not(:first-child),.watch-head>div:not(:first-child) {{text-align:right}}
      .watch-row strong {{display:block;color:#f4f4f4;font-size:1.08rem}}
      .watch-row small {{display:block;color:#858b93;font-size:.72rem;margin-top:3px;font-weight:500}}
      .watch-row.up>div:not(:first-child) {{color:#ff2d3f}}
      .watch-row.down>div:not(:first-child) {{color:#00e56b}}
      .watch-row.flat>div:not(:first-child) {{color:#f2f2f2}}
      .watch-row.unavailable>div:not(:first-child) {{color:#7d828a}}
      .watch-empty {{padding:34px;text-align:center;color:#868b92}}
      @media(max-width:700px) {{
        .watch-head,.watch-row {{grid-template-columns:minmax(90px,1.25fr) repeat(3,minmax(64px,1fr));gap:6px;padding:10px 12px}}
        .watch-head {{font-size:.8rem}} .watch-row {{font-size:.92rem;min-height:60px}}
      }}
    </style>
    <div class="watchlist-board">
      <div class="watch-title">自選觀察</div>
      <div class="watch-head"><div>商品</div><div>成交</div><div>漲跌</div><div>幅度</div></div>
      {body}
    </div>
    """


@st.fragment(run_every=MARKET_QUOTE_REFRESH_INTERVAL)
def render_watchlist() -> None:
    items = api("GET", "/watchlist") or []
    rows = []
    for item in items:
        quote = api("GET", f'/market-data/intraday/{item["symbol"]}')
        limits = api("GET", f'/market-data/intraday/{item["symbol"]}/limits')
        rows.append(
            {
                **item,
                "name": (quote or {}).get("name") or item.get("name"),
                "price": (quote or {}).get("price"),
                "reference_price": (limits or {}).get("reference_price"),
            }
        )
    st.markdown(watchlist_board_html(rows), unsafe_allow_html=True)
    st.caption("點選股票可帶入盤中限價單。紅色為上漲、綠色為下跌；漲跌與幅度以當日參考價計算，每 5 秒更新。")

    with st.expander("管理觀察清單", expanded=not items):
        with st.form("watchlist_add_form", clear_on_submit=True):
            symbol = st.text_input("股票代號", placeholder="例如 2330", key="watchlist_symbol").strip().upper()
            if st.form_submit_button("加入觀察", type="primary") and symbol:
                if api("POST", "/watchlist", json={"symbol": symbol}):
                    st.success(f"已將 {symbol} 加入觀察清單")
                    st.rerun()
        if items:
            labels = {f'{item["symbol"]} {item.get("name", "")}': item["symbol"] for item in items}
            selected = st.selectbox("移除股票", list(labels), key="watchlist_remove_symbol")
            if st.button("移除觀察", key="watchlist_remove_button"):
                if api("DELETE", f"/watchlist/{labels[selected]}") is not None:
                    st.success("已從觀察清單移除")
                    st.rerun()


@st.fragment(run_every=MARKET_QUOTE_REFRESH_INTERVAL)
def render_limit_order(holdings: list[dict]) -> None:
    side = st.radio(
        "方向",
        ["BUY", "SELL"],
        horizontal=True,
        format_func=lambda value: "買進" if value == "BUY" else "賣出",
        key="limit_order_side",
    )

    if side == "SELL":
        available = [row for row in holdings if int(row["available_quantity"]) > 0]
        if not available:
            st.info("目前沒有可掛賣單的持股，或持股已被其他委託保留。")
            return
        by_symbol = {row["symbol"]: row for row in available}
        symbol = st.selectbox("股票代號", list(by_symbol), key="limit_order_sell_symbol")
        max_quantity = int(by_symbol[symbol]["available_quantity"])
    else:
        symbol = st.text_input(
            "股票代號",
            placeholder="2330",
            key="limit_order_buy_symbol",
        ).strip().upper()
        max_quantity = None

    if not symbol:
        st.info("輸入股票代號後，系統會自動將最新成交價帶入限價。")
        return

    quote = api("GET", f"/market-data/intraday/{symbol}")
    if not quote:
        st.warning("尚未取得有效行情，因此無法送出限價單。")
        return
    limits = api("GET", f"/market-data/intraday/{symbol}/limits")
    if not limits:
        st.warning("尚未取得官方漲跌停價格，因此無法送出限價單。")
        return
    show_intraday_quote(quote)

    price_key = "limit_order_price"
    quote_marker = f"{side}:{symbol}"
    if st.session_state.get("limit_order_quote_marker") != quote_marker:
        st.session_state[price_key] = float(quote["price"])
        st.session_state["limit_order_quote_marker"] = quote_marker
    if st.button("以最新成交價更新限價", key="refresh_limit_order_price"):
        st.session_state[price_key] = float(quote["price"])

    limit_down = float(limits["limit_down_price"])
    limit_up = float(limits["limit_up_price"])
    reference = float(limits["reference_price"])
    st.caption(
        f"參考價 NT$ {reference:,.2f}｜跌停 NT$ {limit_down:,.2f}｜漲停 NT$ {limit_up:,.2f}。"
        "最新成交價只在首次選擇股票或按上方按鈕時帶入；你仍可自行調整限價。"
    )
    with st.form("limit_order_form", clear_on_submit=True):
        quantity = st.number_input(
            "委託股數",
            min_value=1,
            max_value=max_quantity,
            step=1,
            key="limit_order_quantity",
        )
        limit_price = st.number_input(
            "限價",
            min_value=limit_down,
            max_value=limit_up,
            step=0.5,
            key=price_key,
        )
        if st.form_submit_button("送出模擬限價單", type="primary"):
            result = api(
                "POST",
                "/orders",
                json={
                    "symbol": symbol,
                    "name": quote.get("name", ""),
                    "side": side,
                    "quantity": quantity,
                    "limit_price": limit_price,
                },
            )
            if result:
                st.success("限價單已送出，等待盤中行情觸價。")
                st.rerun()


@st.fragment(run_every=MARKET_QUOTE_REFRESH_INTERVAL)
def render_market_buy() -> None:
    symbol = st.text_input("股票代號", placeholder="2330", key="market_buy_symbol").strip().upper()
    if not symbol:
        st.info("輸入股票代號後，系統會自動載入即時行情。")
        return

    quote = api("GET", f"/market-data/intraday/{symbol}")
    if not quote:
        st.warning("尚未取得有效行情，因此無法送出買進。")
        return
    show_intraday_quote(quote)
    st.caption("送出時後端會再次取得最新成交價，不使用瀏覽器中的舊價格。")

    with st.form("market_buy_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        quantity = c1.number_input("股數", min_value=1, step=1)
        stop = c2.number_input("S 點停損價（0 表示未設定）", min_value=0.0, step=0.5)
        if st.form_submit_button("依最新價確認模擬買進", type="primary"):
            result = api(
                "POST",
                "/trades/buy-market",
                json={"symbol": symbol, "quantity": quantity, "stop_price": stop or None},
            )
            if result:
                st.success(f'買進完成，實際模擬成交價 NT$ {float(result["price"]):,.2f}')
                st.rerun()


@st.fragment(run_every=MARKET_QUOTE_REFRESH_INTERVAL)
def render_market_sell(holdings: list[dict]) -> None:
    by_symbol = {row["symbol"]: row for row in holdings}
    symbol = st.selectbox("股票代號", list(by_symbol), key="market_sell_symbol")
    quote = api("GET", f"/market-data/intraday/{symbol}")
    if not quote:
        st.warning("尚未取得有效行情，因此無法送出賣出。")
        return
    show_intraday_quote(quote)
    st.caption("送出時後端會再次取得最新成交價，不使用瀏覽器中的舊價格。")

    completed_stage = int(by_symbol[symbol]["sell_stage"])
    st.subheader("4:2:4 分段賣出")
    st.caption(
        f"目前已完成第 {completed_stage} 段；下一段比例為 "
        f"{[40, 20, 40][completed_stage] if completed_stage < 3 else 0}%"
    )
    with st.form("market_sell_424_form"):
        if st.form_submit_button(
            "依最新價執行下一段 4:2:4 賣出",
            type="primary",
            disabled=completed_stage >= 3,
        ):
            result = api("POST", "/trades/sell-424-market", json={"symbol": symbol})
            if result:
                st.success(f'分段賣出完成，實際模擬成交價 NT$ {float(result["price"]):,.2f}')
                st.rerun()

    st.divider()
    st.subheader("指定股數賣出")
    maximum = int(by_symbol[symbol]["available_quantity"])
    if maximum <= 0:
        st.info("此持股目前全部被等待中委託保留，請先取消委託。")
        return
    with st.form("market_sell_form"):
        quantity = st.number_input("賣出股數", min_value=1, max_value=maximum, step=1)
        if st.form_submit_button("依最新價確認模擬賣出", type="primary"):
            result = api(
                "POST",
                "/trades/sell-market",
                json={"symbol": symbol, "quantity": quantity},
            )
            if result:
                st.success(f'賣出完成，實際模擬成交價 NT$ {float(result["price"]):,.2f}')
                st.rerun()


dashboard = api("GET", "/dashboard")
if dashboard:
    metrics = st.columns(5)
    items = [
        ("總資產", dashboard["total_assets"]),
        ("可用現金", dashboard["available_cash"]),
        ("持股市值", dashboard["market_value"]),
        ("總損益", dashboard["total_pnl"]),
        ("報酬率", f'{dashboard["return_rate"]}%'),
    ]
    for col, (label, value) in zip(metrics, items, strict=True):
        col.metric(label, f"{float(value):,.2f}" if label != "報酬率" else value)
    if float(dashboard["reserved_cash"]) > 0:
        st.caption(f'掛單凍結現金：NT$ {float(dashboard["reserved_cash"]):,.2f}')

main_tab_names = ["觀察清單", "持股總覽", "盤中限價單", "立即買進", "收盤價 / S 點", "賣出", "交易紀錄"]
tab_watchlist, tab_dashboard, tab_orders, tab_buy, tab_prices, tab_sell, tab_history = st.tabs(
    main_tab_names,
    default=st.session_state.get("main_tab_default", "觀察清單"),
    key=f'main_tabs_{st.session_state.get("main_tabs_version", 0)}',
)

with tab_watchlist:
    render_watchlist()

with tab_dashboard:
    if dashboard and dashboard["holdings"]:
        frame = pd.DataFrame(dashboard["holdings"]).rename(
            columns={
                "symbol": "代號", "name": "名稱", "quantity": "股數", "average_cost": "均價",
                "last_price": "最新價", "stop_price": "S 點", "sell_stage": "424 已賣階段",
                "reserved_quantity": "掛單股數", "available_quantity": "可用股數",
                "market_value": "市值", "unrealized_pnl": "未實現損益", "return_rate": "報酬率(%)",
            }
        )
        st.dataframe(frame, use_container_width=True, hide_index=True)
    else:
        st.info("目前沒有持股。")

with tab_orders:
    st.caption("買單：最新成交價 ≤ 限價時成交；賣單：最新成交價 ≥ 限價時成交。")
    holdings_for_order = dashboard.get("holdings", []) if dashboard else []
    render_limit_order(holdings_for_order)

    orders = api("GET", "/orders")
    if orders:
        st.subheader("委託紀錄")
        order_frame = pd.DataFrame(orders).rename(columns={
            "id": "單號", "symbol": "代號", "name": "名稱", "side": "方向",
            "quantity": "股數", "limit_price": "限價", "status": "狀態",
            "filled_price": "成交價", "trade_id": "交易編號", "placed_at": "掛單時間", "filled_at": "成交時間",
            "cancelled_at": "取消時間",
        })
        st.dataframe(order_frame, use_container_width=True, hide_index=True)
        pending = [order for order in orders if order["status"] == "PENDING"]
        if pending:
            cancel_id = st.selectbox("取消等待中的委託", [order["id"] for order in pending])
            if st.button("取消委託") and api("DELETE", f"/orders/{cancel_id}"):
                st.success("委託已取消")
                st.rerun()

with tab_buy:
    render_market_buy()

with tab_prices:
    symbols = [row["symbol"] for row in dashboard.get("holdings", [])] if dashboard else []
    if not symbols:
        st.info("請先建立持股。")
    else:
        st.subheader("官方行情")
        selected_symbol = st.selectbox("選擇持股", symbols, key="sync_symbol")
        if st.button("從 TWSE 取得最新收盤價並檢查 S 點", type="primary"):
            synced = api("POST", f"/prices/sync/{selected_symbol}")
            if synced:
                if synced["stopped_out"]:
                    st.warning("官方收盤價已觸發 S 點，持股已全數模擬賣出。")
                else:
                    st.success(f'已更新收盤價：{float(synced["close"]):,.2f}')
                st.rerun()
        st.divider()
        st.subheader("手動輸入備援")
        with st.form("price_form"):
            symbol = st.selectbox("股票代號", symbols, key="price_symbol")
            c1, c2 = st.columns(2)
            close = c1.number_input("每日收盤價", min_value=0.01, step=0.5)
            price_date = c2.date_input("日期", value=date.today())
            if st.form_submit_button("更新並檢查停損", type="primary"):
                result = api("POST", "/prices/close", json={
                    "symbol": symbol, "close": close, "price_date": price_date.isoformat(),
                })
                if result:
                    if result["stopped_out"]:
                        st.warning("已觸發 S 點，持股已按本次收盤價全數模擬賣出。")
                    else:
                        st.success("收盤價已更新，未觸發停損。")
                    st.rerun()
        selected = next((row for row in dashboard["holdings"] if row["symbol"] == symbol), None)
        if selected:
            with st.form("stop_form"):
                value = float(selected["stop_price"] or 0)
                new_stop = st.number_input("調整 S 點（0 表示取消）", min_value=0.0, value=value, step=0.5)
                if st.form_submit_button("儲存 S 點"):
                    if api("PATCH", f"/holdings/{symbol}/stop", json={"stop_price": new_stop or None}):
                        st.success("S 點已更新")
                        st.rerun()

with tab_sell:
    holdings = dashboard.get("holdings", []) if dashboard else []
    if not holdings:
        st.info("目前沒有可賣出的持股。")
    else:
        render_market_sell(holdings)

with tab_history:
    trades = api("GET", "/trades")
    if trades:
        trade_frame = pd.DataFrame(trades).rename(columns={
            "traded_at": "時間", "symbol": "代號", "name": "名稱", "side": "方向",
            "quantity": "股數", "price": "價格", "amount": "金額", "realized_pnl": "已實現損益",
            "reason": "原因", "stage": "階段",
        })
        st.dataframe(trade_frame.drop(columns=["id"]), use_container_width=True, hide_index=True)
    else:
        st.info("尚無交易紀錄。")
