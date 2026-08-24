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
- 限價單輸入或選擇股票後會以最新成交價預填限價，並顯示官方參考價、漲停價與跌停價；超出當日價格區間會由畫面與 API 雙重阻擋。
- 可持久保存的觀察清單，以黑底行情表呈現即時成交價、漲跌與幅度，採台股紅漲綠跌配色；點選股票即可切換至盤中限價單並帶入代號與現價。
- Fugle 連線 heartbeat、最後訊息／tick 時間與 stale tick 保護。
- Alembic 管理資料庫 schema。
- 獨立的「個人資產」帳本，與 NT$2,000,000 模擬帳戶完全分開。
- 個人台股、黃金存摺、保險、新臺幣、臺銀外幣存款與加密貨幣資產估值。
- 個人資產總額下方按現金、黃金、股票、加密貨幣與保單彙總現值；非現金資產另顯示投入成本與投報率。
- 期初建檔可逐筆輸入多筆黃金與股票買進紀錄；相同帳戶及商品會彙總數量與成本，各筆原始日期仍保留，且不影響銀行現金餘額。
- 買賣、內部移轉、存支、保費與保單領回採不可變異動紀錄；輸入錯誤以沖銷後重登修正。
- 每日臺北時間 09:30、13:30 建立永久資產快照，顯示 7 天至全部期間的資產規模走勢。

## Docker Compose 部署

需求：Ubuntu（含 ARM64）、Docker Engine 與 Compose plugin。

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

請至少在 `.env` 設定 `POSTGRES_PASSWORD` 與 `FUGLE_API_KEY`。若要自動取得 BTC、ETH、USDT、USDC、LINK 的新臺幣報價，另填 CoinGecko Demo key：

```dotenv
COINGECKO_DEMO_API_KEY=你的_Demo_API_Key
PERSONAL_ASSET_SNAPSHOT_TIMES=09:30,13:30
```

Compose 會先等待 PostgreSQL，執行 `alembic upgrade head`，成功後才啟動 API、Dashboard、matcher 與個人資產快照服務。

- Dashboard：`http://<主機 IP>:7788`
- FastAPI 僅在 Compose 內部網路的 `8000` port 提供服務。
- API health：`GET /api/v1/health`
- 行情 health：`GET /api/v1/health/market-data`

常用維運指令：

```bash
docker compose ps
docker compose logs -f migrate api web matcher asset-snapshots
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

買單在最新成交價小於等於限價、賣單在最新成交價大於等於限價時，以委託限價整筆成交。委託價格必須介於 Fugle 回傳的當日跌停價與漲停價之間。目前不模擬 bid/ask、委託簿順位、部分成交、滑價、手續費、證交稅、交易時段或零股市場。

真實下單必須另建 Broker Gateway、冪等 client order id、回報對帳、重連與人工 kill switch；不得直接重用模擬成交路徑。

## 個人資產帳本

個人資產只記錄使用者手動登記的真實世界異動，不會送出任何交易指令。買進會由指定的新臺幣帳戶扣款，賣出會把扣除費稅後的資金轉入指定銀行帳戶；費稅可填 0。已入帳資料不直接覆寫或刪除，應在「沖銷紀錄」沖銷後重新輸入。期初建檔也可沖銷，但若已有後續異動，必須由最新一筆開始逐筆沖銷。

自動估值失敗時保留最後成功價格並標示過期，不會把資產歸零。保險現值與估值日期由使用者更新；超過一年會標示過期。歷史快照不因事後補登而回溯改寫。

黃金存摺估值優先使用臺灣銀行每公克本行買進價；若臺銀回傳瀏覽器驗證頁或連線失敗，會自動改用玉山銀行新臺幣黃金存摺每公克銀行買進價，價格來源會顯示於資產明細。兩者都失敗時才沿用最後成功價格或手動備援。
