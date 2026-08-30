from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "自動化交易（模擬模式）"
    database_url: str = "postgresql+psycopg://trading:change-me@db:5432/trading"
    initial_capital: Decimal = Decimal("2000000")
    api_base_url: str = "http://localhost:8000"
    twse_api_url: str = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    twse_mis_url: str = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    market_data_timeout_seconds: float = 15.0
    market_data_stale_after_seconds: float = 10.0
    fugle_api_key: str = ""
    fugle_rest_url: str = "https://api.fugle.tw/marketdata/v1.0/stock"
    fugle_websocket_url: str = "wss://api.fugle.tw/marketdata/v1.0/stock/streaming"
    fugle_max_subscriptions: int = 5
    fugle_quote_cache_seconds: float = 10.0
    fugle_limits_cache_seconds: float = 300.0
    bot_fx_url: str = "https://rate.bot.com.tw/xrt?Lang=zh-TW"
    bot_gold_url: str = "https://rate.bot.com.tw/gold?Lang=zh-TW"
    esun_gold_url: str = "https://wealth.esunbank.com/zh-tw/gold/price/current-price"
    coingecko_api_url: str = "https://api.coingecko.com/api/v3"
    coingecko_demo_api_key: str = ""
    personal_asset_snapshot_times: str = "09:30,13:30"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
