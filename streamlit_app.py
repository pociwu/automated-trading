from datetime import date
from decimal import Decimal
import os

import pandas as pd
import requests
import streamlit as st


API_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/") + "/api/v1"

st.set_page_config(page_title="模擬程式交易", page_icon="📈", layout="wide")
st.title("模擬程式交易")
st.caption("手動交易 · 4:2:4 部位管理 · S 點停損")


def api(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=10, **kwargs)
        response.raise_for_status()
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

tab_dashboard, tab_orders, tab_buy, tab_prices, tab_sell, tab_history = st.tabs(
    ["持股總覽", "盤中限價單", "立即買進", "收盤價 / S 點", "賣出", "交易紀錄"]
)

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
    with st.form("limit_order_form", clear_on_submit=True):
        side = st.radio("方向", ["BUY", "SELL"], horizontal=True, format_func=lambda x: "買進" if x == "BUY" else "賣出")
        c1, c2 = st.columns(2)
        if side == "SELL" and holdings_for_order:
            symbol = c1.selectbox("股票代號", [row["symbol"] for row in holdings_for_order], key="order_symbol_sell")
            selected_holding = next(row for row in holdings_for_order if row["symbol"] == symbol)
            name = selected_holding["name"]
            max_quantity = max(int(selected_holding["available_quantity"]), 1)
        else:
            symbol = c1.text_input("股票代號", placeholder="2330", key="order_symbol_buy")
            name = c2.text_input("股票名稱", placeholder="台積電", key="order_name_buy")
            max_quantity = None
        quantity = st.number_input(
            "委託股數", min_value=1, max_value=max_quantity, step=1, key="order_quantity"
        )
        limit_price = st.number_input("限價", min_value=0.01, step=0.5, key="order_limit_price")
        if st.form_submit_button("送出模擬限價單", type="primary"):
            if side == "SELL" and not holdings_for_order:
                st.error("目前沒有可掛賣單的持股。")
            elif api("POST", "/orders", json={
                "symbol": symbol, "name": name, "side": side,
                "quantity": quantity, "limit_price": limit_price,
            }):
                st.success("限價單已送出，等待盤中行情觸價。")
                st.rerun()

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
    with st.form("buy_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        symbol = c1.text_input("股票代號", placeholder="2330")
        name = c2.text_input("股票名稱", placeholder="台積電")
        c4, c5, c6 = st.columns(3)
        quantity = c4.number_input("股數", min_value=1, step=1)
        price = c5.number_input("成交價", min_value=0.01, step=0.5)
        stop = c6.number_input("S 點停損價（0 表示未設定）", min_value=0.0, step=0.5)
        if st.form_submit_button("確認模擬買進", type="primary"):
            result = api("POST", "/trades/buy", json={
                "symbol": symbol, "name": name, "quantity": quantity, "price": price,
                "stop_price": stop or None,
            })
            if result:
                st.success("買進完成")
                st.rerun()

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
        by_symbol = {row["symbol"]: row for row in holdings}
        st.subheader("4:2:4 分段賣出")
        with st.form("sell_424_form"):
            strategy_symbol = st.selectbox("股票代號", list(by_symbol), key="strategy_sell_symbol")
            completed_stage = int(by_symbol[strategy_symbol]["sell_stage"])
            st.caption(f"目前已完成第 {completed_stage} 段；下一段比例為 {[40, 20, 40][completed_stage] if completed_stage < 3 else 0}%")
            strategy_price = st.number_input("成交價", min_value=0.01, step=0.5, key="strategy_sell_price")
            if st.form_submit_button("執行下一段 4:2:4 賣出", type="primary", disabled=completed_stage >= 3):
                if api("POST", "/trades/sell-424", json={"symbol": strategy_symbol, "price": strategy_price}):
                    st.success("分段賣出完成")
                    st.rerun()
        st.divider()
        st.subheader("指定股數賣出")
        with st.form("sell_form"):
            symbol = st.selectbox("股票代號", list(by_symbol), key="sell_symbol")
            maximum = int(by_symbol[symbol]["quantity"])
            quantity = st.number_input("賣出股數", min_value=1, max_value=maximum, step=1)
            price = st.number_input("成交價", min_value=0.01, step=0.5, key="sell_price")
            if st.form_submit_button("確認模擬賣出", type="primary"):
                if api("POST", "/trades/sell", json={"symbol": symbol, "quantity": quantity, "price": price}):
                    st.success("賣出完成")
                    st.rerun()

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

