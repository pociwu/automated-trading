# 架構說明

## 執行模組

| 模組 | 技術 | 職責 |
|---|---|---|
| Dashboard | Streamlit | paper-trading 操作與狀態顯示 |
| API | FastAPI | 對 Dashboard 提供交易、委託、行情與 health 介面 |
| Database | PostgreSQL 17 + SQLAlchemy 2 | 帳戶、持股、成交、價格、委託與 matcher heartbeat |
| Migration | Alembic | 唯一正式 schema 變更機制 |
| Daily provider | TWSE OpenAPI | 盤後收盤價 |
| Intraday adapter | Fugle raw WebSocket | 盤中 trades tick、連線狀態與 stale-data 攔截 |
| Matcher | Python worker | 將有效 tick 交給 paper order matcher |
| Personal asset ledger | FastAPI service | 維護與模擬帳戶隔離的帳戶、部位及不可變資產異動 |
| Personal valuation | Provider adapters | Fugle/TWSE 台股、臺銀黃金與外匯、CoinGecko 加密貨幣估值 |
| Asset snapshots | Python worker | 每日臺北時間 09:30、13:30 更新行情並寫入永久資產快照 |

## 重要 seam

`TwseMarketDataProvider.get_close(symbol)` 隱藏 TWSE HTTP、cache 與資料解析；呼叫端只取得標準化 quote。

`MarketDataHealthService` 是 API 與獨立 matcher process 的共享 seam。matcher 將連線生命週期及 Fugle 微秒 timestamp 寫入資料庫；API 從同一狀態計算 `healthy`、`degraded`、`unavailable` 或 `idle`。超過 `MARKET_DATA_STALE_AFTER_SECONDS` 的 tick 會在進入 `OrderService` 前被拒絕。

`OrderService.process_tick(symbol, price)` 仍是 paper matcher seam，僅處理已通過 provider 驗證的行情。它不代表券商成交回報，也不能用於 live trading。

`PersonalAssetService` 是獨立的資產帳本 seam。所有已入帳異動保留原始列，錯誤資料透過反向異動沖銷；買賣同時更新指定銀行帳戶及移動平均成本。`PersonalAssetValuationService` 只更新估值及建立快照，不改寫交易歷史。兩者不讀寫 paper-trading 的 `accounts`、`holdings` 或 `trades`。

## 啟動順序

```text
PostgreSQL healthy → Alembic upgrade head → FastAPI healthy → Streamlit + matcher + asset-snapshots
```

FastAPI lifespan 只建立缺少的 `main` paper account，不建立或修改資料表。schema 缺失時應讓啟動失敗，交由 migration 修正。

## Live trading 隔離原則

未來若接真實券商，應建立獨立 `BrokerPort`／Gateway adapter，並隔離 paper/live 帳戶、資料表、環境變數及畫面標示。若券商 SDK 僅支援 x86_64，SDK 應部署於獨立 x86_64 Gateway，ARM 主機只透過受驗證的內部介面呼叫。
