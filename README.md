# 自動化交易（模擬模式）

以 FastAPI、Streamlit、SQLAlchemy 2、PostgreSQL 17 建立的台股 paper-trading 系統。現階段所有成交均為模擬成交，不會送出真實券商委託。

## 已有功能

- 初始模擬本金 NT$2,000,000。
- 手動買賣、持股與損益、交易紀錄。
- 賣出 4:2:4 策略與 S 點全數停損。
- TWSE OpenAPI 每日收盤價同步。
- Fugle raw WebSocket 盤中 `trades` 行情。
- 立即買進與賣出畫面每 5 秒更新 Fugle 最新成交價與最佳委買／委賣價。
- 市價模擬成交會由後端在送出瞬間重新取價；沒有有效行情時不允許送出。
- GTC 限價單、資金／持股保留、取消與模擬撮合。
- Fugle 連線 heartbeat、最後訊息／tick 時間與 stale tick 保護。
- Alembic 管理資料庫 schema。

## Docker Compose 部署

需求：Ubuntu（含 ARM64）、Docker Engine 與 Compose plugin。

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

請至少在 `.env` 設定 `POSTGRES_PASSWORD` 與 `FUGLE_API_KEY`。Compose 會先等待 PostgreSQL，執行 `alembic upgrade head`，成功後才啟動 API、Dashboard 與 matcher。

- Dashboard：`http://<主機 IP>:7788`
- FastAPI 僅在 Compose 內部網路的 `8000` port 提供服務。
- API health：`GET /api/v1/health`
- 行情 health：`GET /api/v1/health/market-data`

常用維運指令：

```bash
docker compose ps
docker compose logs -f migrate api web matcher
docker compose run --rm api pytest
docker compose run --rm api alembic check
docker compose down
```

`postgres_data` volume 會保留資料；只有明確要刪除所有資料時才使用 `docker compose down -v`。

## 本機測試

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Windows PowerShell 將執行檔路徑改為 `.venv\Scripts\python.exe`。

## 模擬撮合限制

買單在最新成交價小於等於限價、賣單在最新成交價大於等於限價時，以委託限價整筆成交。目前不模擬 bid/ask、委託簿順位、部分成交、滑價、手續費、證交稅、交易時段、漲跌停或零股市場。

真實下單必須另建 Broker Gateway、冪等 client order id、回報對帳、重連與人工 kill switch；不得直接重用模擬成交路徑。
